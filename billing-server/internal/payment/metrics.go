// billing-server/internal/payment/metrics.go

package payment

import (
	"context"
	"errors"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 결제 대행사를 부른 수를 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
// 결제 대행사를 감싸서 센다(Measured). 주문의 코드도, 결제 대행사의 코드도 세는 것을 모른다.

// metricProviderCalls 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricProviderCalls = "payment_provider_calls"

// 부른 일(label operation).
const (
	operationConfirm = "confirm"
	operationLookup  = "lookup"
	operationCancel  = "cancel"
)

// 답을 받지 못한 결과(label outcome). 답을 받았으면 그 상태(approved, declined …)가 결과다.
const (
	// OutcomeUnknown 은 결과를 모른다는 것이다(ErrUnknownOutcome). 돈이 나갔을 수도 있다
	OutcomeUnknown = "unknown"
	// OutcomeUnavailable 은 그 밖의 오류로 묻지 못했다는 것이다(설정, 부르지 않는 자리)
	OutcomeUnavailable = "unavailable"
)

// measured 는 부를 때마다 세는 결제 대행사다.
type measured struct {
	inner Provider
	name  string
	calls metric.Int64Counter
}

// Measured 는 inner 를 부를 때마다 meter 로 세는 결제 대행사를 돌려준다. name 은 label provider 다(fake, toss).
func Measured(inner Provider, name string, meter metric.Meter) (Provider, error) {
	calls, err := metrics.MeterOrNoop(meter).Int64Counter(metricProviderCalls,
		metric.WithDescription("결제 대행사를 부른 수. outcome 은 받은 상태, 또는 unknown, unavailable 이다"))
	if err != nil {
		return nil, err
	}
	return measured{inner: inner, name: name, calls: calls}, nil
}

// Confirm 은 승인을 요청하고 센다.
func (m measured) Confirm(ctx context.Context, request Request) (Result, error) {
	result, err := m.inner.Confirm(ctx, request)
	m.count(ctx, operationConfirm, result, err)
	return result, err
}

// Cancel 은 취소를 요청하고 센다.
func (m measured) Cancel(ctx context.Context, request Request) (Result, error) {
	result, err := m.inner.Cancel(ctx, request)
	m.count(ctx, operationCancel, result, err)
	return result, err
}

// Lookup 은 결과를 묻고 센다.
func (m measured) Lookup(ctx context.Context, request Request) (Result, error) {
	result, err := m.inner.Lookup(ctx, request)
	m.count(ctx, operationLookup, result, err)
	return result, err
}

// count 는 부른 일 하나를 센다.
func (m measured) count(ctx context.Context, operation string, result Result, err error) {
	m.calls.Add(ctx, 1, metric.WithAttributes(
		attribute.String("provider", m.name),
		attribute.String("operation", operation),
		attribute.String("outcome", OutcomeOf(result, err)),
	))
}

// OutcomeOf 는 결과를 label outcome 의 값으로 바꾼다. 답을 받았으면 그 상태다.
func OutcomeOf(result Result, err error) string {
	switch {
	case err == nil:
		return string(result.Status)
	case errors.Is(err, ErrUnknownOutcome):
		return OutcomeUnknown
	default:
		return OutcomeUnavailable
	}
}
