// billing-server/internal/guardiannotice/http_test.go

package guardiannotice_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/guardiannotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

const (
	authSecret  = "auth-server-test-secret-of-32-chars"
	noticesPath = "/api/v1/auth/service/guardian-notices"
)

var sentAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

// fakeAuth 는 인증 서버가 되어 받은 요청을 적고 정해 둔 대로 답한다.
type fakeAuth struct {
	status int
	answer string

	path      string
	signature string
	body      []byte
}

func (f *fakeAuth) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 다른 주소로 가라는 답을 따라오면 받았다고 답한다. 따라가지 않아야 오류다
	if r.URL.Path == "/elsewhere" {
		_, _ = w.Write([]byte(`{"status":"queued"}`))
		return
	}
	if f.status == http.StatusFound {
		w.Header().Set("Location", "/elsewhere")
	}
	f.path = r.URL.RequestURI()
	f.signature = r.Header.Get(serviceauth.SignatureHeader)
	f.body, _ = io.ReadAll(r.Body)
	w.WriteHeader(f.status)
	_, _ = w.Write([]byte(f.answer))
}

func sampleNotice() guardiannotice.Notice {
	return guardiannotice.Notice{
		OrderID: uuid.MustParse("11111111-2222-4333-8444-555555555555"), Kind: guardiannotice.KindPaid,
		UserID: uuid.MustParse("99999999-8888-4777-8666-555555555555"), ProductID: "credits-1000",
		Price: 1000, Credits: 1000, OccurredAt: time.Date(2026, 3, 2, 18, 30, 0, 0, time.FixedZone("KST", 9*3600)),
	}
}

func sendTo(t *testing.T, auth *fakeAuth) error {
	t.Helper()
	server := httptest.NewServer(auth)
	t.Cleanup(server.Close)
	sender := guardiannotice.NewHTTPSender(server.URL+noticesPath, authSecret, func() time.Time { return sentAt })
	return sender.Send(context.Background(), sampleNotice())
}

func TestSendPostsASignedNotice(t *testing.T) {
	auth := &fakeAuth{status: http.StatusOK, answer: `{"status":"queued"}`}

	if err := sendTo(t, auth); err != nil {
		t.Fatalf("보내지 못했다: %v", err)
	}
	if auth.path != noticesPath {
		t.Errorf("주소 = %s", auth.path)
	}
	// 인증 서버가 하듯 받은 바이트로 서명을 다시 확인한다
	if err := serviceauth.Verify(authSecret, auth.signature, http.MethodPost, noticesPath, auth.body, sentAt); err != nil {
		t.Errorf("서명이 맞지 않다: %v", err)
	}
	var got map[string]any
	if err := json.Unmarshal(auth.body, &got); err != nil {
		t.Fatalf("본문 = %s", auth.body)
	}
	want := map[string]any{
		"order_id": "11111111-2222-4333-8444-555555555555", "kind": "paid", "user_id": "99999999-8888-4777-8666-555555555555",
		"product_id": "credits-1000", "price": float64(1000), "credits": float64(1000), "occurred_at": "2026-03-02T09:30:00Z",
	}
	for key, value := range want {
		if got[key] != value {
			t.Errorf("%s = %v, 기대 = %v", key, got[key], value)
		}
	}
}

func TestEveryFinishedAnswerIsAccepted(t *testing.T) {
	for _, status := range []string{"queued", "skipped", "duplicate"} {
		if err := sendTo(t, &fakeAuth{status: http.StatusOK, answer: `{"status":"` + status + `"}`}); err != nil {
			t.Errorf("%s: %v", status, err)
		}
	}
}

func TestAnythingElseIsSentAgainLater(t *testing.T) {
	answers := []fakeAuth{
		{status: http.StatusUnauthorized, answer: `{"detail":"x"}`},
		{status: http.StatusNotFound},
		{status: http.StatusServiceUnavailable},
		{status: http.StatusOK, answer: `not json`},
		{status: http.StatusOK, answer: `{"status":"maybe"}`},
		// 다른 주소로 가라는 답은 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다
		{status: http.StatusFound},
	}
	for _, answer := range answers {
		if err := sendTo(t, &answer); err == nil || strings.Contains(err.Error(), authSecret) {
			t.Errorf("%d %s: %v", answer.status, answer.answer, err)
		}
	}
}

func TestAnUnreachableServerIsSentAgainLater(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	address := server.URL
	server.Close()
	sender := guardiannotice.NewHTTPSender(address+noticesPath, authSecret, func() time.Time { return sentAt })

	err := sender.Send(context.Background(), sampleNotice())

	if err == nil || strings.Contains(err.Error(), address) {
		t.Errorf("%v. 오류여야 하고 주소를 싣지 않아야 한다", err)
	}
}
