// billing-server/internal/wallet/source_test.go

// 받은 줄이 어디서 왔는지(지급 묶음의 이름의 앞부분)를 DB 없이 본다(#979).
package wallet_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestSourceOfAGrantComesFromItsKey(t *testing.T) {
	cases := []struct {
		reason wallet.Reason
		key    string
		want   wallet.GrantSource
	}{
		{wallet.ReasonGrant, "welcome", wallet.SourceWelcome},
		{wallet.ReasonGrant, "attendance-20261103", wallet.SourceAttendance},
		{wallet.ReasonGrant, "chest-20261103", wallet.SourceChest},
		{wallet.ReasonGrant, "event-launch-2026", wallet.SourceEvent},
		{wallet.ReasonGrant, "coupon-42", wallet.SourceCoupon},
		{wallet.ReasonGrant, "", wallet.SourceOther},
		{wallet.ReasonGrant, "welcomeback", wallet.SourceOther},
		{wallet.ReasonSpend, "coupon-42", ""},
		{wallet.ReasonExpire, "welcome", ""},
	}
	for _, tc := range cases {
		if got := wallet.SourceOf(tc.reason, tc.key); got != tc.want {
			t.Errorf("SourceOf(%s, %q) = %q, %q 여야 한다", tc.reason, tc.key, got, tc.want)
		}
	}
}
