// billing-server/internal/tracing/tracing.go

// Package tracing 은 결제 서버의 추적(span)을 OTLP 로 수집기(Alloy)에 미는 것(TracerProvider)을 만들고,
// 다른 곳을 부르는 HTTP 요청에 span 을 거는 것(Transport)을 준다.
// 규격은 저장소 루트의 docs/observability.md 의 "3. 추적"에 있다.
//
// 보내는 곳은 메트릭과 같다(OTEL_EXPORTER_OTLP_ENDPOINT). 비어 있으면 아무것도 하지 않는 것(noop)을 둔다.
// 그때는 span 이 생기지 않고, 로그의 trace_id 는 지금처럼 internal/obs 가 정한다.
//
// 메트릭과 달리 프로세스 전체(otel 의 전역)에 둔다. span 은 요청, 서버 사이의 호출, DB, 작업에 두루 걸려서
// 그 모든 곳에 Tracer 를 넘기면 함수마다 인자가 는다. 계측하는 곳은 Tracer() 로 가져다 쓴다.
package tracing

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// ScopeName 은 span 을 만드는 쪽의 이름이다. 메트릭의 것과 같다.
const ScopeName = metrics.ScopeName

// span 에 싣는 우리 식별자의 이름. 로그의 칸과 같은 이름이라 Tempo 에서 같은 말로 찾는다(span.request_id).
// OpenTelemetry 에 없는 개념이라 SDK 가 정한 이름이 없다.
const (
	AttributeRequestID = "request_id"
	AttributeJobID     = "job_id"
)

// tracesPath 는 OTLP(HTTP)로 추적을 받는 주소의 끝이다. 보내는 주소 뒤에 붙인다.
const tracesPath = "/v1/traces"

// Provider 는 span 을 만들 TracerProvider 를 주고, 끌 때 남은 span 을 보낸다.
type Provider struct {
	provider trace.TracerProvider
	shutdown func(context.Context) error
}

// NewProvider 는 Provider 를 만든다. 보내는 주소가 없으면 아무것도 하지 않는 것(noop)을 만든다.
// 만드는 것만으로는 수집기에 닿지 않는다. 수집기가 죽어 있어도 서버는 뜬다.
//
// span 을 남기는 규칙은 Sampler 다.
func NewProvider(ctx context.Context, exporting metrics.Exporting, identity metrics.Identity) (*Provider, error) {
	if !exporting.Enabled() {
		return &Provider{provider: noop.NewTracerProvider(), shutdown: func(context.Context) error { return nil }}, nil
	}
	instance, err := metrics.InstanceID(identity.Process)
	if err != nil {
		return nil, err
	}
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(exporting.Endpoint+tracesPath))
	if err != nil {
		return nil, err
	}
	provider := sdktrace.NewTracerProvider(
		sdktrace.WithResource(metrics.NewResource(identity, instance)),
		sdktrace.WithBatcher(exporter),
		sdktrace.WithSampler(Sampler()),
	)
	return &Provider{provider: provider, shutdown: provider.Shutdown}, nil
}

// Sampler 는 span 을 남길지 정하는 규칙이다. 모두 남긴다(AlwaysSample).
// 부른 쪽의 "기록하지 않음"(traceparent 의 flags 00)을 따르지 않는다. 다른 서버들은 아직 span 을 내보내지 않아
// 모두 00 을 붙여 보낸다. 그것을 따르면 결제 서버의 span 이 다 버려진다. 테스트(tracingtest)도 이 규칙을 쓴다.
func Sampler() sdktrace.Sampler {
	return sdktrace.AlwaysSample()
}

// TracerProvider 는 span 을 만들 것을 돌려준다. 프로세스의 시작에서 otel.SetTracerProvider 로 전역에 둔다.
func (p *Provider) TracerProvider() trace.TracerProvider {
	return p.provider
}

// Shutdown 은 모아 둔 span 을 보내고 끈다. 대사처럼 짧게 도는 명령은 묶음을 보내기 전에 끝나므로 꼭 부른다.
// 수집기가 답하지 않으면 metrics.ShutdownTimeout 뒤에 버리고 끈다.
func (p *Provider) Shutdown() error {
	ctx, cancel := context.WithTimeout(context.Background(), metrics.ShutdownTimeout)
	defer cancel()
	return p.shutdown(ctx)
}

// Tracer 는 span 을 만들 것을 돌려준다. 전역의 TracerProvider 를 따른다. 전역에 둔 것이 없으면 아무것도 하지 않는다.
func Tracer() trace.Tracer {
	return otel.Tracer(ScopeName)
}
