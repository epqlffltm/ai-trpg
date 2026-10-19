// billing-server/internal/order/metrics.go

package order

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 주문이 어느 상태가 되었는지 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
// 상태를 바꾼 이 프로세스가 센다. 다른 요청이 먼저 바꿔서 이번에 바꾸지 않은 것은 세지 않는다.
// 한 트랜잭션에서 바꾼 것(paid, refunding, 되돌린 paid)은 커밋한 뒤에 센다.

// metricOrders 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricOrders = "billing_orders"

// idempotencyKind 는 주문의 중복 방지 키의 label kind 다(billing_idempotency_total).
const idempotencyKind = "order"

// orderMetrics 는 주문을 세는 계측기들이다.
type orderMetrics struct {
	transitions metric.Int64Counter
	// keys 는 주문을 만들 때의 중복 방지 키(Idempotency-Key)의 결과를 센다.
	keys metrics.Idempotency
}

// newOrderMetrics 는 주문의 계측기를 만든다.
func newOrderMetrics(meter metric.Meter) (orderMetrics, error) {
	transitions, err := meter.Int64Counter(metricOrders,
		metric.WithDescription("주문이 그 상태가 된 수. 상태를 바꾼 프로세스가 커밋한 뒤에 센다"))
	if err != nil {
		return orderMetrics{}, err
	}
	keys, err := metrics.NewIdempotency(meter)
	if err != nil {
		return orderMetrics{}, err
	}
	return orderMetrics{transitions: transitions, keys: keys}, nil
}

// noOrderMetrics 는 세지 않는 계측기다. Measure 를 부르기 전의 값이다.
func noOrderMetrics() orderMetrics {
	unmeasured, _ := newOrderMetrics(metrics.MeterOrNoop(nil))
	return unmeasured
}

// became 는 주문 count 개가 status 가 되었다고 센다.
func (m orderMetrics) became(ctx context.Context, status Status, count int64) {
	if count <= 0 {
		return
	}
	m.transitions.Add(ctx, count, metric.WithAttributes(attribute.String("status", string(status))))
}

// keyed 는 주문을 만든 요청 하나의 중복 방지 키를 센다. 주문은 한 문장(INSERT)으로 만들어서 돌아오면 이미 커밋되었다.
func (m orderMetrics) keyed(ctx context.Context, created bool, err error) {
	m.keys.Count(ctx, idempotencyKind, created, err, ErrKeyReused)
}

// Measure 는 이 서비스가 바꾼 주문의 상태와 중복 방지 키의 결과를 meter 로 세게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) Measure(meter metric.Meter) error {
	measured, err := newOrderMetrics(metrics.MeterOrNoop(meter))
	if err != nil {
		return err
	}
	s.metrics = measured
	return nil
}
