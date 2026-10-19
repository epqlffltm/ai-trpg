// billing-server/internal/database/metrics_test.go

package database_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// 연결 풀의 메트릭(docs/observability.md 의 DB 표)을 실제 DB 로 본다.

// connectLimit 은 DB 의 답을 기다리는 가장 긴 시간이다. DB 가 답하지 않아도 테스트가 멈추지 않는다.
const connectLimit = 10 * time.Second

func TestAMeteredPoolCountsItsConnectionsAndWaits(t *testing.T) {
	recorder := metricstest.New(t)
	pool, err := database.NewMeteredPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema,
		database.ServerLimits, recorder.Meter())
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)

	conn, err := pool.Acquire(within(t, connectLimit))
	if err != nil {
		t.Fatalf("연결을 얻지 못했다: %v", err)
	}
	inUse := recorder.Int64("db_pool_connections", attribute.String("state", "in_use"))
	conn.Release()

	if inUse != 1 {
		t.Errorf("쥔 동안의 in_use = %d. 1 이어야 한다", inUse)
	}
	if got := recorder.Int64("db_pool_connections", attribute.String("state", "idle")); got != 1 {
		t.Errorf("돌려준 뒤의 idle = %d. 1 이어야 한다", got)
	}
	if got := recorder.Int64("db_pool_connections_max"); got != int64(database.ServerLimits.MaxConns) {
		t.Errorf("가장 많은 연결 = %d. %d 여야 한다", got, database.ServerLimits.MaxConns)
	}
	if got := recorder.HistogramCount("db_pool_wait"); got != 1 {
		t.Errorf("기다린 시간을 잰 수 = %d. 한 번 얻었으니 1 이어야 한다", got)
	}
	if unit := recorder.Find("db_pool_wait").Unit; unit != "s" {
		t.Errorf("단위 = %q. s 여야 한다", unit)
	}
}

func TestAMeteredPoolStillRunsQueries(t *testing.T) {
	// 연결에 붙인 추적(Tracer)은 쿼리를 건드리지 않는다
	recorder := metricstest.New(t)
	pool, err := database.NewMeteredPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema,
		database.ServerLimits, recorder.Meter())
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)

	var answer int
	if err := pool.QueryRow(within(t, connectLimit), "SELECT 1 + 1").Scan(&answer); err != nil || answer != 2 {
		t.Errorf("답 = %d, 오류 = %v", answer, err)
	}
}

func TestAMeteredPoolHidesTheURLInErrors(t *testing.T) {
	recorder := metricstest.New(t)
	_, err := database.NewMeteredPool(context.Background(), "postgres://billing:x@127.0.0.1:not-a-port/trpg",
		config.DefaultSchema, database.ServerLimits, recorder.Meter())
	if !errors.Is(err, database.ErrInvalidURL) {
		t.Errorf("오류 = %v. ErrInvalidURL 이어야 한다", err)
	}
}
