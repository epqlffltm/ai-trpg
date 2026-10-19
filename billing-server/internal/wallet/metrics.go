// billing-server/internal/wallet/metrics.go

package wallet

import (
	"context"

	"github.com/jackc/pgx/v5"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// 원장에 적은 일을 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
//
// 세는 단위는 줄이 아니라 한 번의 변경(작업 번호, operation_id)이다. 사라진 묶음이 셋이면 expire 줄은 셋이지만 일은 하나다.
// 줄을 하나도 적지 않은 일(사라질 것이 없던 정리, 돌려줄 줄이 없던 반환)은 세지 않는다.
//
// 트랜잭션 안에서 적은 줄은 커밋되기 전까지 적힌 것이 아니다. 그래서 바로 세지 않고 트랜잭션의 바구니에 담는다(txn.AfterCommit).
// 커밋하면 success, 되돌리면 failure 다. 트랜잭션은 이 패키지가 열든(withLockedWallet) 부르는 쪽이 열든 txn.Run 으로 연다.
// txn.Run 으로 열지 않은 트랜잭션의 일은 세지 못한다. 부르는 쪽의 테스트가 센 것을 확인한다.

// metricLedgerOperations 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricLedgerOperations = "billing_ledger_operations"

// 원장에 적은 일이 어떻게 끝났는지(label result).
const (
	// resultSuccess 는 커밋되었다는 것이다.
	resultSuccess = "success"
	// resultFailure 는 적었다가 되돌렸다는 것이다(트랜잭션이 커밋되지 않았다).
	resultFailure = "failure"
)

// ledgerMetrics 는 원장의 일을 세는 계측기다.
type ledgerMetrics struct {
	operations metric.Int64Counter
}

// newLedgerMetrics 는 원장의 계측기를 만든다.
func newLedgerMetrics(meter metric.Meter) (ledgerMetrics, error) {
	operations, err := meter.Int64Counter(metricLedgerOperations,
		metric.WithDescription("원장에 적은 일(작업 번호 하나)의 수. reason 은 원장의 이유, result 는 success, failure 다"))
	if err != nil {
		return ledgerMetrics{}, err
	}
	return ledgerMetrics{operations: operations}, nil
}

// noLedgerMetrics 는 세지 않는 계측기다. Measure 를 부르기 전의 값이다.
func noLedgerMetrics() ledgerMetrics {
	unmeasured, _ := newLedgerMetrics(metrics.MeterOrNoop(nil))
	return unmeasured
}

// afterCommit 은 tx 가 끝나면 reason 의 일 하나를 그 결과로 세게 담는다.
func (m ledgerMetrics) afterCommit(tx pgx.Tx, reason Reason) {
	txn.AfterCommit(tx,
		func(ctx context.Context) { m.count(ctx, reason, resultSuccess) },
		func(ctx context.Context) { m.count(ctx, reason, resultFailure) },
	)
}

// count 는 원장의 일 하나를 센다.
func (m ledgerMetrics) count(ctx context.Context, reason Reason, result string) {
	m.operations.Add(ctx, 1, metric.WithAttributes(attribute.String("reason", string(reason)), attribute.String("result", result)))
}

// Measure 는 이 서비스가 원장에 적은 일을 meter 로 세게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) Measure(meter metric.Meter) error {
	measured, err := newLedgerMetrics(metrics.MeterOrNoop(meter))
	if err != nil {
		return err
	}
	s.metrics = measured
	return nil
}
