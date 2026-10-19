// billing-server/internal/jobs/metrics_test.go

package jobs_test

import (
	"context"
	"errors"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
)

// 작업이 정한 이름과 label 로 세어지는지 본다. docs/observability.md 의 "백그라운드 작업" 표다.

// measure 는 이 테스트 동안 작업을 메모리에 센다. 끝나면 세지 않는 것으로 돌려 둔다.
func measure(t *testing.T) *metricstest.Recorder {
	t.Helper()
	capture(t)
	recorder := metricstest.New(t)
	if err := jobs.Measure(recorder.Meter()); err != nil {
		t.Fatalf("작업의 메트릭을 만들지 못했다: %v", err)
	}
	t.Cleanup(func() { _ = jobs.Measure(nil) })
	return recorder
}

// finished 는 끝난 작업의 수다.
func finished(recorder *metricstest.Recorder, operation, result string) int64 {
	return recorder.Int64("background_jobs_finished",
		attribute.String("operation", operation), attribute.String("result", result))
}

func TestARunIsCountedFromStartToEnd(t *testing.T) {
	recorder := measure(t)
	operation := attribute.String("operation", "sweep.run")

	_ = jobs.Run(context.Background(), "sweep.run", func(context.Context) error { return nil })
	_ = jobs.Run(context.Background(), "sweep.run", func(context.Context) error { return nil })

	if got := recorder.Int64("background_jobs_started", operation); got != 2 {
		t.Errorf("시작한 수 = %d", got)
	}
	if got := finished(recorder, "sweep.run", jobs.ResultSuccess); got != 2 {
		t.Errorf("잘 끝난 수 = %d", got)
	}
	if got := recorder.Int64("background_jobs_running", operation); got != 0 {
		t.Errorf("도는 작업 = %d. 끝났으니 0 이어야 한다", got)
	}
	if got := recorder.HistogramCount("background_job_duration", operation); got != 2 {
		t.Errorf("잰 수 = %d", got)
	}
	if unit := recorder.Find("background_job_duration").Unit; unit != "s" {
		t.Errorf("단위 = %q. s 여야 한다", unit)
	}
}

func TestAFailedRunIsCountedAsServerError(t *testing.T) {
	recorder := measure(t)

	_ = jobs.Run(context.Background(), "reconcile.run", func(context.Context) error { return errors.New("connection refused") })

	if got := finished(recorder, "reconcile.run", jobs.ResultServerError); got != 1 {
		t.Errorf("실패한 수 = %d", got)
	}
}

func TestARunStoppedByShutdownIsCountedAsCancelled(t *testing.T) {
	recorder := measure(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_ = jobs.Run(ctx, "sweep.run", func(ctx context.Context) error { return ctx.Err() })

	if got := finished(recorder, "sweep.run", jobs.ResultCancelled); got != 1 {
		t.Errorf("취소된 수 = %d", got)
	}
}

func TestRunWithoutMeasureDoesNotCount(t *testing.T) {
	// 메트릭을 켜지 않은 명령도 작업은 그대로 돈다
	capture(t)
	ran := false

	err := jobs.Run(context.Background(), "sweep.run", func(context.Context) error { ran = true; return nil })

	if err != nil || !ran {
		t.Errorf("오류 = %v, 돌았다 = %v", err, ran)
	}
}
