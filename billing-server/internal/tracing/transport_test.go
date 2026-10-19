// billing-server/internal/tracing/transport_test.go

package tracing_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing/tracingtest"
)

// 다른 곳을 부르는 요청에 client span 이 걸리는지 본다. 상대는 이 테스트의 HTTP 서버다.

// secretPath 는 주소에 든 결제 번호를 흉내 낸다. span 에 실리면 안 된다.
const secretPath = "/v1/payments/tgen_secret_payment_key"

// receiver 는 받은 요청의 traceparent 를 적어 둔다. 서버의 goroutine 이 적고 테스트가 읽는다.
type receiver struct {
	mu          sync.Mutex
	traceparent string
}

// record 는 받은 traceparent 를 적는다.
func (r *receiver) record(value string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.traceparent = value
}

// received 는 적어 둔 traceparent 다.
func (r *receiver) received() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.traceparent
}

// called 는 받은 요청의 traceparent 를 적어 두고 status 로 답하는 서버다.
func called(t *testing.T, status int) (*httptest.Server, *receiver) {
	t.Helper()
	got := &receiver{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.record(r.Header.Get(obs.TraceparentHeader))
		w.WriteHeader(status)
	}))
	t.Cleanup(server.Close)
	return server, got
}

// call 은 Transport 를 단 client 로 ctx 아래에서 부른다. 보낸 요청(고쳐지지 않았는지 보려고)도 돌려준다.
func call(t *testing.T, ctx context.Context, url string, propagate bool) (*http.Request, error) {
	t.Helper()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		t.Fatalf("요청을 만들지 못했다: %v", err)
	}
	client := &http.Client{Transport: tracing.Transport(nil, propagate)}
	response, err := client.Do(request)
	if err == nil {
		_ = response.Body.Close()
	}
	return request, err
}

func TestACallUnderASpanGetsAClientSpan(t *testing.T) {
	recorder := tracingtest.New(t)
	server, _ := called(t, http.StatusOK)
	ctx, parent := recorder.Parent(context.Background())

	if _, err := call(t, ctx, server.URL+secretPath, true); err != nil {
		t.Fatalf("부르지 못했다: %v", err)
	}

	span := recorder.Only()
	attributes := tracingtest.Attributes(span)
	if span.Name() != "HTTP GET" || span.SpanKind() != trace.SpanKindClient {
		t.Errorf("span = %s, 종류 = %v", span.Name(), span.SpanKind())
	}
	if span.Parent().SpanID() != parent.SpanContext().SpanID() {
		t.Error("부모 span 아래에 놓이지 않았다")
	}
	if attributes["server.address"].AsString() != "127.0.0.1" || attributes["http.response.status_code"].AsInt64() != http.StatusOK {
		t.Errorf("속성 = %v", attributes)
	}
	if span.Status().Code == codes.Error {
		t.Errorf("잘 끝난 호출이 오류로 표시됐다: %v", span.Status())
	}
}

func TestTheAddressPathIsNeverRecorded(t *testing.T) {
	recorder := tracingtest.New(t)
	server, _ := called(t, http.StatusOK)
	ctx, _ := recorder.Parent(context.Background())

	_, _ = call(t, ctx, server.URL+secretPath, false)

	span := recorder.Only()
	for key, value := range tracingtest.Attributes(span) {
		if strings.Contains(value.Emit(), "tgen_secret_payment_key") {
			t.Errorf("주소가 %s 에 실렸다: %s", key, value.Emit())
		}
	}
}

func TestOurServersReceiveTheClientSpanAsParent(t *testing.T) {
	recorder := tracingtest.New(t)
	server, sent := called(t, http.StatusOK)
	ctx, _ := recorder.Parent(context.Background())

	request, _ := call(t, ctx, server.URL, true)

	span := recorder.Only()
	want := "00-" + span.SpanContext().TraceID().String() + "-" + span.SpanContext().SpanID().String() + "-01"
	if sent.received() != want {
		t.Errorf("traceparent = %q, 기대 = %q", sent.received(), want)
	}
	// RoundTripper 는 받은 요청을 고치지 않는다
	if request.Header.Get(obs.TraceparentHeader) != "" {
		t.Error("부른 쪽의 요청에 머리말을 붙였다")
	}
}

func TestOutsideServersReceiveNoTraceparent(t *testing.T) {
	recorder := tracingtest.New(t)
	server, sent := called(t, http.StatusOK)
	ctx, _ := recorder.Parent(context.Background())

	_, _ = call(t, ctx, server.URL, false)

	if sent.received() != "" {
		t.Errorf("결제 대행사 쪽에 traceparent 를 보냈다: %q", sent.received())
	}
	if len(recorder.Ended()) != 1 {
		t.Errorf("span 은 걸려야 한다: %v", recorder.Names())
	}
}

func TestACallWithoutAParentGetsNoSpan(t *testing.T) {
	// 요청이나 작업 밖에서 도는 호출(끊긴 세션의 목록을 받는 것)은 저마다 새 추적이 되어 Tempo 를 메운다
	recorder := tracingtest.New(t)
	server, sent := called(t, http.StatusOK)
	current := obs.Trace{ID: "4bf92f3577b34da6a3ce929d0e0e4736", Flags: "01"}
	ctx := obs.WithRequest(context.Background(), "request-12345", current)

	_, _ = call(t, ctx, server.URL, true)

	if len(recorder.Ended()) != 0 {
		t.Errorf("부모 없이 span 이 걸렸다: %v", recorder.Names())
	}
	// span 이 없어도 추적은 지금처럼 잇는다
	if parsed, ok := obs.ParseTraceparent(sent.received()); !ok || parsed != current {
		t.Errorf("traceparent = %q", sent.received())
	}
}

func TestAServerErrorMarksTheSpan(t *testing.T) {
	recorder := tracingtest.New(t)
	server, _ := called(t, http.StatusServiceUnavailable)
	ctx, _ := recorder.Parent(context.Background())

	_, _ = call(t, ctx, server.URL, true)

	if span := recorder.Only(); span.Status().Code != codes.Error {
		t.Errorf("503 이 오류로 표시되지 않았다: %v", span.Status())
	}
}

func TestAClientErrorDoesNotMarkTheSpan(t *testing.T) {
	// 4xx 는 부른 쪽이 답을 보고 다룬다(없는 결제, 거절된 카드)
	recorder := tracingtest.New(t)
	server, _ := called(t, http.StatusNotFound)
	ctx, _ := recorder.Parent(context.Background())

	_, _ = call(t, ctx, server.URL, true)

	if span := recorder.Only(); span.Status().Code == codes.Error {
		t.Errorf("404 가 오류로 표시됐다: %v", span.Status())
	}
}

func TestAnUnreachableServerMarksTheSpan(t *testing.T) {
	recorder := tracingtest.New(t)
	server, _ := called(t, http.StatusOK)
	url := server.URL
	server.Close()
	ctx, _ := recorder.Parent(context.Background())

	if _, err := call(t, ctx, url, true); err == nil {
		t.Fatal("닫힌 서버에 닿았다")
	}

	span := recorder.Only()
	if span.Status().Code != codes.Error || strings.Contains(span.Status().Description, "127.0.0.1") {
		t.Errorf("상태 = %v. 오류이고 주소가 없어야 한다", span.Status())
	}
}
