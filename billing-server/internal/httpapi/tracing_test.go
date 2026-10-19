// billing-server/internal/httpapi/tracing_test.go

package httpapi_test

import (
	"net/http"
	"strings"
	"testing"

	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing/tracingtest"
)

// 요청마다 서버 span 이 걸리고 로그의 trace_id 가 그 span 의 것인지 본다. span 은 메모리에 모은다(tracingtest).

// observedParentID 는 observedTraceparent 의 부모 span 이다.
const observedParentID = "00f067aa0ba902b7"

func TestARequestGetsAServerSpanNamedByItsRoute(t *testing.T) {
	recorder := tracingtest.New(t)
	server := observe(t, nil)
	orderID := "0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b"

	server.send(http.MethodGet, httpapi.APIPrefix+"/orders/"+orderID+"?secret=query-value")

	span := recorder.Only()
	route := httpapi.APIPrefix + "/orders/:id"
	if span.Name() != "GET "+route || span.SpanKind() != trace.SpanKindServer {
		t.Errorf("span = %s, 종류 = %v", span.Name(), span.SpanKind())
	}
	attributes := tracingtest.Attributes(span)
	if attributes["http.route"].AsString() != route || attributes["http.request.method"].AsString() != http.MethodGet ||
		attributes["http.response.status_code"].AsInt64() == 0 {
		t.Errorf("속성 = %v", attributes)
	}
	// 주소에 든 주문 번호와 주소 뒤의 값은 싣지 않는다
	for key, value := range attributes {
		if strings.Contains(value.Emit(), orderID) || strings.Contains(value.Emit(), "query-value") {
			t.Errorf("실제 주소가 %s 에 실렸다: %s", key, value.Emit())
		}
	}
}

func TestTheLogTraceIDIsTheSpans(t *testing.T) {
	// 로그에서 Tempo 로, Tempo 에서 로그로 같은 번호로 건너간다
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	span := recorder.Only()
	if got := server.finished(t)["trace_id"]; got != span.SpanContext().TraceID().String() {
		t.Errorf("trace_id = %v, span = %s", got, span.SpanContext().TraceID())
	}
	// 응답의 X-Request-ID 로 Tempo 에서 그 요청을 찾는다
	if got := tracingtest.Attributes(span)[tracing.AttributeRequestID].AsString(); got != requestIDOf(response) {
		t.Errorf("span 의 request_id = %q, 응답 = %q", got, requestIDOf(response))
	}
}

func TestTheCallersSpanBecomesTheParent(t *testing.T) {
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token", obs.TraceparentHeader, observedTraceparent)

	span := recorder.Only()
	if span.SpanContext().TraceID().String() != observedTraceID || span.Parent().SpanID().String() != observedParentID ||
		!span.Parent().IsRemote() {
		t.Errorf("trace = %s, 부모 = %s", span.SpanContext().TraceID(), span.Parent().SpanID())
	}
	if got := server.finished(t)["trace_id"]; got != observedTraceID {
		t.Errorf("trace_id = %v", got)
	}
}

func TestACallerThatDoesNotRecordIsStillRecorded(t *testing.T) {
	// 다른 서버들은 span 을 내보내지 않아 flags 00 을 보낸다. 그것을 따르면 결제 서버의 span 이 다 버려진다
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token",
		obs.TraceparentHeader, "00-"+observedTraceID+"-"+observedParentID+"-00")

	if span := recorder.Only(); span.SpanContext().TraceID().String() != observedTraceID {
		t.Errorf("trace = %s", span.SpanContext().TraceID())
	}
}

func TestAMalformedTraceparentStartsANewSpanTrace(t *testing.T) {
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token",
		obs.TraceparentHeader, "00-"+strings.ToUpper(observedTraceID)+"-"+observedParentID+"-01")

	span := recorder.Only()
	if span.Parent().IsValid() || strings.EqualFold(span.SpanContext().TraceID().String(), observedTraceID) {
		t.Errorf("틀린 traceparent 를 부모로 받았다: %s", span.Parent().SpanID())
	}
}

func TestProbesGetNoSpan(t *testing.T) {
	// 10초마다 오는 확인이 추적을 메우지 않는다
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	server.send(http.MethodGet, "/health")
	server.send(http.MethodGet, "/health/ready")

	if names := recorder.Names(); len(names) != 0 {
		t.Errorf("상태 확인에 span 이 걸렸다: %v", names)
	}
}

func TestAServerErrorMarksTheSpan(t *testing.T) {
	recorder := tracingtest.New(t)
	server := observe(t, &panickingWallet{})

	server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	span := recorder.Only()
	if span.Status().Code != codes.Error || tracingtest.Attributes(span)["http.response.status_code"].AsInt64() != http.StatusInternalServerError {
		t.Errorf("상태 = %v, 속성 = %v", span.Status(), tracingtest.Attributes(span))
	}
	// 패닉의 글은 싣지 않는다
	if strings.Contains(span.Status().Description, secretInError) || len(span.Events()) != 0 {
		t.Errorf("패닉의 내용이 span 에 실렸다: %v %v", span.Status(), span.Events())
	}
}

func TestAnUnmatchedAddressIsMarkedButNotAnError(t *testing.T) {
	recorder := tracingtest.New(t)
	server := observe(t, nil)

	server.send(http.MethodGet, "/no/such/address/0b9f5e0c")

	span := recorder.Only()
	if span.Name() != "GET (unmatched)" || span.Status().Code == codes.Error {
		t.Errorf("span = %s, 상태 = %v", span.Name(), span.Status())
	}
}
