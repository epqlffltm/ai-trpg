// billing-server/internal/order/order.go

// Package order 는 크레딧을 사는 주문을 만들고, 결제 대행사의 승인을 받아 크레딧을 넣는다.
//
// 주문의 상태는 한 방향으로만 흐른다. 환불이 거절되면 paid 로 돌아가는 것 하나만 예외다.
//
//		pending -> confirming -> paid -> refunding -> refunded
//		   |                  |              -> paid(결제 대행사가 취소를 거절)
//		   |                  -> failed
//		   -> expired
//
//	  - pending: 주문을 만들었다. 아직 결제 대행사를 부르지 않았다.
//	  - expired: 만료 시각(TTL)까지 치르지 않았다. 돈이 오간 적이 없다. 더는 치를 수 없다.
//	  - confirming: 결제 대행사에 승인을 요청했다. 답을 받기 전이거나, 답을 받지 못했다.
//	  - paid: 승인되었다. 크레딧이 들어갔다.
//	  - failed: 거절되었다. 돈이 나가지 않았다.
//	  - refunding: 청약철회. 그 주문의 크레딧을 비웠고 결제 대행사에 취소를 요청했다. 답을 받기 전이거나 받지 못했다.
//	  - refunded: 결제 대행사가 취소했다. 돈이 돌아갔다.
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
)

// ProviderTimeout 은 결제 대행사의 답을 기다리는 가장 긴 시간이다. 넘으면 결과를 모르는 것으로 본다.
const ProviderTimeout = 10 * time.Second

// OperationTimeout 은 결제 작업 하나(승인, 알림, 청약철회, 운영자의 판정)에 주는 가장 긴 시간이다(#273).
// 풀의 연결을 기다리는 것, 행 잠금, 쿼리, 결제 대행사 호출이 모두 이 안에 든다.
// 결제 대행사의 답(ProviderTimeout)에 DB 의 일과 한 번의 재조회가 들어갈 여유를 더했다.
// 지나면 그 자리에서 멈춘다. 상태는 이미 적어 둔 그대로(confirming, refunding) 남고, 다시 보내기와 대사가 결과를 정한다.
const OperationTimeout = 30 * time.Second

// FailureCodeUnspecified 는 결제 대행사가 거절하면서 이유를 주지 않았을 때 적는 글자다.
const FailureCodeUnspecified = "declined"

// RefundWindow 는 청약철회를 받는 기간이다. 치른 시각부터 센다(7×24시간).
const RefundWindow = 7 * 24 * time.Hour

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
	// ErrExpired 는 치르지 않은 채 만료된 주문을 치르려 했다는 오류다.
	ErrExpired = errors.New("주문이 만료되었습니다. 새 주문을 만들어 주세요")
	// ErrInvalidTTL 은 주문의 만료까지의 시간이 0 이하라는 오류다. 서버를 만들 때만 난다.
	ErrInvalidTTL = errors.New("주문의 만료까지의 시간은 0 보다 커야 합니다")
	// ErrNotRefundable 은 청약철회할 수 있는 상태(paid)가 아니라는 오류다.
	ErrNotRefundable = errors.New("치른 주문만 청약철회할 수 있습니다")
	// ErrRefundWindowClosed 는 치른 지 7일이 지났다는 오류다.
	ErrRefundWindowClosed = errors.New("치른 지 7일이 지나 청약철회할 수 없습니다")
	// ErrCreditsUsed 는 그 주문으로 산 크레딧이 일부라도 줄었다는 오류다(쓴 것, 홀드로 묶인 것).
	ErrCreditsUsed = errors.New("이 주문으로 산 크레딧을 이미 써서 청약철회할 수 없습니다")
	// ErrRefundBusy 는 같은 주문의 다른 요청과 엇갈렸다는 오류다. 아주 드물다. 다시 보내면 된다.
	ErrRefundBusy = errors.New("이 주문의 다른 요청을 처리하고 있습니다. 잠시 뒤 다시 보내 주세요")
	// ErrTimedOut 은 결제 작업이 OperationTimeout 안에 끝나지 않았다는 오류다. 원인(DB 나 결제 대행사의 오류)을 함께 감싼다.
	// 결제를 실패로 정한 것이 아니다. 주문은 적어 둔 상태에 남고, 같은 요청을 다시 보내거나 주문을 보면 결과를 안다.
	ErrTimedOut = errors.New("결제 작업이 정한 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 보내거나 주문을 확인해 주세요")
	// ErrRefundRefused 는 결제 대행사가 취소를 거절했다는 오류다. 크레딧은 돌려놓았고 주문은 paid 다.
	// 결제 대행사가 준 이유를 덧붙여 감싼다(errors.Is 로 알아본다).
	ErrRefundRefused = errors.New("결제 대행사가 취소를 거절했습니다")
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
	StatusExpired    Status = "expired"
	StatusRefunding  Status = "refunding"
	StatusRefunded   Status = "refunded"
)

