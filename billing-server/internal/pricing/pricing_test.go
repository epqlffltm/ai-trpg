// billing-server/internal/pricing/pricing_test.go

package pricing_test

import (
	"regexp"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

func TestNarrationCostsFiftyCredits(t *testing.T) {
	price, ok := pricing.Find(pricing.NarrationStandard)

	if !ok || price.Code != "narration.standard" || price.Credits != 50 {
		t.Errorf("서술의 값 = %+v, 찾음 = %v", price, ok)
	}
}

func TestUnknownCodesAreNotFound(t *testing.T) {
	for _, code := range []string{"", "narration", "narration.standard ", "NARRATION.STANDARD", "narration.free"} {
		if price, ok := pricing.Find(code); ok {
			t.Errorf("%q 의 값을 찾았다: %+v", code, price)
		}
	}
}

func TestEveryPriceIsUsable(t *testing.T) {
	// 이름은 "<무엇>.<등급>" 이고, 겹치지 않고, 값은 0 보다 크다. 값이 0 이면 홀드를 걸 수 없다(DB 가 거절한다)
	shape := regexp.MustCompile(`^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$`)
	seen := map[string]bool{}
	for _, price := range pricing.All() {
		if !shape.MatchString(price.Code) || seen[price.Code] || price.Credits <= 0 {
			t.Errorf("쓸 수 없는 줄이다: %+v", price)
		}
		seen[price.Code] = true
	}
	if len(seen) == 0 {
		t.Error("가격표가 비었다")
	}
}

func TestTheReturnedListIsACopy(t *testing.T) {
	prices := pricing.All()
	prices[0].Credits = 1

	if price, _ := pricing.Find(prices[0].Code); price.Credits == 1 {
		t.Error("돌려받은 목록을 고쳤더니 가격표가 바뀌었다")
	}
}
