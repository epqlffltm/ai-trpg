// billing-server/internal/tracing/tracing_test.go

package tracing_test

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	collector "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/proto"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// span 을 OTLP(HTTP)로 미는 것을 본다. 수집기 대신 이 테스트의 HTTP 서버가 받는다.

// otlpServer 는 OTLP 로 온 span 을 모으는 가짜 수집기다.
type otlpServer struct {
	mu       sync.Mutex
	paths    []string
	requests []*collector.ExportTraceServiceRequest
}

// ServeHTTP 는 받은 본문을 protobuf 로 풀어 모은다.
func (s *otlpServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var request collector.ExportTraceServiceRequest
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
func (s *otlpServer) received() ([]string, []*collector.ExportTraceServiceRequest) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.paths, s.requests
}

// identity 는 테스트의 프로세스다.
var identity = metrics.Identity{Service: "billing-server", Version: "3f2a9c1", Environment: "test", Process: "reconcile"}

func TestWithoutAnEndpointNothingIsRecorded(t *testing.T) {
	provider, err := tracing.NewProvider(context.Background(), metrics.Exporting{}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}

	_, span := provider.TracerProvider().Tracer(tracing.ScopeName).Start(context.Background(), "reconcile.run")
	span.End()

	if span.IsRecording() || span.SpanContext().IsValid() {
		t.Error("보낼 곳이 없는데 span 이 기록됐다")
	}
	if err := provider.Shutdown(); err != nil {
		t.Errorf("끄지 못했다: %v", err)
	}
}

func TestShutdownSendsTheSpansWithTheResource(t *testing.T) {
	// 대사처럼 짧게 도는 명령은 묶음을 보내기 전에 끝난다. 끌 때 보내는 것에 기댄다
	server := &otlpServer{}
	collectorURL := httptest.NewServer(server)
	t.Cleanup(collectorURL.Close)
	provider, err := tracing.NewProvider(context.Background(), metrics.Exporting{Endpoint: collectorURL.URL}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	_, span := provider.TracerProvider().Tracer(tracing.ScopeName).Start(context.Background(), "reconcile.run")
	span.End()

	if err := provider.Shutdown(); err != nil {
		t.Fatalf("끄지 못했다: %v", err)
	}

	paths, requests := server.received()
	if len(requests) != 1 || paths[0] != "/v1/traces" {
		t.Fatalf("받은 요청 = %d 개, 주소 = %v. /v1/traces 로 하나여야 한다", len(requests), paths)
	}
	resource := map[string]string{}
	for _, attr := range requests[0].ResourceSpans[0].Resource.Attributes {
		resource[attr.Key] = attr.Value.GetStringValue()
	}
	// 메트릭과 같은 출처다. Grafana 가 둘을 service 로 잇는다
	if resource["service.name"] != "billing-server" || resource["deployment.environment.name"] != "test" ||
		!strings.HasPrefix(resource["service.instance.id"], "reconcile-") {
		t.Errorf("출처 = %v", resource)
	}
	sent := requests[0].ResourceSpans[0].ScopeSpans[0].Spans[0]
	if sent.Name != "reconcile.run" {
		t.Errorf("보낸 span = %v", sent.Name)
	}
}

func TestAProcessNeedsANameToSendSpans(t *testing.T) {
	_, err := tracing.NewProvider(context.Background(),
		metrics.Exporting{Endpoint: "http://127.0.0.1:1"}, metrics.Identity{Service: "billing-server"})
	if err == nil {
		t.Error("프로세스의 이름 없이 만들어졌다")
	}
}

func TestShutdownGivesUpWhenTheCollectorIsDown(t *testing.T) {
	// 수집기가 죽어 있어도 끄는 일이 멈추지 않는다(ShutdownTimeout 안에 끝난다)
	provider, err := tracing.NewProvider(context.Background(), metrics.Exporting{Endpoint: "http://127.0.0.1:1"}, identity)
	if err != nil {
		t.Fatalf("만들지 못했다: %v", err)
	}
	_, span := provider.TracerProvider().Tracer(tracing.ScopeName).Start(context.Background(), "reconcile.run")
	span.End()

	started := time.Now()
	_ = provider.Shutdown()
	if took := time.Since(started); took > metrics.ShutdownTimeout+time.Second {
		t.Errorf("끄는 데 %s 걸렸다. %s 안이어야 한다", took, metrics.ShutdownTimeout)
	}
}
