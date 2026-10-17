// billing-server/internal/pricing/pricing.go

// Package pricing 은 크레딧을 받는 일의 가격표다. 무엇에 몇 크레딧을 받는지를 정한다.
//
// 부르는 서버(게임 서버)는 금액을 보내지 않는다. "무엇을"(이름)만 말하고 값은 여기서 찾는다.
// 값이 한 곳에 있고, 부르는 서버의 버그가 틀린 금액이 되지 않는다.
//
// 가격표는 DB 에 있고 덧붙이기만 한다(migrations/00006_prices.sql). 값을 바꾸면 새 줄을 더하고 옛 줄은 그대로 둔다.
// 판매를 멈출 때도 지우지 않고 "값 없음" 줄을 더한다. 그래서 "그때 왜 그 값을 받았나"를 나중에도 답할 수 있다.
// Stripe 의 Price 가 금액을 고칠 수 없고 새 가격을 만들어 옛 것을 보관하는 것과 같은 생각이다.
//
// 홀드는 걸 때의 값을 스스로 적어 둔다. 값을 바꿔도 이미 건 홀드는 바뀌지 않는다.
//
// 이름마다 등급(Tier)이 있다(#338). 스탠다드는 골드(산 크레딧)와 실버(무료 크레딧) 모두로 내고, 프리미엄은 골드로만 낸다.
// 등급도 값과 같은 줄에 적어 덧붙이기만 한다. 결제에 쓰는 등급은 이 가격표가 기준이다.
package pricing

import (
	"errors"
	"regexp"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

const (
	// NarrationStandard 는 라운드의 AI 서술 한 번의 기본 이름이다. 마이그레이션이 처음 값(50)을 넣는다.
	NarrationStandard = "narration.standard"
	// MaxCredits 는 한 번에 받는 가장 큰 값이다. 0 을 몇 개 더 붙인 실수를 막는다. DB 의 CHECK 와 같은 값이다.
	MaxCredits credit.Amount = 1_000_000
	// maxCodeLength 는 이름의 가장 긴 길이다. DB 의 CHECK 와 같은 값이다.
	maxCodeLength = 64
	// maxNoteLength 는 바꾼 이유와 바꾼 사람의 가장 긴 길이다.
	maxNoteLength = 200
)

// codePattern 은 이름으로 받는 모양이다. 점으로 나눈 소문자 이름이다(narration.gemma4-26b). DB 의 CHECK 와 같다.
var codePattern = regexp.MustCompile(`^[a-z][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$`)

var (
	// ErrUnknownCode 는 가격표에 그런 이름이 없다는 오류다.
	ErrUnknownCode = errors.New("가격표에 그런 이름이 없습니다")
	// ErrNotForSale 은 판매를 멈춘 이름이라는 오류다.
	ErrNotForSale = errors.New("판매를 멈춘 이름입니다")
	// ErrInvalidCode 는 이름의 모양이 틀렸다는 오류다.
	ErrInvalidCode = errors.New("이름은 점으로 나눈 소문자, 숫자, 밑줄, 붙임표로 된 64자 이하여야 합니다(narration.standard 처럼)")
	// ErrInvalidCredits 는 값이 받는 범위 밖이라는 오류다.
	ErrInvalidCredits = errors.New("값은 1 부터 1000000 까지여야 합니다")
	// ErrMissingNote 는 바꾼 이유나 바꾼 사람이 비었거나 너무 길다는 오류다.
	ErrMissingNote = errors.New("바꾼 이유와 바꾼 사람은 비울 수 없고 200자 이하여야 합니다")
	// ErrPastEffective 는 적용 시각이 지금보다 앞선다는 오류다. 이미 지난 시각의 값을 바꾸면 그때 받은 값의 기록이 틀어진다.
	ErrPastEffective = errors.New("적용 시각은 지금보다 앞설 수 없습니다")
	// ErrSameMoment 는 같은 이름에 같은 적용 시각의 줄이 이미 있다는 오류다.
	ErrSameMoment = errors.New("같은 이름에 같은 적용 시각의 값이 이미 있습니다")
	// ErrInvalidTier 는 등급이 standard, premium 가운데 하나가 아니라는 오류다.
	ErrInvalidTier = errors.New("등급은 standard 나 premium 이어야 합니다")
	// ErrMissingTier 는 처음 파는 이름에 등급을 적지 않았다는 오류다. 이미 파는 이름은 적지 않으면 그때의 등급을 그대로 쓴다.
	// 처음 파는 이름에 기본값을 두지 않는다. 프리미엄 모델이 등급을 빠뜨려 실버로 팔리면 그만큼 손해다.
	ErrMissingTier = errors.New("처음 파는 이름은 등급(standard, premium)을 정해야 합니다")
)

// Tier 는 가격표 이름의 등급이다. DB 의 price_versions.tier 에 이 글자가 그대로 적힌다.
type Tier string

const (
	// TierStandard 는 골드와 실버 모두로 내는 등급이다.
	TierStandard Tier = "standard"
	// TierPremium 은 골드로만 내는 등급이다.
	TierPremium Tier = "premium"
)

// Valid 는 아는 등급인지다.
func (t Tier) Valid() bool {
	return t == TierStandard || t == TierPremium
}

// PaidOnly 는 골드(산 크레딧)로만 내야 하는지다.
func (t Tier) PaidOnly() bool {
	return t == TierPremium
}

// Price 는 지금 받는 값이다.
type Price struct {
	Code    string
	Credits credit.Amount
	Tier    Tier
	// Since 는 이 값이 적용되기 시작한 시각이다.
	Since time.Time
}

// Version 은 가격표의 줄 하나다.
type Version struct {
	ID   int64
	Code string
	// Credits 는 값이다. OnSale 이 false 면(판매를 멈춘 줄) 0 이다.
	Credits     credit.Amount
	OnSale      bool
	Tier        Tier
	EffectiveAt time.Time
	Reason      string
	ChangedBy   string
	CreatedAt   time.Time
}

// Change 는 가격표에 더할 줄이다.
type Change struct {
	Code string
	// Credits 는 새 값이다. 판매를 멈출 때(Stop)는 읽지 않는다.
	Credits credit.Amount
	// Tier 는 등급이다. 비워 두면 적용 시각에 그 이름의 등급을 그대로 쓴다. 처음 파는 이름이면 비울 수 없다.
	Tier Tier
	// EffectiveAt 은 적용을 시작할 시각이다. 비워 두면(zero) 지금이다. 지금보다 앞설 수 없다.
	EffectiveAt time.Time
	// Reason 과 ChangedBy 는 왜, 누가 바꿨는지다. 둘 다 비울 수 없다.
	Reason    string
	ChangedBy string
}

// Service 는 가격표를 읽고 덧붙인다.
type Service struct {
	pool *pgxpool.Pool
	now  func() time.Time
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수다.
func NewService(pool *pgxpool.Pool, now func() time.Time) *Service {
	return &Service{pool: pool, now: now}
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}
