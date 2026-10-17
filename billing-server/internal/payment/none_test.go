// billing-server/internal/payment/none_test.go

package payment_test

import (
	"context"
	"errors"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

func TestNoneRefusesEveryCall(t *testing.T) {
	// 가짜처럼 답하면 잘못 불렸을 때 원장이 바뀐다. 무엇을 불러도 오류다
	ctx := context.Background()
	request := payment.Request{PaymentKey: payment.FakeApproved + "1"}
	calls := map[string]func() (payment.Result, error){
		"Confirm": func() (payment.Result, error) { return payment.None{}.Confirm(ctx, request) },
		"Cancel":  func() (payment.Result, error) { return payment.None{}.Cancel(ctx, request) },
		"Lookup":  func() (payment.Result, error) { return payment.None{}.Lookup(ctx, request) },
	}
	for name, call := range calls {
		result, err := call()
		if !errors.Is(err, payment.ErrNoProvider) || result != (payment.Result{}) {
			t.Errorf("%s = %+v, %v. ErrNoProvider 여야 한다", name, result, err)
		}
		if errors.Is(err, payment.ErrUnknownOutcome) {
			t.Errorf("%s: 결과를 모른다는 오류와 섞이면 주문이 confirming 에 남는다", name)
		}
	}
}
