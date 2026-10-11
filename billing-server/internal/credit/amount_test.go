// billing-server/internal/credit/amount_test.go

package credit_test

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

func TestAmountIsWrittenAsText(t *testing.T) {
	// 지금의 단위(Scale = 0)에서는 정수 그대로다
	if got := credit.Amount(120).String(); got != "120" {
		t.Errorf("String() = %q, 기대 = %q", got, "120")
	}
	if got := credit.Amount(-45).String(); got != "-45" {
		t.Errorf("String() = %q, 기대 = %q", got, "-45")
	}
}

func TestAmountGoesOutAsAJSONString(t *testing.T) {
	// 숫자(120)가 아니라 글자("120")로 나간다. 구조체의 칸이어도, 포인터가 아니어도 같다
	body, err := json.Marshal(struct {
		Paid credit.Amount `json:"paid"`
	}{Paid: 120})
	if err != nil {
		t.Fatalf("JSON 으로 바꾸지 못했다: %v", err)
	}
	if string(body) != `{"paid":"120"}` {
		t.Errorf("JSON = %s, 기대 = %s", body, `{"paid":"120"}`)
	}
}

func TestParseReadsAnAmount(t *testing.T) {
	got, err := credit.Parse("120")
	if err != nil || got != 120 {
		t.Errorf("Parse = %d, %v, 기대 = 120", got, err)
	}
	if _, err := credit.Parse("12.5"); !errors.Is(err, credit.ErrInvalidAmount) {
		t.Errorf("정수 단위에서 소수를 받았다: %v", err)
	}
}
