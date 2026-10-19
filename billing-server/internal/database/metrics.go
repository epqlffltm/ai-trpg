// billing-server/internal/database/metrics.go

package database

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 연결 풀을 메트릭으로 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "메트릭"의 DB 표에 있다.

// 계측기의 이름. 수집기가 단위를 붙여 db_pool_wait_seconds 가 된다.
const (
	metricPoolConnections    = "db_pool_connections"
	metricPoolConnectionsMax = "db_pool_connections_max"
	metricPoolWait           = "db_pool_wait"
)

// 연결의 상태(label state).
const (
	stateIdle  = "idle"
	stateInUse = "in_use"
)

// NewMeteredPool 은 NewPool 과 같고, 연결 풀의 상태(연결 수, 연결을 기다린 시간)를 meter 로 센다.
// 메트릭을 내는 프로세스(서버, 정리 작업, 대사)가 쓴다. 사람이 치는 명령은 NewPool 을 쓴다.
func NewMeteredPool(ctx context.Context, databaseURL string, schema string, limits Limits, meter metric.Meter) (*pgxpool.Pool, error) {
	poolConfig, err := NewPoolConfig(databaseURL, schema, limits)
	if err != nil {
		return nil, err
	}
	timer, err := newAcquireTimer(meter)
	if err != nil {
		return nil, err
	}
	poolConfig.ConnConfig.Tracer = timer
	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		return nil, err
	}
	if err := WatchPool(meter, pool); err != nil {
		pool.Close()
		return nil, err
	}
	return pool, nil
}

// WatchPool 은 Prometheus 가 값을 읽어 갈 때(15초마다) 풀의 연결 수를 읽게 한다. 풀을 두드리지 않는다(Stat 은 세어 둔 값이다).
func WatchPool(meter metric.Meter, pool *pgxpool.Pool) error {
	connections, err := meter.Int64ObservableGauge(metricPoolConnections,
		metric.WithDescription("연결 풀의 연결 수. state 는 idle, in_use 다"))
	if err != nil {
		return err
	}
	maxConnections, err := meter.Int64ObservableGauge(metricPoolConnectionsMax,
		metric.WithDescription("풀이 가질 수 있는 가장 많은 연결"))
	if err != nil {
		return err
	}
	_, err = meter.RegisterCallback(func(_ context.Context, observer metric.Observer) error {
		observePool(observer, pool.Stat(), connections, maxConnections)
		return nil
	}, connections, maxConnections)
	return err
}

// poolStat 은 풀의 세어 둔 값 가운데 메트릭에 쓰는 것이다. *pgxpool.Stat 이 이 모양이다.
type poolStat interface {
	IdleConns() int32
	AcquiredConns() int32
	MaxConns() int32
}

// observePool 은 풀의 값 하나를 적는다.
func observePool(observer metric.Observer, stat poolStat, connections, maxConnections metric.Int64Observable) {
	observer.ObserveInt64(connections, int64(stat.IdleConns()), metric.WithAttributes(attribute.String("state", stateIdle)))
	observer.ObserveInt64(connections, int64(stat.AcquiredConns()), metric.WithAttributes(attribute.String("state", stateInUse)))
	observer.ObserveInt64(maxConnections, int64(stat.MaxConns()))
}

// acquireTimer 는 풀에서 연결을 얻으려고 기다린 시간을 잰다. pgxpool 은 연결의 Tracer 가 AcquireTracer 이기도 하면 부른다.
// 쿼리마다 부르는 것(QueryTracer)은 아무것도 하지 않는다. 쿼리의 시간은 재지 않는다.
type acquireTimer struct {
	wait metric.Float64Histogram
}

// acquireStartKey 는 기다리기 시작한 시각을 context 에 싣는 열쇠다.
type acquireStartKey struct{}

// newAcquireTimer 는 기다린 시간의 계측기를 만든다.
func newAcquireTimer(meter metric.Meter) (acquireTimer, error) {
	wait, err := meter.Float64Histogram(metricPoolWait,
		metric.WithDescription("연결을 얻으려고 기다린 시간. 연결이 모자라면 늘어난다"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(metrics.DurationBuckets...))
	if err != nil {
		return acquireTimer{}, err
	}
	return acquireTimer{wait: wait}, nil
}

// TraceAcquireStart 는 기다리기 시작한 시각을 적는다.
func (a acquireTimer) TraceAcquireStart(ctx context.Context, _ *pgxpool.Pool, _ pgxpool.TraceAcquireStartData) context.Context {
	return context.WithValue(ctx, acquireStartKey{}, time.Now())
}

// TraceAcquireEnd 는 기다린 시간을 잰다. 얻지 못하고 끝난 것(마감, 취소)도 센다. 그만큼 기다렸다.
func (a acquireTimer) TraceAcquireEnd(ctx context.Context, _ *pgxpool.Pool, _ pgxpool.TraceAcquireEndData) {
	started, ok := ctx.Value(acquireStartKey{}).(time.Time)
	if !ok {
		return
	}
	a.wait.Record(ctx, time.Since(started).Seconds())
}

// TraceQueryStart 는 쿼리가 시작할 때 불린다. 아무것도 하지 않는다.
func (a acquireTimer) TraceQueryStart(ctx context.Context, _ *pgx.Conn, _ pgx.TraceQueryStartData) context.Context {
	return ctx
}

// TraceQueryEnd 는 쿼리가 끝날 때 불린다. 아무것도 하지 않는다.
func (a acquireTimer) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {}
