// billing-server/internal/jobs/jobs.go

// Package jobs 는 요청과 따로 도는 일(정리 작업, 대사)에 식별자(job_id)를 걸고, 끝난 모양을 한 줄로 남긴다.
// 규격은 docs/observability.md 의 "작업 식별자 job_id"와 "작업이 끝난 줄"이다. 게임 서버와 인증 서버의 것과 같은 모양이다.
package jobs

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// 작업이 끝난 모양(result)과 실패한 작업의 오류 코드.
const (
	ResultSuccess     = "success"
	ResultCancelled   = "cancelled"
	ResultServerError = "server_error"
	ErrorCodeFailed   = "job.failed"
)

// Run 은 do 를 작업 하나로 돌린다. 새 job_id 를 건 context 를 넘기므로, do 가 남기는 로그에 그 번호가 붙는다.
// 요청에서 띄운 것이 아니므로 새 추적(trace_id)을 시작한다.
//
// 끝나면 한 줄을 남기고 do 의 오류를 그대로 돌려준다.
// 잘 끝난 것은 debug 다. 정리 작업은 몇십 초마다 돈다. info 로 적으면 로그를 메운다. 한 일이 있으면 do 가 따로 info 로 적는다.
// 끄느라 취소된 것은 warning, 오류로 끝난 것은 error 다.
//
// 시작과 끝, 걸린 시간을 메트릭으로도 센다(metrics.go, Measure). 한 번 도는 것을 span 하나로도 남긴다(이름은 operation).
// 그 안의 쿼리와 다른 서버를 부르는 것이 이 span 아래에 놓이고, 로그의 trace_id 가 이 span 의 것이 된다.
func Run(ctx context.Context, operation string, do func(context.Context) error) error {
	ctx, span := startSpan(ctx, operation)
	defer span.End()
	jobID := uuid.NewString()
	ctx = obs.WithJob(ctx, jobID)
	span.SetAttributes(attribute.String(tracing.AttributeJobID, jobID))
	measured := current.Load()
	measured.begin(ctx, operation)
	started := time.Now()
	err := do(ctx)
	took := time.Since(started)
	result := resultOf(ctx, err)
	finish(ctx, operation, took, result, err)
	measured.end(ctx, operation, result, took)
	markSpan(span, result)
	return err
}

// startSpan 은 작업 한 번의 span 을 새 추적으로 건다. 추적을 내보내지 않으면 아무것도 걸리지 않는다.
func startSpan(ctx context.Context, operation string) (context.Context, trace.Span) {
	return tracing.Tracer().Start(ctx, operation, trace.WithNewRoot())
}

// markSpan 은 끝난 모양을 span 에 적는다. 실패만 오류로 표시한다. 오류의 글은 로그에 있다(finish).
func markSpan(span trace.Span, result string) {
	span.SetAttributes(attribute.String(obs.FieldResult, result))
	if result == ResultServerError {
		span.SetStatus(codes.Error, ErrorCodeFailed)
	}
}

// resultOf 는 작업이 끝난 모양이다. 끄느라 취소된 것은 cancelled, 그 밖의 오류는 server_error 다.
func resultOf(ctx context.Context, err error) string {
	switch {
	case err == nil:
		return ResultSuccess
	case errors.Is(err, context.Canceled) && ctx.Err() != nil:
		return ResultCancelled
	default:
		return ResultServerError
	}
}

// finish 는 작업이 끝난 줄을 남긴다.
func finish(ctx context.Context, operation string, took time.Duration, result string, err error) {
	attrs := []slog.Attr{
		slog.String(obs.FieldOperation, operation),
		slog.Int64(obs.FieldDurationMS, took.Milliseconds()),
		slog.String(obs.FieldResult, result),
	}
	switch result {
	case ResultSuccess:
		slog.LogAttrs(ctx, slog.LevelDebug, "작업이 끝났다", attrs...)
	case ResultCancelled:
		slog.LogAttrs(ctx, slog.LevelWarn, "작업이 취소되었다", attrs...)
	default:
		slog.LogAttrs(ctx, slog.LevelError, "작업이 실패했다", append(attrs,
			slog.String(obs.FieldErrorCode, ErrorCodeFailed),
			slog.String(obs.FieldErrorMessage, err.Error()),
		)...)
	}
}
