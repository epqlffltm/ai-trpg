// billing-server/internal/obs/span.go

package obs

import (
	"context"
	"encoding/hex"

	"go.opentelemetry.io/otel/trace"
)

// 추적(span)과 이 패키지의 식별자를 잇는다. span 을 만들고 내보내는 일은 internal/tracing 이 한다.
// span 이 있으면 로그의 trace_id 와 다른 서버에 넘기는 traceparent 가 그 span 의 것이 된다.
// span 이 없으면(내보낼 곳이 없는 PC) 지금처럼 이 패키지가 식별자를 정한다.

// RemoteParent 는 받은 traceparent 를 span 의 부모로 바꾼다. 받는 규칙은 ParseTraceparent 와 같다.
// 형식에 맞지 않으면 false 다. 그때는 부모 없이 새 추적을 시작한다.
func RemoteParent(value string) (trace.SpanContext, bool) {
	parts, ok := traceparentParts(value)
	if !ok {
		return trace.SpanContext{}, false
	}
	traceID, traceErr := trace.TraceIDFromHex(parts[1])
	spanID, spanErr := trace.SpanIDFromHex(parts[2])
	flags, flagsErr := hex.DecodeString(parts[3])
	if traceErr != nil || spanErr != nil || flagsErr != nil {
		return trace.SpanContext{}, false
	}
	parent := trace.NewSpanContext(trace.SpanContextConfig{
		TraceID:    traceID,
		SpanID:     spanID,
		TraceFlags: trace.TraceFlags(flags[0]),
		Remote:     true,
	})
	return parent, parent.IsValid()
}

// TraceOf 는 context 에 걸린 span 의 추적이다. span 이 없으면 false 다.
func TraceOf(ctx context.Context) (Trace, bool) {
	spanContext := trace.SpanContextFromContext(ctx)
	if !spanContext.IsValid() {
		return Trace{}, false
	}
	return Trace{ID: spanContext.TraceID().String(), Flags: spanContext.TraceFlags().String()}, true
}

// spanTraceparent 는 그 span 을 부모로 하는 traceparent 다. 받는 서버의 span 이 이 span 의 아래에 붙는다.
func spanTraceparent(spanContext trace.SpanContext) string {
	return "00-" + spanContext.TraceID().String() + "-" + spanContext.SpanID().String() + "-" + spanContext.TraceFlags().String()
}
