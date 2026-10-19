// billing-server/internal/database/tracing.go

package database

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// 쿼리마다 span 을 건다(docs/observability.md 의 "3. 추적"). 이름은 sqlc 가 쿼리 앞에 적어 둔 이름이다(db GetWallet).
// 문장과 값은 싣지 않는다. 쿼리의 값에 사용자 번호, 결제 번호가 들어간다. 이름만으로 어느 쿼리인지 안다.
// 실패하면 SQLSTATE(23505 같은 것)만 적는다. 오류의 글에는 값이 섞일 수 있다.
//
// 부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 쿼리). 풀이 연결을 확인하는 것처럼 부모 없는 쿼리는 남기지 않는다.

const (
	// sqlcNamePrefix 는 sqlc 가 만든 쿼리의 첫 줄이다(-- name: GetWallet :one)
	sqlcNamePrefix = "-- name: "
	// unnamedQuery 는 이름이 없는 쿼리(손으로 쓴 것)의 이름이다
	unnamedQuery = "query"
	// querySpanPrefix 는 쿼리 span 의 이름 앞에 붙인다
	querySpanPrefix = "db "
)

// querySpanKey 는 이 tracer 가 건 span 을 context 에 싣는 열쇠다. 끝낼 때 부모의 span 을 잘못 끝내지 않게 한다.
type querySpanKey struct{}

// querySpans 는 쿼리마다 span 을 거는 pgx 의 QueryTracer 다.
type querySpans struct{}

// TraceQueryStart 는 쿼리가 시작할 때 span 을 건다. 부모 span 이 없으면 아무것도 하지 않는다.
func (querySpans) TraceQueryStart(ctx context.Context, _ *pgx.Conn, data pgx.TraceQueryStartData) context.Context {
	if !trace.SpanFromContext(ctx).IsRecording() {
		return ctx
	}
	name := queryName(data.SQL)
	ctx, span := tracing.Tracer().Start(ctx, querySpanPrefix+name,
		trace.WithSpanKind(trace.SpanKindClient),
		trace.WithAttributes(
			attribute.String("db.system.name", "postgresql"),
			attribute.String("db.operation.name", name),
		))
	return context.WithValue(ctx, querySpanKey{}, span)
}

// TraceQueryEnd 는 쿼리가 끝날 때 span 을 끝낸다. 실패면 SQLSTATE 를 적는다.
func (querySpans) TraceQueryEnd(ctx context.Context, _ *pgx.Conn, data pgx.TraceQueryEndData) {
	span, ok := ctx.Value(querySpanKey{}).(trace.Span)
	if !ok {
		return
	}
	if data.Err != nil {
		span.SetStatus(codes.Error, sqlState(data.Err))
	}
	span.End()
}

// queryName 은 sqlc 가 붙인 쿼리의 이름이다. 없으면 unnamedQuery 다.
func queryName(sql string) string {
	if !strings.HasPrefix(sql, sqlcNamePrefix) {
		return unnamedQuery
	}
	fields := strings.Fields(sql[len(sqlcNamePrefix):])
	if len(fields) == 0 {
		return unnamedQuery
	}
	return fields[0]
}

// sqlState 는 오류의 SQLSTATE 다. DB 가 낸 오류가 아니면(연결이 끊겼다, 취소됐다) error 다.
func sqlState(err error) string {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		return pgErr.Code
	}
	return "error"
}

// poolTracer 는 풀에 다는 tracer 다. 연결을 기다린 시간을 재고(acquireTimer, metrics.go), 쿼리마다 span 을 건다.
// pgx 는 연결의 Tracer 하나만 받는다. pgxpool 은 그것이 AcquireTracer 이기도 하면 기다리는 것도 알린다.
type poolTracer struct {
	acquire acquireTimer
	queries querySpans
}

// TraceAcquireStart 는 연결을 기다리기 시작할 때다.
func (p poolTracer) TraceAcquireStart(ctx context.Context, pool *pgxpool.Pool, data pgxpool.TraceAcquireStartData) context.Context {
	return p.acquire.TraceAcquireStart(ctx, pool, data)
}

// TraceAcquireEnd 는 연결을 얻었거나 포기했을 때다.
func (p poolTracer) TraceAcquireEnd(ctx context.Context, pool *pgxpool.Pool, data pgxpool.TraceAcquireEndData) {
	p.acquire.TraceAcquireEnd(ctx, pool, data)
}

// TraceQueryStart 는 쿼리가 시작할 때다.
func (p poolTracer) TraceQueryStart(ctx context.Context, conn *pgx.Conn, data pgx.TraceQueryStartData) context.Context {
	return p.queries.TraceQueryStart(ctx, conn, data)
}

// TraceQueryEnd 는 쿼리가 끝날 때다.
func (p poolTracer) TraceQueryEnd(ctx context.Context, conn *pgx.Conn, data pgx.TraceQueryEndData) {
	p.queries.TraceQueryEnd(ctx, conn, data)
}
