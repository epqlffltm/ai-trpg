// billing-server/internal/hold/metrics.go

package hold

import (
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 홀드를 걸 때의 이름표(source + reference)가 중복 방지 키다. 그 결과를 센다(billing_idempotency_total).
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
// 빼고 돌려준 크레딧은 지갑이 센다(billing_ledger_operations_total).

// idempotencyKind 는 홀드의 중복 방지 키의 label kind 다.
const idempotencyKind = "hold"

// Measure 는 이 서비스가 건 홀드의 이름표의 결과를 meter 로 세게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) Measure(meter metric.Meter) error {
	keys, err := metrics.NewIdempotency(meter)
	if err != nil {
		return err
	}
	s.keys = keys
	return nil
}
