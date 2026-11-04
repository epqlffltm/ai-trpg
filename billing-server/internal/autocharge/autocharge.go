// billing-server/internal/autocharge/autocharge.go

// Package autocharge 는 자동 충전이다(#980). 골드가 정한 값 아래로 떨어지면 등록한 카드로 정한 상품을 산다.
//
// 이 단계는 카드의 등록과 설정이다. 떨어진 것을 적고 결제하는 일은 다음 단계다(따로 도는 작업이 결제 대행사를 부른다).
//
//   - 카드: 결제 대행사의 카드 등록 창에서 인증한 뒤 서버가 빌링키를 받는다. 사람마다 하나다. 빌링키는 응답과 로그에 싣지 않는다
//   - 설정: 켜고 끄기, 기준 골드, 살 상품, 한 달 상한(원). 잔액 기준만 둔다. 날짜 기준은 나중에 정한다(2026-11-04 결정)
//   - 켤 수 있는 사람: 카드가 있고 지금 결제할 수 있는 사람(결제 자격). 미성년자는 보호자가 동의했으면 켤 수 있다(2026-11-04 결정)
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
	// ErrIssuerUnavailable 은 결제 대행사의 답을 받지 못해 카드를 등록했는지 모른다는 오류다. 다시 등록하면 된다.
	ErrIssuerUnavailable = errors.New("결제 대행사가 답하지 않아 카드를 등록하지 못했습니다. 다시 등록해 주세요")
)

const (
	// MaxThreshold 는 기준 골드의 가장 큰 값이다. 가장 큰 상품보다 넉넉하다.
	MaxThreshold credit.Amount = 100_000
	// MaxMonthlyLimit 는 한 달 상한의 가장 큰 값이다(원). 0 을 몇 개 더 붙인 실수를 막는다.
	MaxMonthlyLimit int64 = 500_000
	// maxAuthKeyLength 는 받는 인증 키의 가장 긴 길이다.
	maxAuthKeyLength = 300
)

// Settings 는 자동 충전의 설정이다.
type Settings struct {
	Enabled bool
	// Threshold 는 골드가 이 값 아래로 떨어지면 산다는 기준이다.
	Threshold credit.Amount
	// ProductID 는 살 상품이다(catalog).
	ProductID string
	// MonthlyLimit 은 한 달(한국 날짜의 달)에 자동으로 결제하는 돈의 상한이다. 원이다.
	MonthlyLimit int64
}

// Validate 는 설정의 값이 맞는지 본다. 상품은 목록에 있어야 하고, 한 달 상한은 그 상품을 한 번은 살 수 있어야 한다.
func (s Settings) Validate() error {
	var problems []string
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
}

// CheckAuthKey 는 결제 대행사가 준 인증 키의 모양을 본다. 비었거나 너무 길면 틀렸다.
func CheckAuthKey(authKey string) error {
	if strings.TrimSpace(authKey) == "" || len(authKey) > maxAuthKeyLength {
		return ErrInvalidAuthKey
	}
	return nil
}
