// billing-server/internal/stepup/stepup_test.go

package stepup_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/stepup"
)

const (
	authSecret = "auth-server-test-secret-of-32-chars"
	checkPath  = "/api/v1/auth/service/step-up/check"
	sessionID  = "0123456789abcdef0123456789abcdef"
)

var (
	sentAt = time.Date(2026, 11, 16, 9, 0, 0, 0, time.UTC)
	userID = uuid.MustParse("99999999-8888-4777-8666-555555555555")
)

// fakeAuth 는 인증 서버가 되어 받은 요청을 적고 정해 둔 대로 답한다.
type fakeAuth struct {
	status int
	answer string

	calls     int
	path      string
	signature string
	body      []byte
}

func (f *fakeAuth) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 다른 주소로 가라는 답을 따라오면 열렸다고 답한다. 따라가지 않아야 오류다
	if r.URL.Path == "/elsewhere" {
		_, _ = w.Write([]byte(`{"state":"open"}`))
		return
	}
	if f.status == http.StatusFound {
		w.Header().Set("Location", "/elsewhere")
	}
	f.calls++
	f.path = r.URL.RequestURI()
	f.signature = r.Header.Get(serviceauth.SignatureHeader)
	f.body, _ = io.ReadAll(r.Body)
	w.WriteHeader(f.status)
	_, _ = w.Write([]byte(f.answer))
}

func checkWith(t *testing.T, auth *fakeAuth, session string) (stepup.State, error) {
	t.Helper()
	server := httptest.NewServer(auth)
	t.Cleanup(server.Close)
	checker := stepup.NewHTTPChecker(server.URL+checkPath, authSecret, func() time.Time { return sentAt })
	return checker.Check(context.Background(), userID, session)
}

func TestCheckSendsASignedQuestionAndReadsTheState(t *testing.T) {
	for _, want := range []stepup.State{stepup.Open, stepup.Required, stepup.Disabled} {
		auth := &fakeAuth{status: http.StatusOK, answer: `{"state":"` + string(want) + `","expires_at":null}`}

		got, err := checkWith(t, auth, sessionID)

		if err != nil || got != want {
			t.Fatalf("%s: 받은 것 = %q, %v", want, got, err)
		}
		if auth.path != checkPath {
			t.Errorf("주소 = %s", auth.path)
		}
		// 인증 서버가 하듯 받은 바이트로 서명을 다시 확인한다
		if err := serviceauth.Verify(authSecret, auth.signature, http.MethodPost, checkPath, auth.body, sentAt); err != nil {
			t.Errorf("서명이 맞지 않다: %v", err)
		}
		var body map[string]string
		if err := json.Unmarshal(auth.body, &body); err != nil || body["user_id"] != userID.String() || body["session_id"] != sessionID {
			t.Errorf("본문 = %s", auth.body)
		}
	}
}

func TestAnOldTokenWithoutASessionNeedsTheCheckWithoutAsking(t *testing.T) {
	auth := &fakeAuth{status: http.StatusOK, answer: `{"state":"open"}`}

	got, err := checkWith(t, auth, "")

	if err != nil || got != stepup.Required || auth.calls != 0 {
		t.Errorf("받은 것 = %q, %v, 물은 수 = %d", got, err, auth.calls)
	}
}

func TestAnUnknownUserNeedsTheCheck(t *testing.T) {
	got, err := checkWith(t, &fakeAuth{status: http.StatusNotFound, answer: `{"code":"service_user_unknown"}`}, sessionID)

	if err != nil || got != stepup.Required {
		t.Errorf("받은 것 = %q, %v", got, err)
	}
}

func TestOtherAnswersAreUnavailable(t *testing.T) {
	cases := map[string]*fakeAuth{
		"서명이 틀렸다":      {status: http.StatusUnauthorized, answer: `{"code":"service_bad_signature"}`},
		"서버 오류":        {status: http.StatusInternalServerError, answer: `{}`},
		"읽을 수 없는 답":    {status: http.StatusOK, answer: `not json`},
		"모르는 상태":       {status: http.StatusOK, answer: `{"state":"maybe"}`},
		"다른 곳으로 가라는 답": {status: http.StatusFound},
	}
	for name, auth := range cases {
		t.Run(name, func(t *testing.T) {
			got, err := checkWith(t, auth, sessionID)

			if !errors.Is(err, stepup.ErrUnavailable) || got != "" {
				t.Errorf("받은 것 = %q, %v", got, err)
			}
		})
	}
}

func TestAnUnreachableAuthServerIsUnavailable(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	server.Close()
	checker := stepup.NewHTTPChecker(server.URL+checkPath, authSecret, time.Now)

	_, err := checker.Check(context.Background(), userID, sessionID)

	if !errors.Is(err, stepup.ErrUnavailable) {
		t.Errorf("오류 = %v", err)
	}
}
