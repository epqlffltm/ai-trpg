// billing-server/internal/metrics/metrics_test.go

package metrics_test

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	collector "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	"google.golang.org/protobuf/proto"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 메트릭을 OTLP(HTTP)로 미는 것을 본다. 수집기 대신 이 테스트의 HTTP 서버가 받는다.

// otlpServer 는 OTLP 로 온 메트릭을 모으는 가짜 수집기다.
type otlpServer struct {
	mu       sync.Mutex
	paths    []string
	requests []*collector.ExportMetricsServiceRequest
}

// ServeHTTP 는 받은 본문을 protobuf 로 풀어 모은다.
func (s *otlpServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var request collector.ExportMetricsServiceRequest
	if err := proto.Unmarshal(body, &request); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.mu.Lock()
	s.paths = append(s.paths, r.URL.Path)
	s.requests = append(s.requests, &request)
	s.mu.Unlock()
	w.Header().Set("Content-Type", "application/x-protobuf")
	w.WriteHeader(http.StatusOK)
}

// received 는 받은 요청들이다.
func (s *otlpServer) received() ([]string, []*collector.ExportMetricsServiceRequest) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.paths, s.requests
}

// identity 는 테스트의 프로세스다.
var identity = metrics.Identity{Service: "billing-server", Version: "3f2a9c1", Environment: "test", Process: "sweeper"}

func TestWithoutAnEndpointNothingIsSent(t *testing.T) {
	provider, err := metrics.NewProvider(context.Background(), metrics.Exporting{Interval: time.Second}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	counter, err := provider.Meter().Int64Counter("stack_smoke_probe")
	if err != nil {
		t.Fatalf("계측기를 만들지 못했다: %v", err)
	}
	counter.Add(context.Background(), 1)

	if err := provider.Shutdown(); err != nil {
		t.Errorf("끄지 못했다: %v", err)
	}
}

func TestShutdownSendsWhatWasCountedWithTheResource(t *testing.T) {
	// 간격(1시간)을 기다리지 않고 끌 때 보낸다. cron 처럼 짧게 도는 명령이 이것에 기댄다
	server := &otlpServer{}
	collectorURL := httptest.NewServer(server)
	t.Cleanup(collectorURL.Close)
	provider, err := metrics.NewProvider(context.Background(),
		metrics.Exporting{Endpoint: collectorURL.URL, Interval: time.Hour}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	counter, _ := provider.Meter().Int64Counter("stack_smoke_probe")
	counter.Add(context.Background(), 3)

	if err := provider.Shutdown(); err != nil {
		t.Fatalf("끄지 못했다: %v", err)
	}

	paths, requests := server.received()
	if len(requests) != 1 || paths[0] != "/v1/metrics" {
		t.Fatalf("받은 요청 = %d 개, 주소 = %v. /v1/metrics 로 하나여야 한다", len(requests), paths)
	}
	resource := map[string]string{}
	for _, attr := range requests[0].ResourceMetrics[0].Resource.Attributes {
		resource[attr.Key] = attr.Value.GetStringValue()
	}
	if resource["service.name"] != "billing-server" || resource["service.version"] != "3f2a9c1" ||
		resource["deployment.environment.name"] != "test" {
		t.Errorf("출처 = %v", resource)
	}
	if !strings.HasPrefix(resource["service.instance.id"], "sweeper-") || len(resource["service.instance.id"]) != len("sweeper-")+8 {
		t.Errorf("service.instance.id = %q. 프로세스 이름과 8자의 글자여야 한다", resource["service.instance.id"])
	}
	if _, ok := resource["host.name"]; ok {
		t.Errorf("정하지 않은 출처(host.name)가 실렸다: %v", resource)
	}
	sent := requests[0].ResourceMetrics[0].ScopeMetrics[0].Metrics[0]
	if sent.Name != "stack_smoke_probe" || sent.GetSum().DataPoints[0].GetAsInt() != 3 {
		t.Errorf("보낸 메트릭 = %v", sent)
	}
}

func TestEachProcessGetsItsOwnInstance(t *testing.T) {
	// 같으면 두 프로세스의 수가 서로 덮어쓴다
	first := instanceOf(t)
	second := instanceOf(t)
	if first == second {
		t.Errorf("두 프로세스의 instance 가 같다: %q", first)
	}
}

// instanceOf 는 Provider 하나가 보낸 service.instance.id 다.
func instanceOf(t *testing.T) string {
	t.Helper()
	server := &otlpServer{}
	collectorURL := httptest.NewServer(server)
	t.Cleanup(collectorURL.Close)
	provider, err := metrics.NewProvider(context.Background(),
		metrics.Exporting{Endpoint: collectorURL.URL, Interval: time.Hour}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	counter, _ := provider.Meter().Int64Counter("stack_smoke_probe")
	counter.Add(context.Background(), 1)
	_ = provider.Shutdown()
	_, requests := server.received()
	for _, attr := range requests[0].ResourceMetrics[0].Resource.Attributes {
		if attr.Key == "service.instance.id" {
			return attr.Value.GetStringValue()
		}
	}
	t.Fatal("service.instance.id 가 없다")
	return ""
}

func TestAProcessNeedsAName(t *testing.T) {
	_, err := metrics.NewProvider(context.Background(),
		metrics.Exporting{Endpoint: "http://127.0.0.1:1", Interval: time.Second}, metrics.Identity{Service: "billing-server"})
	if err == nil {
		t.Error("프로세스의 이름 없이 만들어졌다")
	}
}

func TestShutdownGivesUpWhenTheCollectorIsDown(t *testing.T) {
	// 수집기가 죽어 있어도 끄는 일이 멈추지 않는다(ShutdownTimeout 안에 끝난다)
	provider, err := metrics.NewProvider(context.Background(),
		metrics.Exporting{Endpoint: "http://127.0.0.1:1", Interval: time.Hour}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	counter, _ := provider.Meter().Int64Counter("stack_smoke_probe")
	counter.Add(context.Background(), 1)

	started := time.Now()
	_ = provider.Shutdown()
	if took := time.Since(started); took > metrics.ShutdownTimeout+time.Second {
		t.Errorf("끄는 데 %s 걸렸다. %s 안이어야 한다", took, metrics.ShutdownTimeout)
	}
}
