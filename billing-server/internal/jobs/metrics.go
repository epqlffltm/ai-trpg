// billing-server/internal/jobs/metrics.go

package jobs

import (
	"context"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 작업을 메트릭으로 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "백그라운드 작업" 표에 있다.
// 게임 서버와 인증 서버의 작업과 같은 이름이다. 수집기가 _total 과 _seconds 를 붙인다.
//
// 로그처럼 프로세스에 하나를 둔다(Measure). 작업을 띄우는 곳(cmd/sweeper, cmd/reconcile)마다 Meter 를 넘기지 않는다.
// 부르지 않으면 세지 않는다.

// 계측기의 이름.
const (
	metricStarted  = "background_jobs_started"
	metricFinished = "background_jobs_finished"
	metricRunning  = "background_jobs_running"
	metricDuration = "background_job_duration"
)

// instruments 는 작업을 세는 계측기들이다.
type instruments struct {
	started  metric.Int64Counter
	finished metric.Int64Counter
	running  metric.Int64UpDownCounter
	duration metric.Float64Histogram
}

// current 는 지금 쓰는 계측기다. 처음에는 세지 않는 것이다.
var current atomic.Pointer[instruments]

func init() {
	noop, _ := newInstruments(metrics.MeterOrNoop(nil))
	current.Store(noop)
}

// Measure 는 이 프로세스의 작업을 meter 로 세게 한다. 프로세스가 뜰 때 한 번 부른다.
func Measure(meter metric.Meter) error {
	measured, err := newInstruments(metrics.MeterOrNoop(meter))
	if err != nil {
		return err
	}
	current.Store(measured)
	return nil
}

// newInstruments 는 작업의 계측기를 만든다.
func newInstruments(meter metric.Meter) (*instruments, error) {
	started, startedErr := meter.Int64Counter(metricStarted, metric.WithDescription("시작한 작업의 수"))
	finished, finishedErr := meter.Int64Counter(metricFinished,
		metric.WithDescription("끝난 작업의 수. result 는 success, server_error, cancelled 다"))
	running, runningErr := meter.Int64UpDownCounter(metricRunning, metric.WithDescription("지금 도는 작업의 수"))
	duration, durationErr := meter.Float64Histogram(metricDuration,
		metric.WithDescription("작업 하나가 걸린 시간"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(metrics.DurationBuckets...))
	for _, err := range []error{startedErr, finishedErr, runningErr, durationErr} {
		if err != nil {
			return nil, err
		}
	}
	return &instruments{started: started, finished: finished, running: running, duration: duration}, nil
}

// begin 은 작업이 시작했다고 센다.
func (i *instruments) begin(ctx context.Context, operation string) {
	labels := metric.WithAttributes(attribute.String("operation", operation))
	i.started.Add(ctx, 1, labels)
	i.running.Add(ctx, 1, labels)
}

// end 는 작업이 끝났다고 센다. result 는 끝난 줄의 result 와 같다.
func (i *instruments) end(ctx context.Context, operation string, result string, took time.Duration) {
	labels := metric.WithAttributes(attribute.String("operation", operation))
	i.running.Add(ctx, -1, labels)
	i.duration.Record(ctx, took.Seconds(), labels)
	i.finished.Add(ctx, 1, metric.WithAttributes(attribute.String("operation", operation), attribute.String("result", result)))
}
