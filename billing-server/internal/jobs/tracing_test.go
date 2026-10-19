// billing-server/internal/jobs/tracing_test.go

package jobs_test

import (
	"context"
	"errors"
	"testing"

	"go.opentelemetry.io/otel/codes"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing/tracingtest"
)

// 작업 한 번이 span 하나로 남는지 본다.

func TestARunIsASpanOfItsOwnTrace(t *testing.T) {
	capture(t)
	recorder := tracingtest.New(t)
	// 작업을 띄운 곳의 span 아래에 놓이지 않는다. 몇십 초마다 도는 것이 한 추적으로 묶이면 끝없이 길어진다
	ctx, parent := recorder.Parent(context.Background())
	var seen obs.IDs

	err := jobs.Run(ctx, "sweep.run", func(ctx context.Context) error {
		seen = obs.CurrentIDs(ctx)
		return nil
	})

	span := recorder.Only()
	if err != nil || span.Name() != "sweep.run" || span.Parent().IsValid() {
		t.Fatalf("오류 = %v, span = %s, 부모 = %v", err, span.Name(), span.Parent().SpanID())
	}
	if span.SpanContext().TraceID() == parent.SpanContext().TraceID() {
		t.Error("띄운 곳의 추적을 이어 갔다")
	}
	// 로그의 trace_id 가 이 span 의 것이다
	if seen.Trace.ID != span.SpanContext().TraceID().String() {
		t.Errorf("trace_id = %s, span = %s", seen.Trace.ID, span.SpanContext().TraceID())
	}
	attributes := tracingtest.Attributes(span)
	if attributes[obs.FieldResult].AsString() != jobs.ResultSuccess || attributes[tracing.AttributeJobID].AsString() != seen.JobID {
		t.Errorf("속성 = %v, 작업 = %s", attributes, seen.JobID)
	}
}

func TestAFailedRunMarksItsSpan(t *testing.T) {
	capture(t)
	recorder := tracingtest.New(t)

	_ = jobs.Run(context.Background(), "sweep.run", func(context.Context) error {
		return errors.New("connect failed: postgres://billing:super-secret@db.internal/trpg")
	})

	span := recorder.Only()
	if span.Status().Code != codes.Error || span.Status().Description != jobs.ErrorCodeFailed {
		t.Errorf("상태 = %v", span.Status())
	}
	// 오류의 글은 로그에만 있다
	if len(span.Events()) != 0 {
		t.Errorf("오류가 span 에 실렸다: %v", span.Events())
	}
}

func TestACancelledRunIsNotAnError(t *testing.T) {
	capture(t)
	recorder := tracingtest.New(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_ = jobs.Run(ctx, "sweep.run", func(ctx context.Context) error { return ctx.Err() })

	span := recorder.Only()
	if span.Status().Code == codes.Error || tracingtest.Attributes(span)[obs.FieldResult].AsString() != jobs.ResultCancelled {
		t.Errorf("상태 = %v, 속성 = %v", span.Status(), tracingtest.Attributes(span))
	}
}

func TestRunWithoutTracingStillGivesATrace(t *testing.T) {
	// span 을 내보내지 않는 PC 에서는 지금처럼 새 추적을 만든다
	capture(t)
	var seen obs.IDs

	_ = jobs.Run(context.Background(), "sweep.run", func(ctx context.Context) error {
		seen = obs.CurrentIDs(ctx)
		return nil
	})

	if seen.Trace.ID == "" || seen.JobID == "" {
		t.Errorf("식별자 = %+v", seen)
	}
}
