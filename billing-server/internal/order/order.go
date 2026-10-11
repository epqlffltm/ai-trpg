// billing-server/internal/order/order.go

// Package order 는 크레딧을 사는 주문을 만들고, 결제 대행사의 승인을 받아 크레딧을 넣는다.
//
// 주문의 상태는 한 방향으로만 흐른다.
//
//		pending -> confirming -> paid
//		                      -> failed
//
//	  - pending: 주문을 만들었다. 아직 결제 대행사를 부르지 않았다.
//	  - confirming: 결제 대행사에 승인을 요청했다. 답을 받기 전이거나, 답을 받지 못했다.
//	  - paid: 승인되었다. 크레딧이 들어갔다.
//	  - failed: 거절되었다. 돈이 나가지 않았다.
//
// 지키는 것 셋.
//
//  1. 결제 대행사를 부르는 동안 DB 의 트랜잭션을 열어 두지 않는다. 다른 서버의 답을 기다리며 줄을 잠그면
//     그 서버가 느려질 때 이 서버의 DB 연결이 바닥난다. 그래서 부르기 전에 confirming 으로 적어 두고,
//     답을 받은 뒤에 새 트랜잭션에서 결과를 적는다.
//  2. 주문을 paid 로 바꾸는 일과 크레딧을 넣는 일은 한 트랜잭션이다. 하나만 되는 일이 없다.
//  3. 상태는 "지금 이 상태일 때만" 바꾼다(조건이 붙은 UPDATE). 같은 요청이 겹쳐 와도 크레딧은 한 번만 들어간다.
//
// 답을 받지 못한 주문은 confirming 에 남는다. 같은 승인 요청을 다시 보내거나 결제 대행사의 알림이 오면
// 결제 대행사에 결과를 물어 마저 끝낸다.
package order

import (
	"context"
	"errors"
	"regexp"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// ProviderTimeout 은 결제 대행사의 답을 기다리는 가장 긴 시간이다. 넘으면 결과를 모르는 것으로 본다.
const ProviderTimeout = 10 * time.Second

// FailureCodeUnspecified 는 결제 대행사가 거절하면서 이유를 주지 않았을 때 적는 글자다.
const FailureCodeUnspecified = "declined"

var (
	// ErrUnknownProduct 는 그런 상품이 없다는 오류다.
	ErrUnknownProduct = errors.New("그런 상품이 없습니다")
	// ErrInvalidKey 는 중복 방지 키의 모양이 틀렸다는 오류다.
	ErrInvalidKey = errors.New("중복 방지 키는 영문자, 숫자, 밑줄, 붙임표로 된 8자에서 128자여야 합니다")
	// ErrKeyReused 는 같은 중복 방지 키로 다른 내용의 주문을 만들려 했다는 오류다.
	ErrKeyReused = errors.New("같은 중복 방지 키로 다른 주문을 만들 수 없습니다")
	// ErrNotFound 는 그런 주문이 없다는 오류다. 남의 주문도 없는 것으로 답한다.
	ErrNotFound = errors.New("그런 주문이 없습니다")
	// ErrInvalidPaymentKey 는 결제 번호의 모양이 틀렸다는 오류다.
	ErrInvalidPaymentKey = errors.New("결제 번호는 빈칸 없는 영문자, 숫자, 밑줄, 붙임표로 된 200자 이하여야 합니다")
	// ErrPaymentKeyMismatch 는 이 주문이 이미 다른 결제 번호로 진행되었다는 오류다.
	ErrPaymentKeyMismatch = errors.New("이 주문은 다른 결제로 이미 진행되었습니다")
	// ErrPaymentKeyUsed 는 그 결제 번호가 이미 다른 주문에 쓰였다는 오류다.
	ErrPaymentKeyUsed = errors.New("이 결제는 이미 다른 주문에 쓰였습니다")
)

// 받는 글자의 모양. 키와 결제 번호는 DB 와 로그에 그대로 적히므로 글자를 좁게 받는다.
var (
	idempotencyKeyPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{8,128}$`)
	paymentKeyPattern     = regexp.MustCompile(`^[A-Za-z0-9_-]{1,200}$`)
)

// Status 는 주문의 상태다. DB 의 orders.status 에 이 글자가 그대로 적힌다.
type Status string

const (
	StatusPending    Status = "pending"
	StatusConfirming Status = "confirming"
	StatusPaid       Status = "paid"
	StatusFailed     Status = "failed"
)

// Order 는 주문 하나다.
type Order struct {
	ID        uuid.UUID
	UserID    uuid.UUID
	ProductID string
	// Price 는 주문할 때의 값이다. 원(KRW)이다.
	Price int64
	// Credits 는 치르면 들어오는 산 크레딧의 양이다.
	Credits credit.Amount
	Status  Status
	// PaymentKey 는 결제 대행사가 붙인 결제 번호다. pending 일 때는 비어 있다.
	PaymentKey string
	// FailureCode 는 거절된 이유다. failed 일 때만 있다.
	FailureCode string
	CreatedAt   time.Time
	// PaidAt 은 치른 시각이다. paid 일 때만 있다.
	PaidAt *time.Time
}

// Depositor 는 주문으로 산 크레딧을 넣는 것의 모양이다. *wallet.Service 가 이 모양이다.
// 주문이 연 트랜잭션을 넘겨받아 그 안에서 넣는다.
type Depositor interface {
	DepositForOrder(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, orderID uuid.UUID) error
}

// Service 는 주문을 만들고 치른다. 서버가 뜰 때 하나 만들어 쓴다.
type Service struct {
	pool     *pgxpool.Pool
	now      func() time.Time
	provider payment.Provider
	wallet   Depositor
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수다.
func NewService(pool *pgxpool.Pool, now func() time.Time, provider payment.Provider, wallet Depositor) *Service {
	return &Service{pool: pool, now: now, provider: provider, wallet: wallet}
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}
