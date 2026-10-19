// billing-server/internal/obs/span_test.go

package obs_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.opentelemetry.io/otel/trace"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// span 이 걸려 있을 때 식별자가 그 span 을 따르는지 본다. span 은 SpanContext 만 실어 흉내 낸다.

const parentID = "00f067aa0ba902b7"

// spanned 는 traceparent 와 같은 span 이 걸린 context 다.
func spanned(t *testing.T) context.Context {
	t.Helper()
	tid, _ := trace.TraceIDFromHex(traceID)
	sid, _ := trace.SpanIDFromHex(parentID)
	spanContext := trace.NewSpanContext(trace.SpanContextConfig{TraceID: tid, SpanID: sid, TraceFlags: trace.FlagsSampled})
	return trace.ContextWithSpanContext(context.Background(), spanContext)
}

func TestRemoteParentReadsTheCallersSpan(t *testing.T) {
	parent, ok := obs.RemoteParent(traceparent)

	if !ok || !parent.IsRemote() || !parent.IsSampled() {
		t.Fatalf("부모 = %+v, 받았는가 = %v", parent, ok)
	}
	if parent.TraceID().String() != traceID || parent.SpanID().String() != parentID {
		t.Errorf("trace = %s, 부모 = %s", parent.TraceID(), parent.SpanID())
	}
}

func TestRemoteParentKeepsTheNotSampledFlag(t *testing.T) {
	// 따를지는 TracerProvider 가 정한다(tracing.Sampler). 여기서는 받은 그대로 둔다
	parent, ok := obs.RemoteParent("00-" + traceID + "-" + parentID + "-00")

	if !ok || parent.IsSampled() {
		t.Errorf("부모 = %+v, 받았는가 = %v", parent, ok)
	}
}

func TestRemoteParentRefusesWhatParseTraceparentRefuses(t *testing.T) {
	values := map[string]string{
		"없다":           "",
		"모르는 버전":       "01-" + traceID + "-" + parentID + "-01",
		"대문자":          "00-" + strings.ToUpper(traceID) + "-" + parentID + "-01",
		"trace-id 가 0": "00-" + strings.Repeat("0", 32) + "-" + parentID + "-01",
		"부모가 0":        "00-" + traceID + "-" + strings.Repeat("0", 16) + "-01",
		"줄바꿈을 붙였다":     traceparent + "\nX-Injected: 1",
		"길다":           traceparent + strings.Repeat("x", 500),
	}
	for name, value := range values {
		t.Run(name, func(t *testing.T) {
			if _, ok := obs.RemoteParent(value); ok {
				t.Errorf("RemoteParent(%q) 가 받았다", value)
			}
		})
	}
}

func TestTraceOfReadsTheSpan(t *testing.T) {
	got, ok := obs.TraceOf(spanned(t))

	if !ok || got != (obs.Trace{ID: traceID, Flags: "01"}) {
		t.Errorf("추적 = %+v, 있는가 = %v", got, ok)
	}
	if _, ok := obs.TraceOf(context.Background()); ok {
		t.Error("span 이 없는데 추적이 있다")
	}
}

func TestSetOutgoingHeadersNamesTheSpanAsParent(t *testing.T) {
	// 요청의 식별자보다 span 이 앞선다. 받는 서버의 span 이 이 span 아래에 붙는다
	ctx := obs.WithRequest(spanned(t), "request-12345", obs.NewTrace())
	request := httptest.NewRequestWithContext(ctx, http.MethodGet, "http://auth.invalid/jwks", nil)

	obs.SetOutgoingHeaders(request)

	if got := request.Header.Get(obs.TraceparentHeader); got != traceparent {
		t.Errorf("traceparent = %q, 기대 = %q", got, traceparent)
	}
}

func TestAJobUnderASpanUsesItsTrace(t *testing.T) {
	ids := obs.CurrentIDs(obs.WithJob(spanned(t), "job-12345"))

	if ids.JobID != "job-12345" || ids.Trace.ID != traceID {
		t.Errorf("식별자 = %+v", ids)
	}
}

func TestAJobStartedByARequestKeepsTheRequestsTrace(t *testing.T) {
	// 요청의 추적이 있으면 그것이 먼저다(요청이 띄운 작업)
	current := obs.NewTrace()
	ctx := obs.WithRequest(spanned(t), "request-12345", current)

	if got := obs.CurrentIDs(obs.WithJob(ctx, "job-12345")).Trace; got != current {
		t.Errorf("추적 = %+v, 기대 = %+v", got, current)
	}
}
