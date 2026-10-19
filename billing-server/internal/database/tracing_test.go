// billing-server/internal/database/tracing_test.go

package database_test

import (
	"context"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/codes"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing/tracingtest"
)

// 쿼리마다 span 이 걸리는지 실제 DB 로 본다.

// namedQuery 는 sqlc 가 만든 쿼리의 모양이다. 값(사용자 번호)을 흉내 낸 글자를 문장에 넣는다.
const namedQuery = "-- name: GetSecretThing :one\nSELECT 'user-0b9f5e0c' AS owner"

// meteredPool 은 span 을 거는 풀을 만들고, 테스트가 끝나면 닫는다.
func meteredPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	pool, err := database.NewMeteredPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema,
		database.ServerLimits, metricstest.New(t).Meter())
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestAQueryUnderASpanGetsASpanNamedBySqlc(t *testing.T) {
	recorder := tracingtest.New(t)
	pool := meteredPool(t)
	ctx, parent := recorder.Parent(within(t, connectLimit))

	var owner string
	if err := pool.QueryRow(ctx, namedQuery).Scan(&owner); err != nil {
		t.Fatalf("쿼리가 실패했다: %v", err)
	}

	span := recorder.Find("db GetSecretThing")
	if span.Parent().SpanID() != parent.SpanContext().SpanID() {
		t.Error("부모 span 아래에 놓이지 않았다")
	}
	attributes := tracingtest.Attributes(span)
	if attributes["db.system.name"].AsString() != "postgresql" || attributes["db.operation.name"].AsString() != "GetSecretThing" {
		t.Errorf("속성 = %v", attributes)
	}
	// 문장과 값은 싣지 않는다
	for key, value := range attributes {
		if strings.Contains(value.Emit(), "user-0b9f5e0c") || strings.Contains(value.Emit(), "SELECT") {
			t.Errorf("문장이 %s 에 실렸다: %s", key, value.Emit())
		}
	}
}

func TestAHandWrittenQueryIsNamedQuery(t *testing.T) {
	recorder := tracingtest.New(t)
	pool := meteredPool(t)
	ctx, _ := recorder.Parent(within(t, connectLimit))

	var answer int
	if err := pool.QueryRow(ctx, "SELECT 1 + 1").Scan(&answer); err != nil {
		t.Fatalf("쿼리가 실패했다: %v", err)
	}

	recorder.Find("db query")
}

func TestAQueryWithoutAParentGetsNoSpan(t *testing.T) {
	// 풀이 연결을 확인하는 것처럼 요청이나 작업 밖의 쿼리는 남기지 않는다
	recorder := tracingtest.New(t)
	pool := meteredPool(t)

	var owner string
	if err := pool.QueryRow(within(t, connectLimit), namedQuery).Scan(&owner); err != nil {
		t.Fatalf("쿼리가 실패했다: %v", err)
	}

	if names := recorder.Names(); len(names) != 0 {
		t.Errorf("부모 없이 span 이 걸렸다: %v", names)
	}
}

func TestAFailedQueryRecordsOnlyItsSQLState(t *testing.T) {
	recorder := tracingtest.New(t)
	pool := meteredPool(t)
	ctx, parent := recorder.Parent(within(t, connectLimit))

	var answer int
	err := pool.QueryRow(ctx, "-- name: DivideByZero :one\nSELECT 1 / 0").Scan(&answer)
	if err == nil {
		t.Fatal("0 으로 나눴는데 실패하지 않았다")
	}

	span := recorder.Find("db DivideByZero")
	if span.Status().Code != codes.Error || span.Status().Description != "22012" {
		t.Errorf("상태 = %v. SQLSTATE 22012 여야 한다", span.Status())
	}
	if len(span.Events()) != 0 {
		t.Errorf("오류의 글이 span 에 실렸다: %v", span.Events())
	}
	// 쿼리의 span 만 끝낸다. 부모는 그대로 기록 중이다
	if !parent.IsRecording() {
		t.Error("부모 span 이 끝났다")
	}
}
