// billing-server/internal/autocharge/autocharge.go

// Package autocharge 는 자동 충전이다(#980). 정한 때에 등록한 카드로 정한 상품을 산다.
//
// 정한 때는 둘 중 하나를 고른다(Mode). 골드가 정한 값 아래로 떨어질 때(잔액 기준, #980),
// 또는 매달 정한 날(한국 날짜의 1~28일, 날짜 기준, #1167). 날짜 기준은 schedule.go 가 그날 일을 적는다.
//
//   - 카드: 결제 대행사의 카드 등록 창에서 인증한 뒤 서버가 빌링키를 받는다. 사람마다 하나다. 빌링키는 응답과 로그에 싣지 않는다
//   - 설정: 켜고 끄기, 방식, 기준 골드 또는 날, 살 상품, 한 달 상한(원). 상품과 한 달 상한은 두 방식이 함께 쓴다
//   - 켤 수 있는 사람: 카드가 있고 지금 결제할 수 있는 사람(결제 자격). 미성년자는 보호자가 동의했으면 켤 수 있다(2026-11-04 결정)
//   - 동의: 켜는 설정을 적을 때마다 자동 결제 동의(docs/legal/auto-charge.md)의 지금의 판(TermsVersion)에 동의해야 한다.
//     가입 때가 아니라 켤 때 따로 받고, 판과 조건과 시각을 쌓아 적는다(auto_charge_consents, 2026-11-04 결정). 끄는 것은 동의가 필요 없다.
//     판이 오르면 이미 켠 사람도 새 판에 다시 동의할 때까지 결제하지 않는다(SkipTermsOutdated, 2026-11-04 결정)
//
// 이 파일은 규칙만 둔다. DB 와 결제 대행사를 부르지 않는다. 적고 읽는 일은 store.go 가 한다.
package autocharge

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

var (
	// ErrInvalidSettings 는 설정의 값이 틀렸다는 오류다.
	ErrInvalidSettings = errors.New("자동 충전의 설정이 틀렸습니다")
	// ErrNoCard 는 등록한 카드 없이 켜려 했다는 오류다.
	ErrNoCard = errors.New("자동 충전을 켜려면 먼저 카드를 등록해야 합니다")
	// ErrCustomerKeyMismatch 는 카드 등록 창에 쓴 고객 키가 이 사람의 것이 아니라는 오류다.
	ErrCustomerKeyMismatch = errors.New("카드 등록을 처음부터 다시 해 주세요")
	// ErrInvalidAuthKey 는 결제 대행사가 준 인증 키의 모양이 틀렸다는 오류다.
	ErrInvalidAuthKey = errors.New("카드 등록의 인증 키가 틀렸습니다")
	// ErrTermsRequired 는 자동 결제에 동의하지 않고 켜려 했다는 오류다.
	ErrTermsRequired = errors.New("자동 충전을 켜려면 자동 결제에 동의해야 합니다")
	// ErrTermsOutdated 는 옛 판에 동의하고 켜려 했다는 오류다. 화면이 지금의 판을 다시 읽어 보여야 한다.
	ErrTermsOutdated = errors.New("자동 결제 동의의 내용이 바뀌었습니다. 다시 읽고 동의해 주세요")
	// ErrIssuerUnavailable 은 결제 대행사의 답을 받지 못해 카드를 등록했는지 모른다는 오류다. 다시 등록하면 된다.
	ErrIssuerUnavailable = errors.New("결제 대행사가 답하지 않아 카드를 등록하지 못했습니다. 다시 등록해 주세요")
)

// TermsVersion 은 자동 결제 동의(docs/legal/auto-charge.md)의 지금의 판이다.
// 중요한 내용이 바뀌면 올린다(PR). 화면의 문서(web/apps/web/src/legal/documents)도 함께 더한다.
// 올리면 그 뒤로 켜는 설정을 적을 때 새 판에 동의해야 한다. 이미 켠 사람을 멈출지는 판을 올릴 때 정한다.
// 2판(#1167)은 날짜 기준을 더했다.
const TermsVersion = 2

// CheckTerms 는 켜는 설정에 지금의 판에 동의했는지 본다. 끄는 설정은 보지 않는다. agreed 가 0 이면 동의하지 않은 것이다.
func CheckTerms(enabled bool, agreed int) error {
	switch {
	case !enabled:
		return nil
	case agreed == 0:
		return ErrTermsRequired
	case agreed != TermsVersion:
		return ErrTermsOutdated
	default:
		return nil
	}
}

