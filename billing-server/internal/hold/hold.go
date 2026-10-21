// billing-server/internal/hold/hold.go

// Package hold 는 값을 치르기 전에 크레딧을 먼저 빼 두고(홀드), 나중에 확정하거나 돌려준다.
//
// 게임 서버가 라운드의 AI 서술을 시작하기 전에 홀드를 건다. 서술이 끝나면 확정하고, 끝내 실패하면 돌려준다.
// 먼저 빼 두는 까닭은 서술이 몇 초에서 몇십 초가 걸리기 때문이다. 끝난 뒤에 빼면 그사이에 크레딧을 다른 데 쓸 수 있고,
// 서술을 이미 만들었는데 받을 크레딧이 없는 일이 생긴다.
//
// 홀드의 상태는 한 방향으로만 흐른다.
//
//	held -> captured (확정했다. 크레딧은 돌아오지 않는다)
//	     -> released (돌려줬다. 부르는 쪽이 돌려 달라고 했거나(requested), 만료되어 정리 작업이 돌려줬거나(expired),
//	                  건 사람이 탈퇴했다(withdrawn))
//
// 홀드에는 만료 시각이 있다(TTL). 그 안에 확정하지 않으면 정리 작업이 돌려준다. 오래 걸리는 쪽은 만료 전에 연장한다.
// 카드의 승인(authorization)이 며칠 뒤 저절로 풀리는 것과 같은 생각이다. 끝이 열린 홀드를 남기지 않는다.
// 만료 시각이 지나도 정리 작업이 돌려주기 전까지는 확정하거나 연장할 수 있다. 시각 하나로 두 쪽이 다투지 않게 한다.
//
// 지키는 것 셋.
//
//  1. 홀드를 만드는 일과 크레딧을 빼는 일은 한 트랜잭션이다. 돌려줄 때도 같다. 하나만 되는 일이 없다.
//  2. 상태는 "지금 held 일 때만" 바꾼다(조건이 붙은 UPDATE). 확정과 반환이 함께 와도 하나만 된다.
//  3. 같은 이름표(reference)로 다시 요청하면 새로 빼지 않고 먼저 건 홀드를 돌려준다.
//     부르는 서버가 응답을 받지 못해 같은 요청을 다시 보내도 크레딧이 두 번 빠지지 않는다.
//
// 값은 부르는 서버가 정하지 않는다. 가격표의 이름(price code)만 받고 값은 가격표(internal/pricing)에서 찾는다.
// 값은 홀드를 거는 순간의 것을 홀드에 적어 둔다. 그 뒤에 가격표가 바뀌어도 이 홀드의 값은 그대로다.
package hold

