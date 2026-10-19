// billing-server/internal/tracing/tracingtest/tracingtest.go

// Package tracingtest 는 테스트가 남긴 span 을 읽게 한다. 메모리에 모으는 것(SpanRecorder)을 전역에 두고,
// 테스트가 끝나면 아무것도 하지 않는 것(noop)으로 되돌린다. 보내는 일(OTLP)은 하지 않는다.
//
// 전역을 바꾸므로 이것을 쓰는 테스트는 t.Parallel 을 쓰지 않는다.
package tracingtest

import (
	"context"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// parentName 은 Parent 가 거는 span 의 이름이다.
const parentName = "test.parent"

// Recorder 는 테스트 하나가 남긴 span 을 모은다.
type Recorder struct {
	t     testing.TB
	spans *tracetest.SpanRecorder
}

// New 는 메모리에 모으는 TracerProvider 를 전역에 둔다. 남기는 규칙은 서버와 같다(tracing.Sampler).
func New(t testing.TB) *Recorder {
	t.Helper()
	spans := tracetest.NewSpanRecorder()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSpanProcessor(spans), sdktrace.WithSampler(tracing.Sampler()))
	otel.SetTracerProvider(provider)
	t.Cleanup(func() {
		otel.SetTracerProvider(noop.NewTracerProvider())
		_ = provider.Shutdown(context.Background())
	})
	return &Recorder{t: t, spans: spans}
}

// Parent 는 기록 중인 span 을 건 context 다. 요청이나 작업 안에서 도는 것을 흉내 낸다. 테스트가 끝나면 닫는다.
func (r *Recorder) Parent(ctx context.Context) (context.Context, trace.Span) {
	ctx, span := tracing.Tracer().Start(ctx, parentName)
	r.t.Cleanup(func() { span.End() })
	return ctx, span
}

// Ended 는 끝난 span 들이다. Parent 가 건 것은 뺀다.
func (r *Recorder) Ended() []sdktrace.ReadOnlySpan {
	var ended []sdktrace.ReadOnlySpan
	for _, span := range r.spans.Ended() {
		if span.Name() != parentName {
			ended = append(ended, span)
		}
	}
	return ended
}

// Names 는 끝난 span 의 이름들이다.
func (r *Recorder) Names() []string {
	var names []string
	for _, span := range r.Ended() {
		names = append(names, span.Name())
	}
	return names
}

// Only 는 끝난 span 이 하나일 때 그것이다. 하나가 아니면 테스트를 멈춘다.
func (r *Recorder) Only() sdktrace.ReadOnlySpan {
	r.t.Helper()
	ended := r.Ended()
	if len(ended) != 1 {
		r.t.Fatalf("끝난 span 이 %d 개다. 하나여야 한다: %v", len(ended), r.Names())
	}
	return ended[0]
}

// Find 는 그 이름으로 끝난 span 이다. 그 이름이 하나가 아니면 테스트를 멈춘다.
func (r *Recorder) Find(name string) sdktrace.ReadOnlySpan {
	r.t.Helper()
	var found []sdktrace.ReadOnlySpan
	for _, span := range r.Ended() {
		if span.Name() == name {
			found = append(found, span)
		}
	}
	if len(found) != 1 {
		r.t.Fatalf("span %s 가 %d 개다. 하나여야 한다: %v", name, len(found), r.Names())
	}
	return found[0]
}

// Attributes 는 span 의 속성을 이름으로 찾게 펼친 것이다.
func Attributes(span sdktrace.ReadOnlySpan) map[attribute.Key]attribute.Value {
	found := map[attribute.Key]attribute.Value{}
	for _, attr := range span.Attributes() {
		found[attr.Key] = attr.Value
	}
	return found
}
