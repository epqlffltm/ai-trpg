// billing-server/internal/obs/ids.go

// Package obs 는 결제 서버의 로그를 네 서버 공통 규격으로 내보낸다.
// 요청을 가리키는 식별자를 정하고(ids.go), 요청이 처리되는 동안 들고 다니고(context.go),
// 민감한 값을 가리고(redact.go), 한 줄의 JSON 으로 적는다(handler.go).
//
// 규격은 저장소 루트의 docs/observability.md 에 있다. 칸의 이름과 뜻을 바꾸려면 그 문서부터 고친다.
// 다른 서버(auth-server, game-server, board-server)의 같은 이름의 코드가 같은 규칙을 따른다.
//
// 이 패키지는 gin 을 모른다. HTTP 요청에 붙이는 일은 internal/httpapi 가 한다.
package obs

import (
	"crypto/rand"
	"encoding/hex"
	"regexp"

	"github.com/google/uuid"
)

const (
	// RequestIDHeader 는 요청의 식별자를 주고받는 머리말이다. 받은 것이 형식에 맞으면 그대로 쓰고, 응답에 돌려준다.
	RequestIDHeader = "X-Request-ID"
	// TraceparentHeader 는 여러 서버를 거치는 흐름의 식별자를 주고받는 머리말이다. W3C Trace Context 의 것이다.
	TraceparentHeader = "traceparent"
	// maxHeaderLength 는 식별자 머리말로 읽는 가장 긴 길이다. 넘으면 형식을 보지 않고 버린다.
	maxHeaderLength = 128
	// sampledOff 는 새로 시작한 추적의 flags 다. 추적을 모으는 것이 아직 없으므로 "기록하지 않음"이다.
	sampledOff = "00"
)

var (
	// requestIDPattern 은 받아들이는 요청 식별자의 모양이다. 영문자, 숫자, 점, 밑줄, 붙임표로 8~64자다.
	// 줄바꿈, 제어 문자, 따옴표, 공백이 없다. 그래서 로그에 적어도 줄이 깨지거나 가짜 줄이 끼어들지 않는다.
	requestIDPattern = regexp.MustCompile(`^[A-Za-z0-9._-]{8,64}$`)
	// traceparentPattern 은 받아들이는 traceparent 의 모양이다. 버전 00 만 받는다.
	// 00-<trace-id 32자>-<parent-id 16자>-<flags 2자>, 모두 소문자 16진수다.
	traceparentPattern = regexp.MustCompile(`^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$`)
)

const (
	// 0 으로만 된 식별자는 "없다"는 뜻이라 받지 않는다(W3C Trace Context)
	zeroTraceID  = "00000000000000000000000000000000"
	zeroParentID = "0000000000000000"
)

// Trace 는 여러 서버를 거치는 한 흐름이다.
type Trace struct {
	// ID 는 흐름의 식별자다. 소문자 16진수 32자다. 로그의 trace_id 칸에 적는다.
	ID string
	// Flags 는 부른 쪽이 정한 표시다(기록할지 말지). 다음 서버에 그대로 넘긴다.
	Flags string
}

// AcceptRequestID 는 받은 값이 요청 식별자로 쓸 수 있는 모양인지 본다. 못 쓰면 false 다.
func AcceptRequestID(value string) (string, bool) {
	if len(value) > maxHeaderLength || !requestIDPattern.MatchString(value) {
		return "", false
	}
	return value, true
}

// NewRequestID 는 새 요청 식별자를 만든다. UUID v4 다.
func NewRequestID() string {
	return uuid.NewString()
}

// RequestIDFrom 은 요청이 쓸 식별자를 정한다. 받은 것이 형식에 맞으면 그것, 아니면 새것이다.
// 틀린 값을 고쳐 쓰지 않는다. 받은 값의 어느 부분도 남기지 않는다.
func RequestIDFrom(value string) string {
	if accepted, ok := AcceptRequestID(value); ok {
		return accepted
	}
	return NewRequestID()
}

// ParseTraceparent 는 traceparent 머리말에서 추적을 읽는다. 형식에 맞지 않으면 false 다.
func ParseTraceparent(value string) (Trace, bool) {
	parts, ok := traceparentParts(value)
	if !ok {
		return Trace{}, false
	}
	return Trace{ID: parts[1], Flags: parts[3]}, true
}

// traceparentParts 는 traceparent 를 버전, trace-id, parent-id, flags 로 나눈다(parts[1:4]). 받지 않는 모양이면 false 다.
// 길거나, 모양이 틀리거나, 0 으로만 된 식별자면 받지 않는다. ParseTraceparent 와 RemoteParent(span.go)가 같은 규칙을 쓴다.
func traceparentParts(value string) ([]string, bool) {
	if len(value) > maxHeaderLength {
		return nil, false
	}
	parts := traceparentPattern.FindStringSubmatch(value)
	if parts == nil || parts[1] == zeroTraceID || parts[2] == zeroParentID {
		return nil, false
	}
	return parts, true
}

// NewTrace 는 새 추적을 시작한다.
func NewTrace() Trace {
	return Trace{ID: randomHex(16), Flags: sampledOff}
}

// TraceFrom 은 요청이 속할 추적을 정한다. 부른 쪽이 준 것이 형식에 맞으면 이어 가고, 아니면 새로 시작한다.
func TraceFrom(value string) Trace {
	if trace, ok := ParseTraceparent(value); ok {
		return trace
	}
	return NewTrace()
}

// FormatTraceparent 는 다른 서버에 보낼 traceparent 값을 만든다.
// 추적의 식별자와 flags 는 그대로 두고, 부모 식별자는 부를 때마다 새로 만든다.
func FormatTraceparent(trace Trace) string {
	return "00-" + trace.ID + "-" + randomHex(8) + "-" + trace.Flags
}

// randomHex 는 n 바이트의 난수를 소문자 16진수로 돌려준다.
func randomHex(n int) string {
	buffer := make([]byte, n)
	// crypto/rand.Read 는 실패하지 않는다(Go 1.24 부터). 난수를 얻지 못하면 프로그램을 멈춘다
	_, _ = rand.Read(buffer)
	return hex.EncodeToString(buffer)
}