import (
	"context"
	"errors"
	"regexp"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

var (
	// ErrInvalidReference 는 이름표의 모양이 틀렸다는 오류다.
	ErrInvalidReference = errors.New("이름표는 영문자, 숫자, 점, 밑줄, 쌍점, 붙임표로 된 8자에서 200자여야 합니다")
	// ErrUnknownPrice 는 가격표에 그런 이름이 없다는 오류다. 처음 값이 미래로 예약되어 아직 적용되지 않은 이름도 같다.
	ErrUnknownPrice = errors.New("가격표에 그런 이름이 없습니다")
	// ErrPriceNotForSale 은 판매를 멈춘 이름이라는 오류다. 부르는 서버는 그 모델을 고를 수 없게 하면 된다.
	ErrPriceNotForSale = errors.New("판매를 멈춘 이름입니다")
	// ErrReferenceReused 는 같은 이름표로 다른 내용의 홀드를 걸려 했다는 오류다.
	ErrReferenceReused = errors.New("같은 이름표로 다른 홀드를 걸 수 없습니다")
	// ErrNotFound 는 그런 홀드가 없다는 오류다.
	ErrNotFound = errors.New("그런 홀드가 없습니다")
	// ErrAlreadyCaptured 는 이미 확정한 홀드를 돌려주려 했다는 오류다.
	ErrAlreadyCaptured = errors.New("이미 확정한 홀드입니다")
	// ErrAlreadyReleased 는 이미 돌려준 홀드를 확정하거나 연장하려 했다는 오류다. 만료되어 돌려준 것도 같다.
	ErrAlreadyReleased = errors.New("이미 돌려준 홀드입니다")
	// ErrInvalidTTL 은 홀드의 만료까지의 시간이 0 이하라는 오류다. 서버를 만들 때만 난다.
	ErrInvalidTTL = errors.New("홀드의 만료까지의 시간은 0 보다 커야 합니다")
)

// referencePattern 은 이름표로 받는 모양이다. DB 와 로그에 그대로 적히므로 글자를 좁게 받는다.
// 쌍점을 받는다. 부르는 서버가 "table:<번호>:round:<번호>:user:<번호>" 처럼 지을 수 있다.
var referencePattern = regexp.MustCompile(`^[A-Za-z0-9._:-]{8,200}$`)

// Status 는 홀드의 상태다. DB 의 holds.status 에 이 글자가 그대로 적힌다.
type Status string

const (
	StatusHeld     Status = "held"
	StatusCaptured Status = "captured"
	StatusReleased Status = "released"
)

// ReleaseReason 은 홀드를 돌려준 이유다. DB 의 holds.release_reason 에 이 글자가 그대로 적힌다.
type ReleaseReason string

const (
	// ReleaseRequested 는 부르는 쪽이 돌려 달라고 한 것이다.
	ReleaseRequested ReleaseReason = "requested"
	// ReleaseExpired 는 만료 시각이 지나 정리 작업이 돌려준 것이다.
	ReleaseExpired ReleaseReason = "expired"
	// ReleaseWithdrawn 은 홀드를 건 사람이 탈퇴해 돌려준 것이다(#603, withdraw.go).
	ReleaseWithdrawn ReleaseReason = "withdrawn"
)

// Hold 는 홀드 하나다.
type Hold struct {
	ID     uuid.UUID
	UserID uuid.UUID
	// Reference 는 부르는 서버가 붙인 이름표다.
	Reference string
	// PriceCode 와 Amount 는 걸 때의 가격표 이름과 값이다.
	PriceCode string
	Amount    credit.Amount
	Status    Status
	CreatedAt time.Time
	// ExpiresAt 은 만료 시각이다. 이때까지 확정하거나 연장하지 않으면 정리 작업이 돌려준다.
	ExpiresAt time.Time
	// SettledAt 은 확정하거나 돌려준 시각이다. held 일 때는 nil 이다.
	SettledAt *time.Time
	// ReleaseReason 은 돌려준 이유다. released 일 때만 있다.
	ReleaseReason ReleaseReason
}

// Wallet 은 홀드로 크레딧을 빼고 돌려놓는 것의 모양이다. *wallet.Service 가 이 모양이다.
// 홀드가 연 트랜잭션을 넘겨받아 그 안에서 한다.
type Wallet interface {
	TakeForHold(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, holdID uuid.UUID, funds wallet.Funds) error
	ReturnForHold(ctx context.Context, tx pgx.Tx, userID uuid.UUID, holdID uuid.UUID) error
}

// Prices 는 가격표에서 값을 찾는 것의 모양이다. *pricing.Service 가 이 모양이다.
// 그런 이름이 없거나 판매를 멈췄으면 pricing.ErrUnknownCode 나 pricing.ErrNotForSale 을 돌려준다.
type Prices interface {
	At(ctx context.Context, code string, at time.Time) (pricing.Price, error)
}

// Service 는 홀드를 걸고, 확정하고, 돌려주고, 연장한다. 서버가 뜰 때 하나 만들어 쓴다.
type Service struct {
	pool   *pgxpool.Pool
	now    func() time.Time
	wallet Wallet
	prices Prices
	// ttl 은 홀드를 걸거나 연장한 때부터 만료까지의 시간이다. 서버마다 따로 정한 것(sourceTTLs)이 없으면 이것이다.
	ttl time.Duration
	// sourceTTLs 는 부른 서버마다 따로 정한 만료까지의 시간이다(WithSourceTTL). 처음에는 비어 있다
	sourceTTLs map[string]time.Duration
	// keys 는 홀드를 걸 때의 이름표(중복 방지 키)의 결과를 센다(metrics.go). 처음에는 세지 않는다
	keys metrics.Idempotency
	// shortfalls 는 크레딧이 모자라 걸지 못한 일을 받는다(shortfall.go). 처음에는 없다(nil). 아무에게도 알리지 않는다
	shortfalls Shortfalls
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수, prices 는 가격표, ttl 은 만료까지의 시간이다.
func NewService(pool *pgxpool.Pool, now func() time.Time, wallet Wallet, prices Prices, ttl time.Duration) (*Service, error) {
	if ttl <= 0 {
		return nil, ErrInvalidTTL
	}
	return &Service{
		pool: pool, now: now, wallet: wallet, prices: prices, ttl: ttl, sourceTTLs: map[string]time.Duration{},
		keys: metrics.NoIdempotency(),
	}, nil
}

// WithSourceTTL 은 그 서버(source)가 건 홀드의 만료까지의 시간을 따로 정한다. 걸 때와 연장할 때 쓴다.
// 서버를 만들 때 한 번 부른다(요청과 함께 부르지 않는다). ttl 이 0 이하면 ErrInvalidTTL 이다.
//
// 까닭: chat 의 말 한 번은 몇 초면 끝난다. 홀드를 건 chat 서버가 죽으면 그 크레딧이 HOLD_TTL(하루) 동안 묶인다.
// 짧게 두면 정리 작업이 곧 돌려준다. 게임 서버의 라운드는 길게 열려 있어 HOLD_TTL 그대로다.
func (s *Service) WithSourceTTL(source string, ttl time.Duration) error {
	if ttl <= 0 {
		return ErrInvalidTTL
	}
	s.sourceTTLs[source] = ttl
	return nil
}

// ttlFor 는 그 서버가 건 홀드의 만료까지의 시간이다. 따로 정한 것이 없으면 기본(ttl)이다.
func (s *Service) ttlFor(source string) time.Duration {
	if ttl, ok := s.sourceTTLs[source]; ok {
		return ttl
	}
	return s.ttl
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}

// toHold 는 DB 의 줄을 이 패키지의 모양으로 바꾼다.
func toHold(row holddb.Hold) Hold {
	held := Hold{
		ID:        row.ID,
		UserID:    row.UserID,
		Reference: row.Reference,
		PriceCode: row.PriceCode,
		Amount:    row.Amount,
		Status:    Status(row.Status),
		CreatedAt: row.CreatedAt,
		ExpiresAt: row.ExpiresAt,
	}
	if row.SettledAt.Valid {
		held.SettledAt = &row.SettledAt.Time
	}
	if row.ReleaseReason.Valid {
		held.ReleaseReason = ReleaseReason(row.ReleaseReason.String)
	}
	return held
}
