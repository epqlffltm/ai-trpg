// billing-server/internal/coupon/coupon.go

// Package coupon 은 쿠폰이다(#979). 운영자가 코드를 만들고(cmd/coupons), 사용자가 코드를 넣으면 실버(무료 크레딧)를 받는다.
//
//   - 한 코드를 여럿이 쓴다(공용 코드). 한 사람은 한 쿠폰을 한 번만 받는다. 전체 사용 한도를 둘 수 있다(1 이면 한 사람용)
//   - 실버만 준다. 골드는 환불과 청약철회의 계산에 들어가서 주지 않는다(2026-11-03 결정)
//   - 본인인증을 마친 사람만 받는다. 한 사람이 계정을 여럿 만들어 같은 쿠폰을 여러 번 받는 것을 막는다(출석과 같다)
//   - 틀린 코드를 마구 넣어 보는 것을 사람마다 막는다(한 시간에 MaxFailures 번). IP 마다는 프록시가 막는다
//
// 이 파일은 규칙만 둔다. DB 를 보지 않는다. 적고 읽는 일은 store.go 가 한다.
package coupon

import (
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

var (
	// ErrNotFound 는 그런 코드의 쿠폰이 없다는 오류다. 모양이 틀린 코드도 같다. 틀린 시도로 센다.
	ErrNotFound = errors.New("그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요")
	// ErrNotStarted 는 아직 쓸 수 있는 때가 오지 않은 쿠폰이라는 오류다.
	ErrNotStarted = errors.New("아직 쓸 수 없는 쿠폰입니다")
	// ErrEnded 는 쓸 수 있는 때가 지난 쿠폰이라는 오류다.
	ErrEnded = errors.New("기간이 지난 쿠폰입니다")
	// ErrStopped 는 운영자가 멈춘 쿠폰이라는 오류다.
	ErrStopped = errors.New("더는 쓸 수 없는 쿠폰입니다")
	// ErrExhausted 는 받을 수 있는 사람의 수가 다 찬 쿠폰이라는 오류다.
	ErrExhausted = errors.New("모두 받아 간 쿠폰입니다")
	// ErrAlreadyRedeemed 는 그 사람이 이미 받은 쿠폰이라는 오류다. 이 오류가 나면 아무것도 바뀌지 않는다.
	ErrAlreadyRedeemed = errors.New("이미 받은 쿠폰입니다")
	// ErrVerificationRequired 는 본인인증을 하지 않아 받을 수 없다는 오류다.
	ErrVerificationRequired = errors.New("쿠폰을 받으려면 먼저 본인인증을 해야 합니다")
	// ErrInvalidSpec 은 운영자가 만들려는 쿠폰의 값이 틀렸다는 오류다.
	ErrInvalidSpec = errors.New("쿠폰의 값이 틀렸습니다")
	// ErrCodeTaken 은 같은 코드의 쿠폰이 이미 있다는 오류다.
	ErrCodeTaken = errors.New("같은 코드의 쿠폰이 이미 있습니다")
)

// TooManyAttemptsError 는 틀린 코드를 너무 자주 넣었다는 오류다. RetryAfter 뒤에 다시 넣을 수 있다.
type TooManyAttemptsError struct {
	RetryAfter time.Duration
}

func (e *TooManyAttemptsError) Error() string {
	return "쿠폰 코드를 너무 자주 틀렸습니다. 잠시 뒤에 다시 넣어 주세요"
}

const (
	// MaxSilver 는 쿠폰 하나로 받는 가장 큰 실버다. 0 을 몇 개 더 붙인 실수를 막는다.
	MaxSilver credit.Amount = 100_000
	// MaxSilverDays 는 받은 실버가 사라질 때까지의 가장 긴 날 수다.
	MaxSilverDays = 365
	// MaxReasonLength 는 만든 까닭의 가장 긴 글자 수다.
	MaxReasonLength = 200
	// MaxFailures 는 한 사람이 한 창(FailureWindow)에 틀릴 수 있는 수다. 이만큼 틀리면 창이 끝날 때까지 받지 않는다.
	MaxFailures = 10
	// FailureWindow 는 틀린 수를 세는 창의 길이다.
	FailureWindow = time.Hour
)

// codePattern 은 코드의 모양이다. DB 의 제약(coupons_code_shape)과 같다.
var codePattern = regexp.MustCompile(`^[A-Z0-9-]{4,32}$`)

// NormalizeCode 는 사용자가 넣은 글을 찾을 코드로 바꾼다. 앞뒤 빈칸을 지우고 대문자로 바꾼다.
// 모양이 틀리면 false 다(그런 쿠폰은 없다).
func NormalizeCode(input string) (string, bool) {
	code := strings.ToUpper(strings.TrimSpace(input))
	return code, codePattern.MatchString(code)
}

// GrantKey 는 쿠폰의 실버에 붙이는 지급의 이름이다. 지갑이 한 사용자에게 같은 이름을 두 번 주지 않는다.
// 받은 기록의 기본 키(쿠폰, 사용자)와 함께 두 번 받는 것을 두 겹으로 막는다. 코드가 아니라 번호로 짓는다(코드는 대문자다).
func GrantKey(id int64) string { return "coupon-" + strconv.FormatInt(id, 10) }

// Coupon 은 쿠폰 하나다.
type Coupon struct {
	ID     int64
	Code   string
	Silver credit.Amount
	// SilverDays 는 받은 실버가 사라질 때까지의 날 수다. 0 이면 다른 무료 크레딧과 같다.
	SilverDays int
	StartsAt   time.Time
	EndsAt     time.Time
	// MaxRedemptions 는 받을 수 있는 사람의 수다. 0 이면 한도가 없다.
	MaxRedemptions int
	Redemptions    int
	// StoppedAt 은 운영자가 멈춘 시각이다. 멈추지 않았으면 nil 이다.
	StoppedAt *time.Time
	CreatedBy string
	Reason    string
	CreatedAt time.Time
}

// TTL 은 받은 실버가 사라질 때까지의 시간이다. 0 이면 지갑의 기본값이다.
func (c Coupon) TTL() time.Duration {
	return time.Duration(c.SilverDays) * 24 * time.Hour
}

// Availability 는 지금 이 쿠폰을 받을 수 있는지다. 받을 수 있으면 nil 이다. 그 사람이 이미 받았는지는 보지 않는다.
func Availability(c Coupon, now time.Time) error {
	switch {
	case c.StoppedAt != nil:
		return ErrStopped
	case now.Before(c.StartsAt):
		return ErrNotStarted
	case !now.Before(c.EndsAt):
		return ErrEnded
	case c.MaxRedemptions > 0 && c.Redemptions >= c.MaxRedemptions:
		return ErrExhausted
	}
	return nil
}

// Spec 은 운영자가 만드는 쿠폰의 값이다.
type Spec struct {
	Code           string
	Silver         credit.Amount
	SilverDays     int
	StartsAt       time.Time
	EndsAt         time.Time
	MaxRedemptions int
	CreatedBy      string
	Reason         string
}

// Validate 는 만들려는 쿠폰의 값이 맞는지 본다. 코드는 NormalizeCode 를 거친 것이어야 한다.
func (s Spec) Validate() error {
	var problems []string
	if !codePattern.MatchString(s.Code) {
		problems = append(problems, "코드는 영문 대문자, 숫자, 붙임표로 된 4자에서 32자여야 합니다")
	}
	if s.Silver < 1 || s.Silver > MaxSilver {
		problems = append(problems, fmt.Sprintf("실버는 1 에서 %s 사이여야 합니다", MaxSilver))
	}
	if s.SilverDays < 0 || s.SilverDays > MaxSilverDays {
		problems = append(problems, fmt.Sprintf("실버의 기한은 0(기본값) 또는 1 에서 %d 일이어야 합니다", MaxSilverDays))
	}
	if !s.EndsAt.After(s.StartsAt) {
		problems = append(problems, "끝나는 때가 시작하는 때보다 뒤여야 합니다")
	}
	if s.MaxRedemptions < 0 {
		problems = append(problems, "받을 수 있는 사람의 수는 0(한도 없음) 이상이어야 합니다")
	}
	if strings.TrimSpace(s.CreatedBy) == "" {
		problems = append(problems, "만든 사람을 적어야 합니다")
	}
	if strings.TrimSpace(s.Reason) == "" || len([]rune(s.Reason)) > MaxReasonLength {
		problems = append(problems, fmt.Sprintf("까닭은 1 자에서 %d 자여야 합니다", MaxReasonLength))
	}
	if len(problems) > 0 {
		return fmt.Errorf("%w: %s", ErrInvalidSpec, strings.Join(problems, ", "))
	}
	return nil
}

// Attempts 는 한 사람의 지금 창의 틀린 수다.
type Attempts struct {
	WindowStartedAt time.Time
	Failures        int
}

// Blocked 는 지금 넣어 볼 수 없는지와 얼마 뒤에 다시 넣을 수 있는지다. attempts 가 nil 이면 틀린 적이 없다.
// 창이 끝났으면 막지 않는다(다음에 틀리면 새 창을 연다).
func Blocked(attempts *Attempts, now time.Time) (bool, time.Duration) {
	if attempts == nil || attempts.Failures < MaxFailures {
		return false, 0
	}
	ends := attempts.WindowStartedAt.Add(FailureWindow)
	if !now.Before(ends) {
		return false, 0
	}
	return true, ends.Sub(now)
}

// Redemption 은 받은 쿠폰이다.
type Redemption struct {
	Code      string
	Silver    credit.Amount
	ExpiresAt time.Time
}
