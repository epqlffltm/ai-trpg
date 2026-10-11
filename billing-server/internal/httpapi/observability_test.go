// billing-server/internal/httpapi/observability_test.go

package httpapi_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 요청마다 식별자가 걸리고 끝나면 공통 규격의 한 줄이 남는지 본다. 규격은 저장소 루트의 docs/observability.md 에 있다.
// 서버가 쓰는 것과 같은 로거(obs.NewLogger)를 라우터에 넣고, 나간 줄을 모아서 본다.

const (
	observedTraceID     = "4bf92f3577b34da6a3ce929d0e0e4736"
	observedTraceparent = "00-" + observedTraceID + "-00f067aa0ba902b7-01"
	// 오류의 글에 든, 응답과 로그에 실리면 안 되는 값
	secretInError = "postgres://billing:super-secret@db.internal:5432/trpg"
)

var (
	observedUUID    = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	observedTraceRE = regexp.MustCompile(`^[0-9a-f]{32}$`)
	timestampRE     = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`)
)

// panickingWallet 은 잔액을 물으면 패닉을 내는 가짜 지갑이다.
type panickingWallet struct{ fakeWallet }

func (*panickingWallet) Balance(context.Context, uuid.UUID) (wallet.Balance, error) {
	panic("connect failed: " + secretInError)
}

// observed 는 로그를 모으는 라우터다.
type observed struct {
	router http.Handler
	out    *bytes.Buffer
}

// observe 는 서버와 같은 로거를 꽂은 라우터를 만든다. reader 가 nil 이면 멀쩡한 가짜 지갑이다.
func observe(t *testing.T, reader httpapi.WalletReader) observed {
	t.Helper()
	if reader == nil {
		reader = &fakeWallet{}
	}
	var out bytes.Buffer
	info := obs.ServiceInfo{Service: obs.ServiceName, Environment: "test", Version: "test-version"}
	router := httpapi.NewRouter(httpapi.Dependencies{
		DB:       &fakeDB{},
		Verifier: &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}},
		Wallet:   reader,
		Logger:   obs.NewLogger(&out, info, slog.LevelDebug),
	})
	return observed{router: router, out: &out}
}

// send 는 요청을 보내고 응답을 돌려준다. headers 는 이름과 값을 번갈아 적는다.
func (o observed) send(method string, path string, headers ...string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, nil)
	for i := 0; i+1 < len(headers); i += 2 {
		request.Header.Add(headers[i], headers[i+1])
	}
	response := httptest.NewRecorder()
	o.router.ServeHTTP(response, request)
	return response
}

// lines 는 나간 줄들을 다시 읽는다. 줄마다 JSON 하나여야 한다.
func (o observed) lines(t *testing.T) []map[string]any {
	t.Helper()
	var parsed []map[string]any
	for _, line := range strings.Split(strings.TrimRight(o.out.String(), "\n"), "\n") {
		if line == "" {
			continue
		}
		var entry map[string]any
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			t.Fatalf("JSON 이 아닌 줄이 나갔다: %q", line)
		}
		parsed = append(parsed, entry)
	}
	return parsed
}

// finished 는 요청이 끝났다는 줄이다. 하나여야 한다.
func (o observed) finished(t *testing.T) map[string]any {
	t.Helper()
	var found []map[string]any
	for _, entry := range o.lines(t) {
		if _, ok := entry["status_code"]; ok {
			found = append(found, entry)
		}
	}
	if len(found) != 1 {
		t.Fatalf("요청이 끝난 줄이 %d개다. 하나여야 한다: %s", len(found), o.out.String())
	}
	return found[0]
}

// errorLines 는 error 수준이면서 error_code 가 있는 줄들이다.
func (o observed) errorLines(t *testing.T) []map[string]any {
	t.Helper()
	var found []map[string]any
	for _, entry := range o.lines(t) {
		if _, ok := entry["error_code"]; ok {
			found = append(found, entry)
		}
	}
	return found
}

func requestIDOf(response *httptest.ResponseRecorder) string {
	return response.Header().Get(obs.RequestIDHeader)
}

func TestARequestWithoutAnIDGetsANewOne(t *testing.T) {
	server := observe(t, nil)

	first := server.send(http.MethodGet, "/health")
	second := server.send(http.MethodGet, "/health")

	if !observedUUID.MatchString(requestIDOf(first)) {
		t.Errorf("응답의 식별자가 UUID 가 아니다: %q", requestIDOf(first))
	}
	if requestIDOf(first) == requestIDOf(second) {
		t.Error("두 요청의 식별자가 같다")
	}
}

func TestAWellFormedRequestIDIsKept(t *testing.T) {
	server := observe(t, nil)

	response := server.send(http.MethodGet, "/health", obs.RequestIDHeader, "client-chosen-id-0001")

	if requestIDOf(response) != "client-chosen-id-0001" {
		t.Errorf("응답의 식별자 = %q", requestIDOf(response))
	}
	if got := server.finished(t)["request_id"]; got != "client-chosen-id-0001" {
		t.Errorf("로그의 식별자 = %v", got)
	}
}

func TestAMalformedRequestIDIsReplaced(t *testing.T) {
	values := map[string]string{
		"짧다":      "short",
		"길다":      strings.Repeat("a", 65),
		"아주 길다":   strings.Repeat("a", 3000),
		"공백":      "has space in it",
		"줄바꿈":     "request-12345\r\n{\"level\":\"error\",\"message\":\"forged-line\"}",
		"제어 문자":   "request-\x00\x1b[31m-12345",
		"JSON":    `{"level":"forged-line"}`,
		"쌍반점":     "forged-line;12345",
		"영문이 아니다": "식별자-forged-line-12345",
	}
	for name, value := range values {
		t.Run(name, func(t *testing.T) {
			server := observe(t, nil)

			response := server.send(http.MethodGet, "/health", obs.RequestIDHeader, value)

			if !observedUUID.MatchString(requestIDOf(response)) {
				t.Errorf("응답의 식별자가 새것이 아니다: %q", requestIDOf(response))
			}
			// 받은 값은 로그에 남지 않는다. 가짜 줄도 끼어들지 않는다
			if strings.Contains(server.out.String(), "forged-line") || len(server.lines(t)) != 1 {
				t.Errorf("받은 값이 로그에 남았다: %s", server.out.String())
			}
			if server.finished(t)["request_id"] != requestIDOf(response) {
				t.Error("로그의 식별자가 응답의 식별자와 다르다")
			}
		})
	}
}

func TestARepeatedRequestIDHeaderIsReplaced(t *testing.T) {
	server := observe(t, nil)

	response := server.send(http.MethodGet, "/health",
		obs.RequestIDHeader, "client-chosen-id-0001", obs.RequestIDHeader, "client-chosen-id-0002")

	// 어느 것을 믿을지 정할 수 없다
	if !observedUUID.MatchString(requestIDOf(response)) {
		t.Errorf("응답의 식별자 = %q", requestIDOf(response))
	}
}

func TestTheCallersTraceIsContinued(t *testing.T) {
	server := observe(t, nil)

	server.send(http.MethodGet, "/health", obs.TraceparentHeader, observedTraceparent)
	if got := server.finished(t)["trace_id"]; got != observedTraceID {
		t.Errorf("trace_id = %v, 기대 = %s", got, observedTraceID)
	}
}

func TestAMalformedTraceparentStartsANewTrace(t *testing.T) {
	server := observe(t, nil)

	server.send(http.MethodGet, "/health", obs.TraceparentHeader, "00-"+strings.ToUpper(observedTraceID)+"-00f067aa0ba902b7-01")

	got, _ := server.finished(t)["trace_id"].(string)
	if !observedTraceRE.MatchString(got) || strings.EqualFold(got, observedTraceID) {
		t.Errorf("trace_id = %q", got)
	}
}

func TestEveryResponseCarriesTheRequestID(t *testing.T) {
	server := observe(t, nil)

	unauthorized := server.send(http.MethodGet, meURL)
	missing := server.send(http.MethodGet, "/no/such/address")

	if unauthorized.Code != http.StatusUnauthorized || !observedUUID.MatchString(requestIDOf(unauthorized)) {
		t.Errorf("401 응답: 상태 코드 = %d, 식별자 = %q", unauthorized.Code, requestIDOf(unauthorized))
	}
	if missing.Code != http.StatusNotFound || !observedUUID.MatchString(requestIDOf(missing)) {
		t.Errorf("404 응답: 상태 코드 = %d, 식별자 = %q", missing.Code, requestIDOf(missing))
	}
}

func TestTheFinishedLineHasTheCommonFields(t *testing.T) {
	server := observe(t, nil)

	response := server.send(http.MethodGet, "/health")

	line := server.finished(t)
	for name, want := range map[string]any{
		"level": "info", "service": "billing-server", "environment": "test", "version": "test-version",
		"operation": "http.request", "method": "GET", "route": "/health",
		"status_code": float64(200), "result": "success", "request_id": requestIDOf(response),
	} {
		if line[name] != want {
			t.Errorf("%s = %v, 기대 = %v", name, line[name], want)
		}
	}
	if stamp, _ := line["timestamp"].(string); !timestampRE.MatchString(stamp) {
		t.Errorf("timestamp = %q", stamp)
	}
	if trace, _ := line["trace_id"].(string); !observedTraceRE.MatchString(trace) {
		t.Errorf("trace_id = %q", trace)
	}
	// 걸린 시간은 천분의 1초 단위의 정수다
	if elapsed, ok := line["duration_ms"].(float64); !ok || elapsed < 0 || elapsed != float64(int64(elapsed)) {
		t.Errorf("duration_ms = %v", line["duration_ms"])
	}
}

func TestTheRouteIsTheTemplateNotTheAddress(t *testing.T) {
	server := observe(t, nil)
	orderID := "0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b"

	server.send(http.MethodGet, httpapi.APIPrefix+"/orders/"+orderID+"?secret=query-value")

	line := server.finished(t)
	if line["route"] != httpapi.APIPrefix+"/orders/:id" {
		t.Errorf("route = %v", line["route"])
	}
	// 주소에 든 주문 번호와 주소 뒤에 붙인 값은 남지 않는다
	if strings.Contains(server.out.String(), orderID) || strings.Contains(server.out.String(), "query-value") {
		t.Errorf("실제 주소가 로그에 남았다: %s", server.out.String())
	}
}

func TestAnUnmatchedAddressIsMarkedAndItsPathKeptApart(t *testing.T) {
	server := observe(t, nil)

	server.send(http.MethodGet, "/no/such/address?x=query-value")

	line := server.finished(t)
	if line["route"] != "(unmatched)" || line["path"] != "/no/such/address" {
		t.Errorf("route = %v, path = %v", line["route"], line["path"])
	}
	if line["status_code"] != float64(404) || line["result"] != "client_error" || line["level"] != "info" {
		t.Errorf("404 의 줄 = %v", line)
	}
	if strings.Contains(server.out.String(), "query-value") {
		t.Errorf("주소 뒤에 붙인 값이 로그에 남았다: %s", server.out.String())
	}
}

func TestClientErrorsAreInfo(t *testing.T) {
	server := observe(t, nil)

	server.send(http.MethodGet, meURL)

	// 요청이 틀린 것이다. 서버는 제 일을 했다. 경고로 올리지 않는다
	line := server.finished(t)
	if line["status_code"] != float64(401) || line["result"] != "client_error" || line["level"] != "info" {
		t.Errorf("401 의 줄 = %v", line)
	}
	if len(server.errorLines(t)) != 0 {
		t.Errorf("요청의 잘못에 오류 줄을 남겼다: %s", server.out.String())
	}
}

func TestHeadersAndTokensAreNeverLogged(t *testing.T) {
	server := observe(t, nil)

	server.send(http.MethodGet, walletURL+"?token=query-secret-value",
		"Authorization", "Bearer header-secret-token-value",
		"Cookie", "refresh_token=cookie-secret-value",
		"X-PG-Signature", "signature-secret-value",
	)

	for _, secret := range []string{"header-secret-token-value", "cookie-secret-value", "signature-secret-value", "query-secret-value"} {
		if strings.Contains(server.out.String(), secret) {
			t.Errorf("로그에 %q 가 남았다: %s", secret, server.out.String())
		}
	}
}

func TestAHandledFailureIsLoggedWithTheRequestID(t *testing.T) {
	server := observe(t, &fakeWallet{err: errors.New("connect failed: " + secretInError)})

	response := server.send(http.MethodGet, walletURL,
		"Authorization", "Bearer the-token", obs.TraceparentHeader, observedTraceparent)

	failures := server.errorLines(t)
	if response.Code != http.StatusInternalServerError || len(failures) != 1 {
		t.Fatalf("상태 코드 = %d, 오류 줄 = %d개: %s", response.Code, len(failures), server.out.String())
	}
	for name, want := range map[string]any{
		"level": "error", "operation": "http.request", "error_code": "internal.error",
		"request_id": requestIDOf(response), "trace_id": observedTraceID,
	} {
		if failures[0][name] != want {
			t.Errorf("%s = %v, 기대 = %v", name, failures[0][name], want)
		}
	}
	// 원인은 로그에 남되, 그 안의 비밀번호는 가려진다
	if cause, _ := failures[0]["error_message"].(string); !strings.Contains(cause, "connect failed") {
		t.Errorf("error_message = %q", cause)
	}
	if strings.Contains(server.out.String(), "super-secret") {
		t.Errorf("로그에 비밀번호가 남았다: %s", server.out.String())
	}
	line := server.finished(t)
	if line["status_code"] != float64(500) || line["result"] != "server_error" || line["level"] != "error" {
		t.Errorf("500 의 줄 = %v", line)
	}
}

func TestAPanicIsLoggedWithTheRequestIDAndAStack(t *testing.T) {
	server := observe(t, &panickingWallet{})

	response := server.send(http.MethodGet, walletURL,
		"Authorization", "Bearer the-token", obs.TraceparentHeader, observedTraceparent)

	failures := server.errorLines(t)
	if len(failures) != 1 {
		t.Fatalf("오류 줄이 %d개다: %s", len(failures), server.out.String())
	}
	for name, want := range map[string]any{
		"level": "error", "operation": "http.request", "error_code": "http.unhandled_exception",
		"error_type": "string", "request_id": requestIDOf(response), "trace_id": observedTraceID,
	} {
		if failures[0][name] != want {
			t.Errorf("%s = %v, 기대 = %v", name, failures[0][name], want)
		}
	}
	if stack, _ := failures[0]["stack_trace"].(string); !strings.Contains(stack, "observability_test.go") {
		t.Errorf("stack_trace 에 패닉이 난 곳이 없다: %q", stack)
	}
	if strings.Contains(server.out.String(), "super-secret") {
		t.Errorf("로그에 비밀번호가 남았다: %s", server.out.String())
	}
	line := server.finished(t)
	if line["status_code"] != float64(500) || line["result"] != "server_error" || line["level"] != "error" {
		t.Errorf("500 의 줄 = %v", line)
	}
	if line["route"] != walletURL {
		t.Errorf("route = %v", line["route"])
	}
}

func TestAPanicAnswersWithoutItsContents(t *testing.T) {
	server := observe(t, &panickingWallet{})

	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	if response.Code != http.StatusInternalServerError {
		t.Fatalf("상태 코드 = %d", response.Code)
	}
	var answer map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &answer); err != nil || len(answer) != 1 || answer["detail"] == nil {
		t.Errorf("본문 = %s", response.Body.String())
	}
	for _, leaked := range []string{"super-secret", "connect failed", "goroutine", ".go:"} {
		if strings.Contains(response.Body.String(), leaked) {
			t.Errorf("응답에 %q 가 실렸다: %s", leaked, response.Body.String())
		}
	}
	if !observedUUID.MatchString(requestIDOf(response)) {
		t.Errorf("응답의 식별자 = %q", requestIDOf(response))
	}
}

func TestTheServerKeepsAnsweringAfterAPanic(t *testing.T) {
	server := observe(t, &panickingWallet{})

	server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")
	response := server.send(http.MethodGet, "/health")

	if response.Code != http.StatusOK {
		t.Errorf("패닉 뒤의 요청: 상태 코드 = %d", response.Code)
	}
}

func TestHealthBodiesAreUnchanged(t *testing.T) {
	server := observe(t, nil)

	health := server.send(http.MethodGet, "/health")
	ready := server.send(http.MethodGet, "/health/ready")

	// 본문의 모양은 그대로다. 식별자는 머리말로만 돌려준다
	if body(health) != `{"status":"ok"}` || body(ready) != `{"status":"ok"}` {
		t.Errorf("본문 = %s, %s", body(health), body(ready))
	}
}
