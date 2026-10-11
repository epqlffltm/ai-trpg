// billing-server/internal/obs/handler_test.go

package obs_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log"
	"log/slog"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// 서명까지 갖춘 토큰의 모양. 실제 키로 만든 것이 아니다.
const fakeJWT = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU"

var testInfo = obs.ServiceInfo{Service: "billing-server", Environment: "test", Version: "test-version"}

// capture 는 로거와, 그 로거가 내보낸 줄들을 읽는 함수를 돌려준다.
func capture(t *testing.T, threshold slog.Level) (*slog.Logger, *bytes.Buffer) {
	t.Helper()
	var out bytes.Buffer
	return obs.NewLogger(&out, testInfo, threshold), &out
}

// entries 는 나간 줄들을 다시 읽는다. 줄마다 JSON 하나여야 한다.
func entries(t *testing.T, out *bytes.Buffer) []map[string]any {
	t.Helper()
	var parsed []map[string]any
	for _, line := range strings.Split(strings.TrimRight(out.String(), "\n"), "\n") {
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

// logged 는 줄 하나를 남기고 나간 것을 돌려준다.
func logged(t *testing.T, message string, args ...any) map[string]any {
	t.Helper()
	logger, out := capture(t, slog.LevelDebug)
	logger.Info(message, args...)
	return entries(t, out)[0]
}

func TestEveryLineHasTheCommonFields(t *testing.T) {
	entry := logged(t, "서버가 떴다")

	for name, want := range map[string]any{
		"level": "info", "service": "billing-server", "environment": "test",
		"version": "test-version", "message": "서버가 떴다",
	} {
		if entry[name] != want {
			t.Errorf("%s = %v, 기대 = %v", name, entry[name], want)
		}
	}
	stamp, _ := entry["timestamp"].(string)
	if _, err := time.Parse("2006-01-02T15:04:05.000Z", stamp); err != nil {
		t.Errorf("timestamp 가 규격의 모양이 아니다: %q", stamp)
	}
}

func TestALineIsOneJSONObject(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)

	logger.Info("첫 줄\n{\"level\":\"error\",\"message\":\"가짜 줄\"}", "reason", "둘째\r\n줄")

	// 메시지와 값에 줄바꿈을 넣어도 로그는 한 줄이다. 가짜 로그 줄을 끼워 넣을 수 없다
	if strings.Count(out.String(), "\n") != 1 || len(entries(t, out)) != 1 {
		t.Errorf("한 줄이 아니다: %q", out.String())
	}
}

func TestLevelsUseTheCommonNames(t *testing.T) {
	cases := map[slog.Level]string{
		slog.LevelDebug: "debug", slog.LevelInfo: "info", slog.LevelWarn: "warning",
		slog.LevelError: "error", slog.LevelError + 4: "critical",
	}
	for level, want := range cases {
		logger, out := capture(t, slog.LevelDebug)
		logger.Log(context.Background(), level, "글")
		if got := entries(t, out)[0]["level"]; got != want {
			t.Errorf("수준 %v = %v, 기대 = %v", level, got, want)
		}
	}
}

func TestLinesBelowTheThresholdAreDropped(t *testing.T) {
	logger, out := capture(t, slog.LevelWarn)

	logger.Debug("디버그")
	logger.Info("정보")
	logger.Warn("경고")
	logger.Error("오류")

	got := entries(t, out)
	if len(got) != 2 || got[0]["message"] != "경고" || got[1]["message"] != "오류" {
		t.Errorf("나간 줄 = %v", got)
	}
}

func TestParseLevelReadsTheSetting(t *testing.T) {
	for name, want := range map[string]slog.Level{
		"debug": slog.LevelDebug, "info": slog.LevelInfo, "warning": slog.LevelWarn, "error": slog.LevelError,
	} {
		if got, ok := obs.ParseLevel(name); !ok || got != want {
			t.Errorf("ParseLevel(%q) = %v, %v", name, got, ok)
		}
	}
	if _, ok := obs.ParseLevel("verbose"); ok {
		t.Error("모르는 수준을 받았다")
	}
}

func TestScalarFieldsAreWritten(t *testing.T) {
	entry := logged(t, "요청을 처리했다",
		"operation", "http.request", "duration_ms", 12, "result", "success", "retried", false, "ratio", 0.5)

	if entry["operation"] != "http.request" || entry["duration_ms"] != float64(12) {
		t.Errorf("칸이 다르다: %v", entry)
	}
	if entry["result"] != "success" || entry["retried"] != false || entry["ratio"] != 0.5 {
		t.Errorf("칸이 다르다: %v", entry)
	}
}

func TestContextIDsAreAttached(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)
	trace := obs.NewTrace()
	ctx := obs.WithRequest(context.Background(), "request-12345", trace)

	logger.InfoContext(ctx, "요청 안")
	logger.Info("요청 밖")

	got := entries(t, out)
	if got[0]["request_id"] != "request-12345" || got[0]["trace_id"] != trace.ID {
		t.Errorf("식별자가 붙지 않았다: %v", got[0])
	}
	// 걸려 있지 않은 식별자는 빈 글자로 채우지 않고 싣지 않는다
	for _, name := range []string{"request_id", "trace_id", "job_id"} {
		if _, present := got[1][name]; present {
			t.Errorf("걸지 않은 %s 가 실렸다: %v", name, got[1])
		}
	}
}