// Order 는 주문 하나다.
type Order struct {
	ID        uuid.UUID
	UserID    uuid.UUID
	ProductID string
	// Channel 은 주문을 치른 길이다(channel.go). 결제 대행사를 부를 때 이것으로 고른다.
	Channel Channel
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
	// UpdatedAt 은 상태가 마지막으로 바뀐 시각이다. confirming·refunding 이면 그 상태가 된 시각이다.
	UpdatedAt time.Time
	// ExpiresAt 은 만료 시각이다. 이때까지 승인을 요청하지 않으면 치를 수 없다.
	ExpiresAt time.Time
	// PaidAt 은 치른 시각이다. paid, refunding, refunded 일 때 있다.
	PaidAt *time.Time
	// RefundableUntil 은 청약철회를 받는 마지막 시각(치른 시각 + RefundWindow)이다. 치르지 않았으면 nil 이다.
	RefundableUntil *time.Time
	// Refundable 은 지금 청약철회할 수 있는지다. paid 이고, 기한 안이고, 그 주문의 크레딧이 하나도 줄지 않았어야 한다.
	// 읽은 순간의 값이다. 실제로 할 수 있는지는 청약철회를 요청할 때 다시 본다.
	Refundable bool
	// RefundedAt 은 환불된 시각이다. refunded 일 때만 있다.
	RefundedAt *time.Time
}

// Depositor 는 주문으로 산 크레딧을 넣는 것의 모양이다.
// 주문이 연 트랜잭션을 넘겨받아 그 안에서 넣는다.
type Depositor interface {
	DepositForOrder(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, orderID uuid.UUID) error
}

// Refunder 는 청약철회로 그 주문의 크레딧을 비우고 되돌리는 것의 모양이다.
// 비우기와 되돌리기는 주문이 연 트랜잭션 안에서 한다.
type Refunder interface {
	// OrderLotFull 은 그 주문의 크레딧이 하나도 줄지 않았는지 본다. 읽기만 한다.
	OrderLotFull(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (bool, error)
	// TakeForRefund 는 그 주문의 크레딧을 비운다. 줄었으면 wallet.ErrLotUsed 다.
	TakeForRefund(ctx context.Context, tx pgx.Tx, userID uuid.UUID, orderID uuid.UUID) error
	// ReturnRefund 는 비운 크레딧을 되돌린다.
	ReturnRefund(ctx context.Context, tx pgx.Tx, userID uuid.UUID, orderID uuid.UUID) error
}

// Wallet 은 주문이 쓰는 지갑의 모양이다. *wallet.Service 가 이 모양이다.
type Wallet interface {
	Depositor
	Refunder
}

// Service 는 주문을 만들고 치른다. 서버가 뜰 때 하나 만들어 쓴다.
type Service struct {
	pool *pgxpool.Pool
	now  func() time.Time
	// providers 는 길마다 부를 결제 대행사다. 고르는 것은 askProvider 다.
	providers Providers
	wallet    Wallet
	// ttl 은 주문을 만든 때부터 만료까지의 시간이다.
	ttl time.Duration
	// operationTimeout 은 결제 작업 하나에 주는 시간이다. 기본은 OperationTimeout 이다.
	operationTimeout time.Duration
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수, providers 는 길마다 부를 결제 대행사(웹은 꼭 있어야 한다),
// ttl 은 주문의 만료까지의 시간이다.
func NewService(pool *pgxpool.Pool, now func() time.Time, providers Providers, wallet Wallet, ttl time.Duration) (*Service, error) {
	if ttl <= 0 {
		return nil, ErrInvalidTTL
	}
	if err := checkProviders(providers); err != nil {
		return nil, err
	}
	return &Service{pool: pool, now: now, providers: providers, wallet: wallet, ttl: ttl, operationTimeout: OperationTimeout}, nil
}

// WithOperationTimeout 은 결제 작업 하나에 주는 시간만 바꾼 Service 를 돌려준다. 테스트가 짧게 줄여 쓴다.
func (s *Service) WithOperationTimeout(limit time.Duration) *Service {
	changed := *s
	changed.operationTimeout = limit
	return &changed
}

// detach 는 결제 작업이 쓸 context 를 만든다. 요청의 취소와는 떨어지고, 작업 전체의 마감은 새로 붙는다.
//
// 떨어지는 까닭: 요청을 보낸 쪽이 중간에 연결을 끊어도 멈추지 않는다. 결제 대행사의 답을 받고도 적지 못하는 일을 줄인다.
// 마감을 붙이는 까닭: context.WithoutCancel 은 취소와 함께 마감까지 지운다. 마감이 없으면 풀이 바닥나거나
// 행 잠금이 풀리지 않을 때 작업이 끝나지 않고 연결과 고루틴을 붙잡는다(#273).
// 이 아래에서 다시 WithoutCancel 을 부르지 않는다. 부르면 이 마감이 지워진다.
func (s *Service) detach(ctx context.Context) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.WithoutCancel(ctx), s.operationTimeout)
}

// timedOut 은 작업의 마감에 걸려 난 오류에 ErrTimedOut 을 함께 감싼다. 아니면 그대로 돌려준다.
func timedOut(ctx context.Context, err error) error {
	if err != nil && errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return errors.Join(ErrTimedOut, err)
	}
	return err
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}
