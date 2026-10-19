// billing-server/internal/payment/metrics_test.go

package payment_test

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 결제 대행사를 부른 수(payment_provider_calls)를 시험한다. 이름과 label 은 docs/observability.md 의 "결제 (billing)" 표에 있다.

// answering 은 정해 둔 답을 돌려주는 결제 대행사다.
type answering struct {
	result payment.Result
	err    error
}

func (a answering) Confirm(context.Context, payment.Request) (payment.Result, error) {
	return a.result, a.err
}
func (a answering) Cancel(context.Context, payment.Request) (payment.Result, error) {
	return a.result, a.err
}
func (a answering) Lookup(context.Context, payment.Request) (payment.Result, error) {
	return a.result, a.err
}

// callLabels 는 부른 수의 label 이다.
func callLabels(provider, operation, outcome string) []attribute.KeyValue {
	return []attribute.KeyValue{
		attribute.String("provider", provider), attribute.String("operation", operation), attribute.String("outcome", outcome),
	}
}

// measuredProvider 는 inner 를 감싸 세는 결제 대행사와 그 값을 모으는 것을 만든다.
func measuredProvider(t *testing.T, inner payment.Provider) (payment.Provider, *metricstest.Recorder) {
	t.Helper()
	recorder := metricstest.New(t)
	provider, err := payment.Measured(inner, "toss", recorder.Meter())
	if err != nil {
		t.Fatalf("결제 대행사를 감싸지 못했다: %v", err)
	}
	return provider, recorder
}

func TestOutcomeIsTheAnsweredStatusOrWhyThereWasNoAnswer(t *testing.T) {
	cases := []struct {
		name   string
		result payment.Result
		err    error
		want   string
	}{
		{"승인", payment.Result{Status: payment.StatusApproved}, nil, "approved"},
		{"거절", payment.Result{Status: payment.StatusDeclined, Code: "card_declined"}, nil, "declined"},
		{"입금 대기", payment.Result{Status: payment.StatusAwaitingDeposit}, nil, "awaiting_deposit"},
		{"답을 받지 못했다", payment.Result{}, payment.ErrUnknownOutcome, "unknown"},
		{"감싼 ErrUnknownOutcome", payment.Result{}, fmt.Errorf("confirm: %w", payment.ErrUnknownOutcome), "unknown"},
		// 거절 코드(Code)는 label 이 아니다. 결제 대행사가 정하는 값이라 종류가 끝이 없다
		{"그 밖의 오류", payment.Result{Status: payment.StatusApproved}, errors.New("no secret key"), "unavailable"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := payment.OutcomeOf(tc.result, tc.err); got != tc.want {
				t.Errorf("outcome = %q. %q 여야 한다", got, tc.want)
			}
		})
	}
}

func TestEveryCallIsCountedByOperationAndOutcome(t *testing.T) {
	provider, recorder := measuredProvider(t, answering{result: payment.Result{Status: payment.StatusApproved}})
	ctx := context.Background()
	_, _ = provider.Confirm(ctx, payment.Request{})
	_, _ = provider.Confirm(ctx, payment.Request{})
	_, _ = provider.Lookup(ctx, payment.Request{})
	_, _ = provider.Cancel(ctx, payment.Request{})

	want := map[string]int64{"confirm": 2, "lookup": 1, "cancel": 1}
	for operation, count := range want {
		if got := recorder.Int64("payment_provider_calls", callLabels("toss", operation, "approved")...); got != count {
			t.Errorf("%s = %d. %d 여야 한다", operation, got, count)
		}
	}
}

func TestTheWrapperPassesTheAnswerThroughUnchanged(t *testing.T) {
	inner := answering{result: payment.Result{Status: payment.StatusPending}, err: payment.ErrUnknownOutcome}
	provider, recorder := measuredProvider(t, inner)

	result, err := provider.Confirm(context.Background(), payment.Request{})

	// 세는 것이 답을 바꾸면 주문이 다르게 끝난다
	if result != inner.result || !errors.Is(err, payment.ErrUnknownOutcome) {
		t.Errorf("답 = %+v, %v. 감싼 것의 답 그대로여야 한다", result, err)
	}
	if got := recorder.Int64("payment_provider_calls", callLabels("toss", "confirm", "unknown")...); got != 1 {
		t.Errorf("결과를 모르는 승인 = %d. 1 이어야 한다", got)
	}
}
