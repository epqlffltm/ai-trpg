// billing-server/internal/tracing/transport.go

package tracing

import (
	"net/http"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// 다른 곳을 부르는 HTTP 요청에 client span 을 건다. span 에는 메서드, 상대의 호스트 이름, 상태 코드만 싣는다.
// 주소의 경로는 싣지 않는다. 결제 대행사의 주소에는 결제 번호(paymentKey)가 들어 있다(docs/observability.md 의 "민감정보").
//
// 부모 span 이 기록 중일 때만 span 을 건다. 요청이나 작업 밖에서 도는 호출(끊긴 세션의 목록을 30초마다 받는 것)은
// 저마다 새 추적이 되어 Tempo 를 메운다.

// spanName 은 client span 의 이름이다. 메서드만 붙인다(HTTP GET). 주소는 값의 종류가 끝없이 늘어 이름에 넣지 않는다.
const spanName = "HTTP "

// transport 는 base 를 감싸 요청마다 client span 을 거는 것이다.
type transport struct {
	base      http.RoundTripper
	propagate bool
}

// Transport 는 base 를 감싼 것을 돌려준다. base 가 nil 이면 http.DefaultTransport 다.
// propagate 면 우리 서버끼리의 요청이라 traceparent 를 붙인다(받는 서버의 span 이 이 span 아래에 붙는다).
// 우리 서버가 아닌 곳(결제 대행사)은 false 다. 내부의 흐름을 밖에 알릴 까닭이 없다.
func Transport(base http.RoundTripper, propagate bool) http.RoundTripper {
	if base == nil {
		base = http.DefaultTransport
	}
	return transport{base: base, propagate: propagate}
}

// RoundTrip 은 요청 하나를 보낸다. 부모 span 이 없으면 span 없이 보낸다.
func (t transport) RoundTrip(request *http.Request) (*http.Response, error) {
	if !trace.SpanFromContext(request.Context()).IsRecording() {
		return t.base.RoundTrip(t.prepared(request))
	}
	ctx, span := Tracer().Start(request.Context(), spanName+request.Method,
		trace.WithSpanKind(trace.SpanKindClient),
		trace.WithAttributes(
			attribute.String("http.request.method", request.Method),
			attribute.String("server.address", request.URL.Hostname()),
		))
	defer span.End()
	response, err := t.base.RoundTrip(t.prepared(request.WithContext(ctx)))
	recordResponse(span, response, err)
	return response, err
}

// prepared 는 보낼 요청이다. propagate 면 복사본에 traceparent 를 붙인다. RoundTripper 는 받은 요청을 고치지 않는다.
func (t transport) prepared(request *http.Request) *http.Request {
	if !t.propagate {
		return request
	}
	clone := request.Clone(request.Context())
	obs.SetOutgoingHeaders(clone)
	return clone
}

// recordResponse 는 답을 span 에 적는다. 오류의 글은 싣지 않는다(주소가 들어 있을 수 있다).
func recordResponse(span trace.Span, response *http.Response, err error) {
	if err != nil {
		span.SetStatus(codes.Error, "요청을 보내지 못했다")
		return
	}
	span.SetAttributes(attribute.Int("http.response.status_code", response.StatusCode))
	if response.StatusCode >= http.StatusInternalServerError {
		span.SetStatus(codes.Error, http.StatusText(response.StatusCode))
	}
}