func TestJobIDIsAttached(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)

	logger.InfoContext(obs.WithJob(context.Background(), "job-12345"), "작업 안")

	entry := entries(t, out)[0]
	if entry["job_id"] != "job-12345" || entry["trace_id"] == nil {
		t.Errorf("작업의 식별자가 붙지 않았다: %v", entry)
	}
	if _, present := entry["request_id"]; present {
		t.Errorf("작업의 줄에 요청 식별자가 실렸다: %v", entry)
	}
}

func TestFixedFieldsCannotBeOverridden(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)
	ctx := obs.WithRequest(context.Background(), "request-12345", obs.NewTrace())

	logger.With("service", "other-server").InfoContext(ctx, "글",
		"environment", "production", "version", "9.9.9", "level", "debug",
		"timestamp", "1999-01-01T00:00:00.000Z", "message", "다른 글", "request_id", "forged-request-id")

	entry := entries(t, out)[0]
	for name, want := range map[string]any{
		"service": "billing-server", "environment": "test", "version": "test-version",
		"level": "info", "message": "글", "request_id": "request-12345",
	} {
		if entry[name] != want {
			t.Errorf("%s = %v, 기대 = %v", name, entry[name], want)
		}
	}
	// 같은 이름이 두 번 나가지도 않는다
	if strings.Count(out.String(), `"service"`) != 1 || strings.Count(out.String(), `"request_id"`) != 1 {
		t.Errorf("같은 칸이 두 번 나갔다: %s", out.String())
	}
}

func TestRepeatedFieldNamesAreWrittenOnce(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)

	logger.With("operation", "first").Info("글", "operation", "second")

	if strings.Count(out.String(), `"operation"`) != 1 || entries(t, out)[0]["operation"] != "first" {
		t.Errorf("같은 칸이 두 번 나갔다: %s", out.String())
	}
}

func TestEnvironmentAndVersionAreOmittedUntilKnown(t *testing.T) {
	var out bytes.Buffer
	logger := obs.NewLogger(&out, obs.ServiceInfo{Service: "billing-server"}, slog.LevelInfo)

	logger.Info("설정을 읽기 전")

	entry := entries(t, &out)[0]
	if _, present := entry["environment"]; present {
		t.Errorf("모르는 환경을 실었다: %v", entry)
	}
	if _, present := entry["version"]; present {
		t.Errorf("모르는 버전을 실었다: %v", entry)
	}
}

func TestSensitiveNamesAreRedacted(t *testing.T) {
	names := []string{
		"password", "new_password", "token", "access_token", "refreshToken", "jwt",
		"authorization", "Authorization", "cookie", "Set-Cookie", "secret", "webhook_secret",
		"api_key", "apiKey", "private_key", "database_url", "DATABASE_URL", "dsn",
		"email", "user_email", "code", "invite_code", "otp", "prompt",
		"card_number", "payment_key", "paymentKey", "signature", "X-PG-Signature",
		"body", "content", "title", "text", "headers",
	}
	for _, name := range names {
		if !obs.IsSensitiveName(name) {
			t.Errorf("IsSensitiveName(%q) = false", name)
		}
		if got := logged(t, "글", name, "드러나면 안 되는 값")[name]; got != obs.Redacted {
			t.Errorf("%s 칸의 값이 가려지지 않았다: %v", name, got)
		}
	}
}

func TestOrdinaryNamesAreKept(t *testing.T) {
	names := []string{
		"operation", "status_code", "error_code", "duration_ms", "result", "route", "method",
		"email_hash", "order_id", "token_type", "error_type", "key_count", "reason",
	}
	for _, name := range names {
		if obs.IsSensitiveName(name) {
			t.Errorf("IsSensitiveName(%q) = true", name)
		}
	}
}

