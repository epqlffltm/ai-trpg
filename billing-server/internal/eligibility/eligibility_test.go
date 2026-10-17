// billing-server/internal/eligibility/eligibility_test.go

package eligibility_test

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
)

func day(year int, month time.Month, d int) time.Time {
	return time.Date(year, month, d, 0, 0, 0, 0, time.UTC)
}

func TestDecide(t *testing.T) {
	adultDay := day(2027, 3, 15)
	today := day(2026, 10, 18)
	cases := []struct {
		name   string
		record *eligibility.Record
		today  time.Time
		want   error
	}{
		{"본인인증 전", nil, today, eligibility.ErrVerificationRequired},
		{"이미 성년", &eligibility.Record{}, today, nil},
		{"미성년자, 동의 없음", &eligibility.Record{LegalAdultFrom: &adultDay}, today, eligibility.ErrGuardianConsentRequired},
		{"미성년자, 동의함", &eligibility.Record{LegalAdultFrom: &adultDay, GuardianConsent: true}, today, nil},
		{"성년이 되기 전날", &eligibility.Record{LegalAdultFrom: &adultDay}, adultDay.AddDate(0, 0, -1), eligibility.ErrGuardianConsentRequired},
		// 다시 인증하지 않아도 그날부터 결제할 수 있다
		{"성년이 되는 날", &eligibility.Record{LegalAdultFrom: &adultDay}, adultDay, nil},
	}
	for _, tc := range cases {
		if got := eligibility.Decide(tc.record, tc.today); !errors.Is(got, tc.want) || (tc.want == nil && got != nil) {
			t.Errorf("%s: %v, 기대 = %v", tc.name, got, tc.want)
		}
	}
}

func TestKoreanDateTurnsAtKoreanMidnight(t *testing.T) {
	// UTC 15시가 한국 자정이다. 서버의 날짜(UTC)로 자르면 아침 9시까지 하루가 늦다
	before := eligibility.KoreanDate(time.Date(2026, 12, 31, 14, 59, 59, 0, time.UTC))
	after := eligibility.KoreanDate(time.Date(2026, 12, 31, 15, 0, 0, 0, time.UTC))

	if !before.Equal(day(2026, 12, 31)) || !after.Equal(day(2027, 1, 1)) {
		t.Errorf("전 = %v, 뒤 = %v", before, after)
	}
}
