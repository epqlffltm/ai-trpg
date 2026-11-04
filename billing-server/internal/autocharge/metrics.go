// billing-server/internal/autocharge/metrics.go

package autocharge

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 결제 작업(cmd/autocharge)이 충전할 일을 어떻게 끝냈는지 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
// 이 작업이 바꾼 것만 센다. 다른 쪽(다른 작업, 사람의 결정)이 먼저 끝내 이번에 바꾸지 않은 것은 세지 않는다.
// 사람이 정한 것(cmd/autocharges decide)은 세지 않는다(로그의 autocharge.resolve 로 본다).

// metricAutoCharges 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricAutoCharges = "billing_auto_charges"

// label outcome 의 값. 끝난 것(paid, declined, skipped)과, 답을 받지 못해 다시 보낼 것(retried)이다.
const (
	outcomeLabelPaid     = "paid"
	outcomeLabelDeclined = "declined"
	outcomeLabelSkipped  = "skipped"
	outcomeLabelRetried  = "retried"
)

// chargeMetrics 는 결제 작업의 계측기다.
type chargeMetrics struct {
	charges metric.Int64Counter
}

// newChargeMetrics 는 결제 작업의 계측기를 만든다.
func newChargeMetrics(meter metric.Meter) (chargeMetrics, error) {
	charges, err := meter.Int64Counter(metricAutoCharges,
		metric.WithDescription("결제 작업이 충전할 일을 끝낸 수(결과마다)와 다시 보낼 것으로 미룬 수. 커밋한 뒤에 센다"))
	if err != nil {
		return chargeMetrics{}, err
	}
	return chargeMetrics{charges: charges}, nil
}

// noChargeMetrics 는 세지 않는 계측기다. Measure 를 부르기 전의 값이다.
func noChargeMetrics() chargeMetrics {
	unmeasured, _ := newChargeMetrics(metrics.MeterOrNoop(nil))
	return unmeasured
}

// ended 는 일 하나가 outcome 이 되었다고 센다. 그만둔 것(skipped)만 까닭(reason)을 붙인다.
func (m chargeMetrics) ended(ctx context.Context, outcome string, reason string) {
	attrs := []attribute.KeyValue{attribute.String("outcome", outcome)}
	if outcome == outcomeLabelSkipped {
		attrs = append(attrs, attribute.String("reason", reason))
	}
	m.charges.Add(ctx, 1, metric.WithAttributes(attrs...))
}

// Measure 는 이 서비스의 결제 작업이 끝낸 일을 meter 로 세게 한다. 결제 작업을 돌리기 전에 한 번 부른다.
func (s *Service) Measure(meter metric.Meter) error {
	measured, err := newChargeMetrics(metrics.MeterOrNoop(meter))
	if err != nil {
		return err
	}
	s.metrics = measured
	return nil
}
