// billing-server/internal/obs/ids_test.go

package obs_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

const (
	traceID     = "4bf92f3577b34da6a3ce929d0e0e4736"
	traceparent = "00-" + traceID + "-00f067aa0ba902b7-01"
)

var (
	uuidPattern    = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	traceIDPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)
)

func TestRequestIDFromKeepsWellFormedValues(t *testing.T) {
	values := []string{
		"0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b",
		"req_12345678",
		"A1b2.C3d4-E5f6",
		strings.Repeat("a", 8),
		strings.Repeat("a", 64),
	}
	for _, value := range values {
		if got := obs.RequestIDFrom(value); got != value {
			t.Errorf("RequestIDFrom(%q) = %q. 그대로 써야 한다", value, got)
		}
	}
}

func TestRequestIDFromReplacesMalformedValues(t *testing.T) {
	values := map[string]string{
		"없다":        "",
		"짧다":        "short",
		"길다":        strings.Repeat("a", 65),
		"아주 길다":     strings.Repeat("a", 5000),
		"공백":        "has space in it",
		"줄바꿈":       "line\nbreak-12345",
		"캐리지 리턴":    "carriage\rreturn-1",
		"탭":         "tab\tinside-12345",
		"NUL":       "null\x00byte-12345",
		"ESC":       "escape\x1b[31m-12345",
		"영문자가 아니다":  "한글로-된-식별자-12345",
		"JSON":      `{"injected":"json"}`,
		"쌍반점":       "semi;colon-12345",
		"빗금":        "slash/inside-12345",
		"끝에 줄바꿈":    "request-12345\n",
		"가짜 줄을 붙였다": "request-12345\r\n{\"level\":\"error\"}",
	}
	for name, value := range values {
		t.Run(name, func(t *testing.T) {
			if _, ok := obs.AcceptRequestID(value); ok {
				t.Fatalf("AcceptRequestID(%q) 가 받았다", value)
			}
			replaced := obs.RequestIDFrom(value)
			// 고쳐 쓰지 않고 새로 만든다. 받은 값의 어느 부분도 남지 않는다
			if !uuidPattern.MatchString(replaced) {
				t.Errorf("새 식별자가 UUID 가 아니다: %q", replaced)
			}
		})
	}
}

func TestNewRequestIDsDiffer(t *testing.T) {
	if obs.NewRequestID() == obs.NewRequestID() {
		t.Error("새로 만든 식별자 둘이 같다")
	}
}

func TestTraceFromContinuesTheCallersTrace(t *testing.T) {
	trace, ok := obs.ParseTraceparent(traceparent)

	if !ok || trace.ID != traceID || trace.Flags != "01" {
		t.Errorf("추적 = %+v, 받았는가 = %v", trace, ok)
	}
	if obs.TraceFrom(traceparent) != trace {
		t.Error("부른 쪽의 추적을 이어 가지 않았다")
	}
}

func TestTraceFromStartsANewTraceOnMalformedValues(t *testing.T) {
	values := map[string]string{
		"없다":            "",
		"아무 글자":         "garbage",
		"trace-id 뿐이다":  traceID,
		"모르는 버전":        "01-" + traceID + "-00f067aa0ba902b7-01",
		"버전 ff":         "ff-" + traceID + "-00f067aa0ba902b7-01",
		"대문자":           "00-" + strings.ToUpper(traceID) + "-00f067aa0ba902b7-01",
		"trace-id 가 짧다": "00-" + traceID[:31] + "-00f067aa0ba902b7-01",
		"부모가 짧다":        "00-" + traceID + "-00f067aa0ba902-01",
		"trace-id 가 0":  "00-" + strings.Repeat("0", 32) + "-00f067aa0ba902b7-01",
		"부모가 0":         "00-" + traceID + "-" + strings.Repeat("0", 16) + "-01",
		"줄바꿈을 붙였다":      traceparent + "\nX-Injected: 1",
		"길다":            traceparent + strings.Repeat("x", 500),
	}
	for name, value := range values {
		t.Run(name, func(t *testing.T) {
			if _, ok := obs.ParseTraceparent(value); ok {
				t.Fatalf("ParseTraceparent(%q) 가 받았다", value)
			}
			trace := obs.TraceFrom(value)
			if !traceIDPattern.MatchString(trace.ID) || trace.ID == traceID {
				t.Errorf("새 추적이 아니다: %+v", trace)
			}
		})
	}
}

