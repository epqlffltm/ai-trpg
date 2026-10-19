// billing-server/internal/httpapi/tracing.go

package httpapi

import (
	"context"
	"net/http"

	"github.com/gin-gonic/gin"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// 요청마다 서버 span 을 건다. 이름은 메서드와 주소의 틀이다(GET /api/v1/billing/orders/:id). 실제 주소가 아니다.
// span 을 내보낼 곳이 없으면(tracing 이 noop) 아무것도 남지 않고, 로그의 trace_id 는 지금처럼 정해진다.
//
// 받은 traceparent 가 형식에 맞으면 그 아래에 붙는다(부른 서버의 span 이 부모가 된다). 받는 규칙은 internal/obs 와 같다.
// 상태 확인(/health, /health/ready)은 span 을 걸지 않는다. 10초마다 오는 확인이 추적을 메우지 않게 한다.
// span 에는 메서드, 주소의 틀, 상태 코드만 싣는다. 머리말, 주소 뒤의 값, 본문은 싣지 않는다.

// requestSpan 은 요청에 서버 span 을 거는 미들웨어다. 가장 먼저 붙인다. 뒤의 로그와 쿼리가 이 span 아래에 놓인다.
func requestSpan() gin.HandlerFunc {
	return func(c *gin.Context) {
		if isProbe(c.FullPath()) {
			c.Next()
			return
		}
		ctx, span := tracing.Tracer().Start(parentContext(c.Request), serverSpanName(c),
			trace.WithSpanKind(trace.SpanKindServer),
			trace.WithAttributes(
				attribute.String("http.request.method", c.Request.Method),
				attribute.String("http.route", routeOf(c)),
			))
		defer span.End()
		c.Request = c.Request.WithContext(ctx)
		c.Next()
		finishServerSpan(span, c.Writer.Status())
	}
}

// parentContext 는 span 의 부모를 실은 context 다. 받은 traceparent 가 틀렸으면 부모 없이 새 추적을 시작한다.
func parentContext(request *http.Request) context.Context {
	ctx := request.Context()
	if parent, ok := obs.RemoteParent(singleHeader(request, obs.TraceparentHeader)); ok {
		return trace.ContextWithRemoteSpanContext(ctx, parent)
	}
	return ctx
}

// routeOf 는 요청이 맞은 주소의 틀이다. 맞은 것이 없으면(404) 표시(unmatchedRoute)다. 로그의 route 칸과 같다.
func routeOf(c *gin.Context) string {
	if route := c.FullPath(); route != "" {
		return route
	}
	return unmatchedRoute
}

// serverSpanName 은 서버 span 의 이름이다.
func serverSpanName(c *gin.Context) string {
	return c.Request.Method + " " + routeOf(c)
}

// tagRequestSpan 은 서버 span 에 요청 식별자를 싣는다. 응답의 X-Request-ID 로 Tempo 에서 그 요청을 찾는다.
// span 이 없으면(상태 확인, 추적을 내보내지 않는 PC) 아무것도 하지 않는다.
func tagRequestSpan(ctx context.Context, requestID string) {
	trace.SpanFromContext(ctx).SetAttributes(attribute.String(tracing.AttributeRequestID, requestID))
}

// finishServerSpan 은 상태 코드를 적는다. 서버의 잘못(5xx)만 오류로 표시한다. 4xx 는 요청의 잘못이다(로그의 수준과 같다).
func finishServerSpan(span trace.Span, status int) {
	span.SetAttributes(attribute.Int("http.response.status_code", status))
	if status >= http.StatusInternalServerError {
		span.SetStatus(codes.Error, http.StatusText(status))
	}
}
