// billing-server/internal/metrics/idempotency.go

package metrics

import (
	"context"
	"errors"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

// 중복 방지 키(같은 키로 다시 온 요청)의 결과를 센다. 주문(order)과 홀드(hold)가 같은 계측기를 쓴다.
// 두 곳이 따로 만들면 설명이 어긋나 같은 이름의 계측기가 둘이 된다. 그래서 만드는 곳을 여기 하나로 둔다.
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.

// metricIdempotency 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricIdempotency = "billing_idempotency"

// 중복 방지 키의 결과(label outcome).
const (
	// OutcomeFirst 는 그 키로 처음 왔다는 것이다. 새로 만들었다.
	OutcomeFirst = "first"
	// OutcomeReplayed 는 같은 키, 같은 내용으로 다시 왔다는 것이다. 새로 만들지 않고 먼저 것을 돌려줬다.
	OutcomeReplayed = "replayed"
	// OutcomeConflict 는 같은 키에 다른 내용으로 왔다는 것이다(409). 부르는 쪽의 버그다.
	OutcomeConflict = "conflict"
)

// Idempotency 는 중복 방지 키의 결과를 세는 계측기다.
type Idempotency struct {
	results metric.Int64Counter
}

// NewIdempotency 는 중복 방지 키의 계측기를 만든다. meter 가 없으면 세지 않는다.
func NewIdempotency(meter metric.Meter) (Idempotency, error) {
	results, err := MeterOrNoop(meter).Int64Counter(metricIdempotency,
		metric.WithDescription("중복 방지 키의 결과. kind 는 order, hold, outcome 은 first, replayed, conflict 다"))
	if err != nil {
		return Idempotency{}, err
	}
	return Idempotency{results: results}, nil
}

// NoIdempotency 는 세지 않는 계측기다.
func NoIdempotency() Idempotency {
	unmeasured, _ := NewIdempotency(nil)
	return unmeasured
}

// Count 는 끝난 요청 하나를 센다. created 는 새로 만들었는지, err 는 끝난 결과, reused 는 "같은 키에 다른 내용"의 오류다.
// 키를 보기 전에 끝난 요청(모양이 틀린 키, DB 오류)은 세지 않는다. 키의 결과가 아니다.
func (i Idempotency) Count(ctx context.Context, kind string, created bool, err error, reused error) {
	outcome, ok := IdempotencyOutcome(created, err, reused)
	if !ok {
		return
	}
	i.results.Add(ctx, 1, metric.WithAttributes(attribute.String("kind", kind), attribute.String("outcome", outcome)))
}

// IdempotencyOutcome 은 끝난 결과를 label outcome 의 값으로 바꾼다. 키의 결과가 아니면 두 번째 값이 false 다.
func IdempotencyOutcome(created bool, err error, reused error) (string, bool) {
	switch {
	case err == nil && created:
		return OutcomeFirst, true
	case err == nil:
		return OutcomeReplayed, true
	case errors.Is(err, reused):
		return OutcomeConflict, true
	default:
		return "", false
	}
}