func TestFormatTraceparentKeepsTheTraceAndRenewsTheParent(t *testing.T) {
	trace := obs.Trace{ID: traceID, Flags: "01"}

	first := obs.FormatTraceparent(trace)
	second := obs.FormatTraceparent(trace)

	// 받는 쪽이 다시 읽을 수 있는 모양이다
	if parsed, ok := obs.ParseTraceparent(first); !ok || parsed != trace {
		t.Errorf("만든 값을 다시 읽지 못했다: %q", first)
	}
	if first == second {
		t.Error("부모 식별자가 부를 때마다 새로 만들어지지 않았다")
	}
}

func TestContextCarriesTheRequestIDs(t *testing.T) {
	trace := obs.NewTrace()

	if got := obs.CurrentIDs(context.Background()); got != (obs.IDs{}) {
		t.Errorf("아무것도 걸지 않았는데 식별자가 있다: %+v", got)
	}
	ctx := obs.WithRequest(context.Background(), "request-12345", trace)
	if got := obs.CurrentIDs(ctx); got.RequestID != "request-12345" || got.Trace != trace || got.JobID != "" {
		t.Errorf("식별자 = %+v", got)
	}
	// 취소만 떼어 낸 context 에도 식별자가 따라간다. 키를 다시 가져오는 일이 그렇게 돈다
	if got := obs.CurrentIDs(context.WithoutCancel(ctx)); got.RequestID != "request-12345" {
		t.Errorf("식별자가 따라가지 않았다: %+v", got)
	}
}

func TestJobContextDropsTheRequestIDAndKeepsTheTrace(t *testing.T) {
	trace := obs.NewTrace()
	request := obs.WithRequest(context.Background(), "request-12345", trace)

	spawned := obs.CurrentIDs(obs.WithJob(request, "job-12345"))
	alone := obs.CurrentIDs(obs.WithJob(context.Background(), "job-67890"))

	if spawned.RequestID != "" || spawned.JobID != "job-12345" || spawned.Trace != trace {
		t.Errorf("요청이 띄운 작업의 식별자 = %+v", spawned)
	}
	// 요청 없이 시작한 작업은 새 추적을 시작한다
	if alone.JobID != "job-67890" || !traceIDPattern.MatchString(alone.Trace.ID) {
		t.Errorf("혼자 시작한 작업의 식별자 = %+v", alone)
	}
}

func TestSetOutgoingHeadersPassesTheTraceOnly(t *testing.T) {
	trace := obs.Trace{ID: traceID, Flags: "01"}
	ctx := obs.WithRequest(context.Background(), "request-12345", trace)
	request := httptest.NewRequestWithContext(ctx, http.MethodGet, "http://auth.invalid/jwks", nil)

	obs.SetOutgoingHeaders(request)

	if parsed, ok := obs.ParseTraceparent(request.Header.Get(obs.TraceparentHeader)); !ok || parsed != trace {
		t.Errorf("traceparent = %q", request.Header.Get(obs.TraceparentHeader))
	}
	// 받는 서버가 제 요청의 식별자를 따로 만든다
	if request.Header.Get(obs.RequestIDHeader) != "" {
		t.Error("요청의 식별자를 다른 서버에 넘겼다")
	}
}

func TestSetOutgoingHeadersAddsNothingOutsideARequest(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "http://auth.invalid/jwks", nil)

	obs.SetOutgoingHeaders(request)

	if request.Header.Get(obs.TraceparentHeader) != "" {
		t.Error("추적이 없는데 traceparent 를 붙였다")
	}
}
