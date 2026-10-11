// billing-server/internal/wallet/wallet.go

// Package wallet 은 사용자의 크레딧을 넣고, 쓰고, 읽는다.
//
// 크레딧은 두 종류다.
//   - 산 크레딧(paid): 사라지지 않는다. 잔액을 지갑(wallets)의 한 칸에 들고 있다.
//   - 무료 크레딧(free): 지급된 뒤 정해진 시간이 지나면 사라진다. 지급할 때마다 사라지는 시각이 달라서,
//     지급 하나를 한 줄(free_grants)로 두고 줄마다 남은 양을 적는다.
//
// 크레딧이 바뀔 때마다 원장(ledger_entries)에 줄을 덧붙인다. 지금의 값과 원장은 같은 트랜잭션에서 함께 바뀐다.
// 그래서 "산 크레딧의 잔액 = 원장의 paid 줄의 합"이고 "지급 묶음의 남은 양 = 그 묶음의 원장 줄의 합"이다.
//
// 한 사용자의 크레딧을 바꾸는 일은 모두 그 사용자의 지갑 줄을 먼저 잠근다. 같은 사용자의 변경은 한 줄로 선다.
// 두 요청이 한꺼번에 잔액보다 많이 쓰려 해도 뒤의 것은 앞의 것이 끝난 뒤의 잔액을 본다.
//
// 이 패키지는 누가 부르는지 따지지 않는다. 받은 사용자 번호를 그대로 믿는다. 누구의 지갑인지는 부르는 쪽이 정한다.
package wallet

import (
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// MaxAmount 는 한 번에 넣거나 쓸 수 있는 가장 큰 양이다.
// 실수로 들어온 터무니없는 값을 막고, 양을 더할 때 int64 를 넘지 않게 한다.
const MaxAmount credit.Amount = 1_000_000_000_000

var (
	// ErrInvalidAmount 는 양이 0 이하이거나 MaxAmount 보다 크다는 오류다.
	ErrInvalidAmount = errors.New("크레딧의 양은 1 이상이어야 하고 한 번에 다룰 수 있는 양을 넘을 수 없습니다")
	// ErrInsufficient 는 쓰려는 양이 가진 것보다 많다는 오류다. 이 오류가 나면 아무것도 바뀌지 않는다.
	ErrInsufficient = errors.New("크레딧이 모자랍니다")
)

// Kind 는 크레딧의 종류다. DB 의 ledger_entries.kind 에 이 글자가 그대로 적힌다.
type Kind string

const (
	// KindPaid 는 산 크레딧이다.
	KindPaid Kind = "paid"
	// KindFree 는 무료 크레딧이다.
	KindFree Kind = "free"
)

// Reason 은 크레딧이 바뀐 이유다. DB 의 ledger_entries.reason 에 이 글자가 그대로 적힌다.
// 값을 더하려면 마이그레이션으로 DB 의 CHECK 도 함께 고친다.
type Reason string

const (
	// ReasonDeposit 은 산 크레딧이 들어왔다는 뜻이다.
	ReasonDeposit Reason = "deposit"
	// ReasonGrant 는 무료 크레딧이 지급되었다는 뜻이다.
	ReasonGrant Reason = "grant"
	// ReasonSpend 는 크레딧을 썼다는 뜻이다.
	ReasonSpend Reason = "spend"
	// ReasonExpire 는 무료 크레딧이 기한이 지나 사라졌다는 뜻이다.
	ReasonExpire Reason = "expire"
)

// Policy 는 크레딧을 다루는 규칙 가운데 설정으로 바꿀 수 있는 것들이다.
type Policy struct {
	// FreeFirst 가 true 면 무료 크레딧부터 쓰고, false 면 산 크레딧부터 쓴다.
	// 무료 크레딧끼리는 설정과 상관없이 먼저 사라지는 것부터 쓴다.
	FreeFirst bool
	// FreeTTL 은 무료 크레딧이 지급된 뒤 사라질 때까지의 시간이다.
	FreeTTL time.Duration
}

// Balance 는 지금 쓸 수 있는 크레딧이다.
type Balance struct {
	// Paid 는 산 크레딧이다.
	Paid credit.Amount
	// Free 는 아직 사라지지 않은 무료 크레딧이다.
	Free credit.Amount
}

// Total 은 산 크레딧과 무료 크레딧을 더한 양이다.
func (b Balance) Total() credit.Amount {
	return b.Paid + b.Free
}

// Entry 는 원장의 한 줄이다.
type Entry struct {
	// ID 는 줄의 번호다. 나중에 적힌 줄이 더 크다.
	ID int64
	// OperationID 는 한 번의 변경이 남긴 줄들을 묶는다.
	OperationID uuid.UUID
	Kind        Kind
	Reason      Reason
	// Amount 는 늘었으면 양수, 줄었으면 음수다.
	Amount    credit.Amount
	CreatedAt time.Time
}

// Service 는 크레딧을 넣고, 쓰고, 읽는다. 서버가 뜰 때 하나 만들어 쓴다.
type Service struct {
	pool   *pgxpool.Pool
	now    func() time.Time
	policy Policy
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수다.
// 실제 서버는 time.Now 를 넘기고, 테스트는 마음대로 돌릴 수 있는 시계를 넘긴다.
func NewService(pool *pgxpool.Pool, now func() time.Time, policy Policy) *Service {
	return &Service{pool: pool, now: now, policy: policy}
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
// 그보다 잘게 쪼갠 부분을 드라이버가 버릴지 반올림할지에 기대지 않는다. Go 가 가진 시각과 DB 에 적힌 시각이 같아야
// 사라지는 시각의 경계에서 두 쪽의 답이 같다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}

// checkAmount 는 넣거나 쓰려는 양이 받을 수 있는 범위인지 본다.
func checkAmount(amount credit.Amount) error {
	if amount <= 0 || amount > MaxAmount {
		return ErrInvalidAmount
	}
	return nil
}
