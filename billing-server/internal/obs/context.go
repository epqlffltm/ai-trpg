// billing-server/internal/obs/context.go

package obs

import (
	"context"
	"net/http"

	"go.opentelemetry.io/otel/trace"
)

// idsKey 는 context 에 식별자를 넣는 열쇠다. 이 패키지만 쓰는 타입이라 다른 값과 겹치지 않는다.
type idsKey struct{}

// IDs 는 지금 처리 중인 일을 가리키는 식별자들이다. 없는 것은 빈 글자다.
//
// 이 값들은 로그를 찾는 데만 쓴다. 누구의 요청인지, 무엇을 해도 되는지를 판단하는 데 쓰지 않는다.
// 요청 식별자는 부르는 쪽이 정할 수 있는 값이다.
type IDs struct {
	// RequestID 는 이 서버가 받은 HTTP 요청 하나의 식별자다.
	RequestID string
	// Trace 는 여러 서버를 거치는 흐름이다.
	Trace Trace
	// JobID 는 요청과 따로 도는 작업 하나의 식별자다. 결제 서버에는 아직 그런 작업이 없다.
	JobID string
}

// WithRequest 는 요청의 식별자를 실은 context 를 돌려준다.
func WithRequest(ctx context.Context, requestID string, trace Trace) context.Context {
	return context.WithValue(ctx, idsKey{}, IDs{RequestID: requestID, Trace: trace})
}

// WithJob 은 작업의 식별자를 실은 context 를 돌려준다. 요청의 식별자는 떼고, 추적은 이어 간다.
// 작업은 그것을 띄운 요청이 끝난 뒤에도 돈다. 요청 식별자를 달고 있으면 끝난 요청의 일로 보인다.
// 이어 갈 추적이 없으면 작업의 span 의 추적을, 그것도 없으면 새 추적을 쓴다.
func WithJob(ctx context.Context, jobID string) context.Context {
	return context.WithValue(ctx, idsKey{}, IDs{JobID: jobID, Trace: jobTrace(ctx)})
}

// jobTrace 는 작업이 속할 추적이다. 요청의 것, 작업의 span 의 것, 새것의 차례로 고른다.
func jobTrace(ctx context.Context) Trace {
	if current := CurrentIDs(ctx).Trace; current.ID != "" {
		return current
	}
	if spanned, ok := TraceOf(ctx); ok {
		return spanned
	}
	return NewTrace()
}

// CurrentIDs 는 context 에 실린 식별자들을 돌려준다. 없으면 빈 값이다.
func CurrentIDs(ctx context.Context) IDs {
	if ctx == nil {
		return IDs{}
	}
	ids, _ := ctx.Value(idsKey{}).(IDs)
	return ids
}

// SetOutgoingHeaders 는 우리 서버끼리 부르는 요청에 추적을 이어 붙인다. 요청의 context 에 추적이 없으면 아무것도 하지 않는다.
// span 이 걸려 있으면 그 span 을 부모로 붙인다. 받는 서버의 span 이 그 아래에 이어진다.
//
// 요청 식별자(X-Request-ID)는 넘기지 않는다. 받는 서버가 제 요청의 식별자를 따로 만든다. 둘은 trace_id 로 이어진다.
// 우리 서버가 아닌 곳(결제 대행사)을 부르는 요청에는 쓰지 않는다. 내부의 흐름을 밖에 알릴 까닭이 없다.
func SetOutgoingHeaders(request *http.Request) {
	if spanContext := trace.SpanContextFromContext(request.Context()); spanContext.IsValid() {
		request.Header.Set(TraceparentHeader, spanTraceparent(spanContext))
		return
	}
	current := CurrentIDs(request.Context()).Trace
	if current.ID == "" {
		return
	}
	request.Header.Set(TraceparentHeader, FormatTraceparent(current))
}