const (
	// MaxThreshold 는 기준 골드의 가장 큰 값이다. 가장 큰 상품보다 넉넉하다.
	MaxThreshold credit.Amount = 100_000
	// MaxMonthlyLimit 는 한 달 상한의 가장 큰 값이다(원). 0 을 몇 개 더 붙인 실수를 막는다.
	MaxMonthlyLimit int64 = 500_000
	// maxAuthKeyLength 는 받는 인증 키의 가장 긴 길이다.
	maxAuthKeyLength = 300
	// MaxChargeDay 는 날짜 기준에서 고를 수 있는 가장 늦은 날이다. 모든 달에 그날이 있게 28일까지다(2026-11-08 결정).
	MaxChargeDay = 28
)

// Mode 는 언제 사는지다. auto_charge_settings.mode 에 그대로 적힌다.
type Mode string

const (
	// ModeBalance 는 골드가 기준(Threshold) 아래로 떨어지면 산다는 것이다(#980).
	ModeBalance Mode = "balance"
	// ModeDate 는 매달 정한 날(ChargeDay, 한국 날짜)에 산다는 것이다(#1167).
	ModeDate Mode = "date"
)

// Settings 는 자동 충전의 설정이다.
type Settings struct {
	Enabled bool
	// Mode 는 언제 사는지다. 잔액 기준이나 날짜 기준이다.
	Mode Mode
	// Threshold 는 골드가 이 값 아래로 떨어지면 산다는 기준이다. 잔액 기준만 쓴다. 날짜 기준이어도 값은 남긴다.
	Threshold credit.Amount
	// ChargeDay 는 날짜 기준에서 사는 날(한국 날짜의 1~28일)이다. 0 이면 고르지 않은 것이다. 잔액 기준이어도 남긴다.
	ChargeDay int
	// ProductID 는 살 상품이다(catalog).
	ProductID string
	// MonthlyLimit 은 한 달(한국 날짜의 달)에 자동으로 결제하는 돈의 상한이다. 원이다.
	MonthlyLimit int64
}

// Validate 는 설정의 값이 맞는지 본다. 상품은 목록에 있어야 하고, 한 달 상한은 그 상품을 한 번은 살 수 있어야 한다.
// 날짜 기준은 날을 골라야 한다(1~28일).
func (s Settings) Validate() error {
	problems := s.timingProblems()
	product, ok := catalog.Find(s.ProductID)
	if !ok {
		problems = append(problems, "모르는 상품입니다")
	}
	if s.Threshold < 0 || s.Threshold > MaxThreshold {
		problems = append(problems, fmt.Sprintf("기준 골드는 0 에서 %s 사이여야 합니다", MaxThreshold))
	}
	if s.MonthlyLimit < 1 || s.MonthlyLimit > MaxMonthlyLimit {
		problems = append(problems, fmt.Sprintf("한 달 상한은 1 에서 %d 원 사이여야 합니다", MaxMonthlyLimit))
	} else if ok && s.MonthlyLimit < product.Price {
		problems = append(problems, "한 달 상한은 고른 상품의 값보다 작을 수 없습니다")
	}
	if len(problems) > 0 {
		return fmt.Errorf("%w: %s", ErrInvalidSettings, strings.Join(problems, ", "))
	}
	return nil
}

// timingProblems 는 방식과 날의 틀린 것이다. 기준 골드는 Validate 가 본다(두 방식 모두 값을 남긴다).
func (s Settings) timingProblems() []string {
	var problems []string
	switch s.Mode {
	case ModeBalance, ModeDate:
	default:
		problems = append(problems, "방식은 balance 나 date 여야 합니다")
	}
	if s.ChargeDay < 0 || s.ChargeDay > MaxChargeDay {
		problems = append(problems, fmt.Sprintf("날은 1 에서 %d 사이여야 합니다", MaxChargeDay))
	} else if s.Mode == ModeDate && s.ChargeDay == 0 {
		problems = append(problems, "날짜 기준은 날을 골라야 합니다")
	}
	return problems
}

// Card 는 화면에 보이는 등록한 카드다. 빌링키는 없다.
type Card struct {
	IssuerCode   string
	Number       string
	RegisteredAt time.Time
}

// View 는 한 사람의 자동 충전이다. 설정을 적은 적이 없으면 Settings 가 nil 이고, 카드가 없으면 Card 가 nil 이다.
type View struct {
	Settings *Settings
	// ConsecutiveFailures 는 이어서 실패한 수다. 다음 단계에서 이 수가 정한 수가 되면 끈다.
	ConsecutiveFailures int
	Card                *Card
	// AgreedTermsVersion 은 마지막으로 동의한 자동 결제 동의의 판이다. 동의한 적이 없으면 0 이다. 지금의 판은 TermsVersion 이다.
	AgreedTermsVersion int
}

// CheckAuthKey 는 결제 대행사가 준 인증 키의 모양을 본다. 비었거나 너무 길면 틀렸다.
func CheckAuthKey(authKey string) error {
	if strings.TrimSpace(authKey) == "" || len(authKey) > maxAuthKeyLength {
		return ErrInvalidAuthKey
	}
	return nil
}