func TestSecretsInsideTextAreScrubbed(t *testing.T) {
	entry := logged(t,
		"토큰을 검증하지 못했다: "+fakeJWT,
		"detail", "Authorization: Bearer "+fakeJWT,
		"hint", "Basic dXNlcjpwYXNzd29yZA==",
		"cause", "DB 에 닿지 않는다: postgres://billing:super-secret@db.internal:5432/trpg",
		"who", "someone.private@example.com 에게 보내지 못했다",
	)

	line := mustJSON(t, entry)
	for _, secret := range []string{fakeJWT, "dXNlcjpwYXNzd29yZA==", "super-secret", "billing:", "someone.private"} {
		if strings.Contains(line, secret) {
			t.Errorf("로그에 %q 가 남았다: %s", secret, line)
		}
	}
	// 어디에 닿지 못했는지, 어느 도메인인지는 남는다
	if !strings.Contains(line, "db.internal") || !strings.Contains(line, "s***@example.com") {
		t.Errorf("가리지 않아도 되는 것까지 가렸다: %s", line)
	}
}

func TestErrorsAreWrittenAsScrubbedText(t *testing.T) {
	cause := errors.New("connect failed: postgres://billing:super-secret@db.internal/trpg")

	entry := logged(t, "실패했다", "error_message", cause)

	text, _ := entry["error_message"].(string)
	if !strings.Contains(text, "connect failed") || strings.Contains(text, "super-secret") {
		t.Errorf("error_message = %q", text)
	}
}

func TestCompositeValuesAreNotExpanded(t *testing.T) {
	type payload struct{ Password string }
	entry := logged(t, "글",
		"payload", payload{Password: "struct-secret"},
		"items", []string{"slice-secret"},
		"lookup", map[string]string{"k": "map-secret"},
		slog.Group("request", slog.String("inner", "group-secret")),
	)

	line := mustJSON(t, entry)
	for _, secret := range []string{"struct-secret", "slice-secret", "map-secret", "group-secret"} {
		if strings.Contains(line, secret) {
			t.Errorf("묶음을 풀어 적었다(%s): %s", secret, line)
		}
	}
	// 종류의 이름만 남는다
	if entry["items"] != "[[]string]" {
		t.Errorf("items = %v", entry["items"])
	}
}

func TestLongValuesAreTruncated(t *testing.T) {
	entry := logged(t, strings.Repeat("가", obs.MaxMessageLength+100),
		"reason", strings.Repeat("나", obs.MaxValueLength+100),
		"stack_trace", strings.Repeat("s", obs.MaxStackLength+100),
	)

	for name, limit := range map[string]int{
		"message": obs.MaxMessageLength, "reason": obs.MaxValueLength, "stack_trace": obs.MaxStackLength,
	} {
		text, _ := entry[name].(string)
		// 자른 글의 끝에 표시(…)가 하나 붙는다
		if utf8.RuneCountInString(text) != limit+1 || !strings.HasSuffix(text, "…") {
			t.Errorf("%s 의 길이 = %d, 기대 = %d", name, utf8.RuneCountInString(text), limit+1)
		}
	}
}

func TestGroupsPrefixFieldNames(t *testing.T) {
	logger, out := capture(t, slog.LevelDebug)

	logger.WithGroup("order").Info("글", "state", "paid", "payment_key", "pay-secret")

	entry := entries(t, out)[0]
	if entry["order.state"] != "paid" {
		t.Errorf("묶음의 이름이 붙지 않았다: %v", entry)
	}
	// 묶음 안의 민감한 이름도 가린다
	if entry["order.payment_key"] != obs.Redacted {
		t.Errorf("묶음 안의 값이 가려지지 않았다: %v", entry)
	}
}

func TestTheStandardLogPackageGoesThroughTheHandler(t *testing.T) {
	previous := slog.Default()
	previousFlags, previousWriter := log.Flags(), log.Writer()
	t.Cleanup(func() {
		slog.SetDefault(previous)
		log.SetFlags(previousFlags)
		log.SetOutput(previousWriter)
	})
	logger, out := capture(t, slog.LevelInfo)
	slog.SetDefault(logger)

	// net/http 서버 같은 표준 라이브러리가 이렇게 남긴다
	log.Printf("표준 log 로 남긴 줄: %s", fakeJWT)

	entry := entries(t, out)[0]
	if entry["service"] != "billing-server" || entry["level"] != "info" {
		t.Errorf("공통 규격으로 나가지 않았다: %v", entry)
	}
	if strings.Contains(out.String(), fakeJWT) {
		t.Errorf("토큰이 가려지지 않았다: %s", out.String())
	}
}

// mustJSON 은 값을 JSON 글로 바꾼다.
func mustJSON(t *testing.T, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("JSON 으로 바꾸지 못했다: %v", err)
	}
	return string(encoded)
}
