// billing-server/internal/payment/fake_test.go

package payment_test

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

func TestFakeAnswersByThePaymentKeyPrefix(t *testing.T) {
	approved := payment.Result{Status: payment.StatusApproved}
	declined := payment.Result{Status: payment.StatusDeclined, Code: payment.FakeCodeDeclined}
	cases := []struct {
		name string
		key  string
		// answers 가 false 면 승인 요청에 답이 오지 않는다
		answers bool
		// truth 는 실제 결과다. 조회하면 이것이 나오고, 승인 요청에 답이 올 때도 이것이다
		truth payment.Result
	}{
		{"승인", payment.FakeApproved + "1", true, approved},
		{"거절", payment.FakeDeclined + "1", true, declined},
		{"답이 없지만 승인됨", payment.FakeTimeoutApproved + "1", false, approved},
		{"답이 없고 거절됨", payment.FakeTimeoutDeclined + "1", false, declined},
		{"답이 없고 결제 대행사도 모름", payment.FakeLost + "1", false, payment.Result{Status: payment.StatusPending}},
		{"모르는 앞머리", "pay_123", true, payment.Result{Status: payment.StatusDeclined, Code: payment.FakeCodeUnknownKey}},
		{"빈 번호", "", true, payment.Result{Status: payment.StatusDeclined, Code: payment.FakeCodeUnknownKey}},
		{"대문자는 다른 번호", "FAKE_OK_1", true, payment.Result{Status: payment.StatusDeclined, Code: payment.FakeCodeUnknownKey}},
	}
	fake := payment.Fake{}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			request := payment.Request{PaymentKey: tc.key, OrderID: uuid.New(), Amount: 1000}

			confirmed, confirmErr := fake.Confirm(context.Background(), request)
			looked, lookupErr := fake.Lookup(context.Background(), tc.key)

			if tc.answers && (confirmErr != nil || confirmed != tc.truth) {
				t.Errorf("승인 요청 = %+v, %v. 기대 = %+v", confirmed, confirmErr, tc.truth)
			}
			if !tc.answers && !errors.Is(confirmErr, payment.ErrUnknownOutcome) {
				t.Errorf("승인 요청 = %+v, %v. ErrUnknownOutcome 이어야 한다", confirmed, confirmErr)
			}
			if lookupErr != nil || looked != tc.truth {
				t.Errorf("조회 = %+v, %v. 기대 = %+v", looked, lookupErr, tc.truth)
			}
		})
	}
}

func TestFakeGivesTheSameAnswerEveryTime(t *testing.T) {
	// 기억하는 것이 없다. 같은 번호에는 몇 번을 물어도, 서버를 다시 띄워도 같은 답이다
	key := payment.FakeApproved + uuid.NewString()
	request := payment.Request{PaymentKey: key, OrderID: uuid.New(), Amount: 1000}

	first, _ := payment.Fake{}.Confirm(context.Background(), request)
	second, _ := payment.Fake{}.Confirm(context.Background(), request)

	if first != second || first.Status != payment.StatusApproved {
		t.Errorf("첫 답 = %+v, 둘째 답 = %+v", first, second)
	}
}
