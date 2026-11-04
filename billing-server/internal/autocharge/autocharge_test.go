// billing-server/internal/autocharge/autocharge_test.go
// 자동 충전의 규칙(설정의 값, 인증 키의 모양)을 DB 없이 본다.
package autocharge_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
)

func validSettings() autocharge.Settings {
	return autocharge.Settings{Enabled: true, Threshold: 500, ProductID: "credits-5000", MonthlyLimit: 30_000}
}

func TestValidSettingsPass(t *testing.T) {
	for name, settings := range map[string]autocharge.Settings{
		"보통":               validSettings(),
		"기준 0(다 써야 산다)":    {ProductID: "credits-1000", MonthlyLimit: 1_000},
		"가장 큰 값들":          {Threshold: autocharge.MaxThreshold, ProductID: "credits-30000", MonthlyLimit: autocharge.MaxMonthlyLimit},
		"한 달 상한이 상품 값과 같다": {Threshold: 1, ProductID: "credits-10000", MonthlyLimit: 10_000},
	} {
		if err := settings.Validate(); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
}

func TestBadSettingsAreRefused(t *testing.T) {
	change := func(edit func(*autocharge.Settings)) autocharge.Settings {
		settings := validSettings()
		edit(&settings)
		return settings
	}
	for name, settings := range map[string]autocharge.Settings{
		"모르는 상품":          change(func(s *autocharge.Settings) { s.ProductID = "credits-7" }),
		"음수 기준":           change(func(s *autocharge.Settings) { s.Threshold = -1 }),
		"너무 큰 기준":         change(func(s *autocharge.Settings) { s.Threshold = autocharge.MaxThreshold + 1 }),
		"상한 0":            change(func(s *autocharge.Settings) { s.MonthlyLimit = 0 }),
		"너무 큰 상한":         change(func(s *autocharge.Settings) { s.MonthlyLimit = autocharge.MaxMonthlyLimit + 1 }),
		"상한이 상품 한 번보다 작다": change(func(s *autocharge.Settings) { s.MonthlyLimit = 4_999 }),
	} {
		if err := settings.Validate(); !errors.Is(err, autocharge.ErrInvalidSettings) {
			t.Errorf("%s: 오류 = %v", name, err)
		}
	}
}

func TestAuthKeyShape(t *testing.T) {
	if err := autocharge.CheckAuthKey("bln_abcd1234"); err != nil {
		t.Errorf("맞는 키를 거절했다: %v", err)
	}
	for name, key := range map[string]string{"비었다": "", "빈칸뿐": "   ", "너무 길다": strings.Repeat("a", 301)} {
		if err := autocharge.CheckAuthKey(key); !errors.Is(err, autocharge.ErrInvalidAuthKey) {
			t.Errorf("%s: 오류 = %v", name, err)
		}
	}
}

func TestTurningOnNeedsTheCurrentTermsButTurningOffDoesNot(t *testing.T) {
	for name, tc := range map[string]struct {
		enabled bool
		agreed  int
		want    error
	}{
		"끄기는 동의가 필요 없다":   {false, 0, nil},
		"켜기는 지금의 판":       {true, autocharge.TermsVersion, nil},
		"켜는데 동의하지 않았다":    {true, 0, autocharge.ErrTermsRequired},
		"켜는데 틀린 판을 보냈다":   {true, -1, autocharge.ErrTermsOutdated},
		"켜는데 모르는 판에 동의했다": {true, autocharge.TermsVersion + 1, autocharge.ErrTermsOutdated},
	} {
		if got := autocharge.CheckTerms(tc.enabled, tc.agreed); !errors.Is(got, tc.want) || (tc.want == nil && got != nil) {
			t.Errorf("%s: %v, 기대 = %v", name, got, tc.want)
		}
	}
}
