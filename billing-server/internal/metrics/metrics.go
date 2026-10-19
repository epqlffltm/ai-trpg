// billing-server/internal/metrics/metrics.go

// Package metrics 는 결제 서버의 메트릭을 OTLP 로 수집기(Alloy)에 미는 것(MeterProvider)을 만든다.
// 규격은 저장소 루트의 docs/observability.md 의 "메트릭"과 "2. 메트릭"에 있다.
//
// 보내는 주소가 비어 있으면 내보내지 않는다(noop). 계측하는 코드는 그대로 돌고 보내기만 없다.
// PC 에서 직접 띄운 서버가 없는 주소로 보내며 오류를 남기지 않는다.
//
// 이름은 OTLP 의 이름으로 짓는다(http_server_request_duration, 단위 s). Prometheus 의 이름(…_seconds, …_total)은
// 수집기가 붙인다. 그래서 저장소를 Mimir 로 바꿔도 이름이 같다.
//
// 전역(otel.SetMeterProvider)에 두지 않는다. 만든 쪽(cmd/…)이 Meter 를 계측하는 곳에 넘긴다.
package metrics

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/metric/noop"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
)

// ScopeName 은 계측기를 만드는 쪽의 이름이다. Prometheus 의 label 로는 붙지 않는다(수집기가 뺀다).
const ScopeName = "github.com/epqlffltm/ai-trpg/billing-server"

// ShutdownTimeout 은 끌 때 남은 메트릭을 보내려고 기다리는 가장 긴 시간이다. 수집기가 죽어 있으면 이만큼 뒤에 끈다.
const ShutdownTimeout = 5 * time.Second

// metricsPath 는 OTLP(HTTP)로 메트릭을 받는 주소의 끝이다. 보내는 주소(OTEL_EXPORTER_OTLP_ENDPOINT) 뒤에 붙인다.
const metricsPath = "/v1/metrics"

// DurationBuckets 는 시간을 재는 히스토그램의 구간(초)이다. SDK 의 기본 구간은 밀리초를 가정한 숫자라
// 초로 재면 거의 모두 첫 칸에 든다. 다섯 서버가 같은 구간을 쓴다(docs/observability.md 의 "계측기를 만드는 법").
var DurationBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10}

// Exporting 은 메트릭을 어디로, 얼마나 자주 보낼지다. Endpoint 가 비면 보내지 않는다.
type Exporting struct {
	// Endpoint 는 수집기의 OTLP(HTTP) 주소다(http://alloy:4318). 끝에 /v1/metrics 를 붙여 보낸다.
	Endpoint string
	// Interval 은 모은 값을 보내는 간격이다.
	Interval time.Duration
}

// Enabled 는 메트릭을 보내는지다.
func (e Exporting) Enabled() bool {
	return e.Endpoint != ""
}

// Identity 는 메트릭을 낸 곳이다. 모든 메트릭에 붙는다(OTLP 의 resource).
type Identity struct {
	// Service 는 서비스 이름이다(billing-server). 수집기가 label service 로 옮긴다.
	Service string
	// Version 과 Environment 는 APP_VERSION, APP_ENVIRONMENT 다. Prometheus 에서는 target_info 에 있다.
	Version     string
	Environment string
	// Process 는 이 서버의 어느 프로세스인지다(server, sweeper, reconcile). label instance 의 앞부분이 된다.
	Process string
}

// Provider 는 계측기를 만들 Meter 를 주고, 끌 때 남은 것을 보낸다.
type Provider struct {
	provider metric.MeterProvider
	shutdown func(context.Context) error
}

// NewProvider 는 Provider 를 만든다. 보내는 주소가 없으면 아무것도 보내지 않는 것(noop)을 만든다.
// 만드는 것만으로는 수집기에 닿지 않는다. 수집기가 죽어 있어도 서버는 뜬다.
func NewProvider(ctx context.Context, exporting Exporting, identity Identity) (*Provider, error) {
	if !exporting.Enabled() {
		return &Provider{provider: noop.NewMeterProvider(), shutdown: func(context.Context) error { return nil }}, nil
	}
	exporter, err := newExporter(ctx, exporting.Endpoint)
	if err != nil {
		return nil, err
	}
	instance, err := instanceID(identity.Process)
	if err != nil {
		return nil, err
	}
	provider := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(NewResource(identity, instance)),
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exporter, sdkmetric.WithInterval(exporting.Interval))),
	)
	return &Provider{provider: provider, shutdown: provider.Shutdown}, nil
}

// newExporter 는 OTLP(HTTP, protobuf)로 보내는 것을 만든다. 주소의 http/https 를 그대로 따른다.
func newExporter(ctx context.Context, endpoint string) (sdkmetric.Exporter, error) {
	return otlpmetrichttp.New(ctx, otlpmetrichttp.WithEndpointURL(endpoint+metricsPath))
}

// NewResource 는 모든 메트릭에 붙는 출처를 만든다. 정해 둔 것만 싣는다(호스트 이름, 프로세스 번호는 싣지 않는다).
func NewResource(identity Identity, instance string) *resource.Resource {
	return resource.NewSchemaless(
		attribute.String("service.name", identity.Service),
		attribute.String("service.version", identity.Version),
		attribute.String("deployment.environment.name", identity.Environment),
		attribute.String("service.instance.id", instance),
	)
}

// InstanceID 는 프로세스마다 다른 이름을 새로 만든다(sweeper-3f2a9c1d). 추적(internal/tracing)도 같은 모양을 쓴다.
func InstanceID(process string) (string, error) {
	return instanceID(process)
}

// instanceID 는 프로세스마다 다른 이름이다(sweeper-3f2a9c1d). 같으면 두 프로세스의 수가 서로 덮어쓴다.
// 앞의 이름으로 서버와 정리 작업을 가른다. 뒤의 글자는 띄울 때마다 새로 정한다.
func instanceID(process string) (string, error) {
	if process == "" {
		return "", errors.New("메트릭을 낸 프로세스의 이름이 없습니다")
	}
	random := make([]byte, 4)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	return process + "-" + hex.EncodeToString(random), nil
}

// Meter 는 계측기를 만들 것을 돌려준다.
func (p *Provider) Meter() metric.Meter {
	return p.provider.Meter(ScopeName)
}

// Shutdown 은 모아 둔 값을 한 번 보내고 끈다. cron 처럼 짧게 도는 명령은 간격을 기다리기 전에 끝나므로 꼭 부른다.
// 수집기가 답하지 않으면 ShutdownTimeout 뒤에 버리고 끈다. 끄는 일이 그 때문에 멈추지 않는다.
func (p *Provider) Shutdown() error {
	ctx, cancel := context.WithTimeout(context.Background(), ShutdownTimeout)
	defer cancel()
	return p.shutdown(ctx)
}

// MeterOrNoop 은 넣어 준 Meter 가 없으면 아무것도 하지 않는 Meter 를 돌려준다. 테스트와 메트릭이 없는 명령이 쓴다.
func MeterOrNoop(meter metric.Meter) metric.Meter {
	if meter != nil {
		return meter
	}
	return noop.NewMeterProvider().Meter(ScopeName)
}
