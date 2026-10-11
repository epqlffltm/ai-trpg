// billing-server/internal/httpapi/auth_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const meURL = httpapi.APIPrefix + "/me"

// fakeVerifier 는 정해 둔 대로 답하는 가짜 검증기다. 받은 토큰을 적어 둔다.
type fakeVerifier struct {
	claims auth.Claims
	err    error
	tokens []string
}

func (f *fakeVerifier) Verify(_ context.Context, token string) (auth.Claims, error) {
	f.tokens = append(f.tokens, token)
	return f.claims, f.err
}

// call 은 Authorization 머리말을 붙여 GET 요청을 보낸다. header 가 비어 있으면 붙이지 않는다.
func call(t *testing.T, verifier httpapi.TokenVerifier, path string, header string) *httptest.ResponseRecorder {
	t.Helper()
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier})
	request := httptest.NewRequest(http.MethodGet, path, nil)
	if header != "" {
		request.Header.Set("Authorization", header)
	}
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}

// mustUUID 는 글자를 UUID 로 읽는다. 못 읽으면 테스트를 실패시킨다.
func mustUUID(t *testing.T, text string) uuid.UUID {
	t.Helper()
	id, err := uuid.Parse(text)
	if err != nil {
		t.Fatalf("UUID 가 아니다: %v", err)
	}
	return id
}

func body(response *httptest.ResponseRecorder) string {
	return strings.TrimSpace(response.Body.String())
}

func TestMeReturnsTheTokenOwner(t *testing.T) {
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}

	response := call(t, verifier, meURL, "Bearer the-token")

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
	if got, want := body(response), `{"user_id":"`+testenv.UserID+`"}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
	// 머리말에서 "Bearer " 를 뗀 것만 검증기에 넘긴다
	if len(verifier.tokens) != 1 || verifier.tokens[0] != "the-token" {
		t.Errorf("검증기가 받은 토큰 = %v", verifier.tokens)
	}
}

func TestBearerSchemeIsCaseInsensitive(t *testing.T) {
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}

	for _, header := range []string{"bearer the-token", "BEARER the-token", "Bearer   the-token  "} {
		if response := call(t, verifier, meURL, header); response.Code != http.StatusOK {
			t.Errorf("%q 의 상태 코드 = %d, 기대 = %d", header, response.Code, http.StatusOK)
		}
	}
	for _, token := range verifier.tokens {
		if token != "the-token" {
			t.Errorf("검증기가 받은 토큰 = %q", token)
		}
	}
}

func TestRequestsWithoutABearerTokenAreUnauthorized(t *testing.T) {
	cases := map[string]string{
		"머리말이 없다":   "",
		"방식이 다르다":   "Basic dXNlcjpwYXNz",
		"토큰이 없다":    "Bearer",
		"토큰이 비었다":   "Bearer    ",
		"방식 없이 토큰만": "the-token",
		"붙여 썼다":     "Bearerthe-token",
	}
	for name, header := range cases {
		t.Run(name, func(t *testing.T) {
			verifier := &fakeVerifier{}

			response := call(t, verifier, meURL, header)

			assertUnauthorized(t, response)
			// 토큰이 없으면 검증기를 부르지도 않는다
			if len(verifier.tokens) != 0 {
				t.Errorf("검증기를 불렀다: %v", verifier.tokens)
			}
		})
	}
}

func TestInvalidTokensAreUnauthorizedWithoutAReason(t *testing.T) {
	// 검증기가 이유를 붙여 와도 응답에는 싣지 않는다
	verifier := &fakeVerifier{err: errors.Join(auth.ErrInvalidToken, errors.New("signature is invalid for key-1"))}

	response := call(t, verifier, meURL, "Bearer forged")

	assertUnauthorized(t, response)
	if strings.Contains(response.Body.String(), "signature") || strings.Contains(response.Body.String(), "key-1") {
		t.Errorf("응답에 거부한 이유가 실렸다: %s", body(response))
	}
}

func TestUnavailableKeysAreServiceUnavailable(t *testing.T) {
	verifier := &fakeVerifier{err: jwks.ErrUnavailable}

	response := call(t, verifier, meURL, "Bearer maybe-fine")

	// 401 이 아니다. 401 이면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusServiceUnavailable)
	}
	if got := response.Header().Get("Retry-After"); got != "60" {
		t.Errorf("Retry-After = %q, 기대 = %q", got, "60")
	}
	if response.Header().Get("WWW-Authenticate") != "" {
		t.Error("503 에 WWW-Authenticate 를 붙였다")
	}
	if got, want := body(response), `{"detail":"지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
}

func TestHealthDoesNotNeedAToken(t *testing.T) {
	verifier := &fakeVerifier{err: auth.ErrInvalidToken}

	for _, path := range []string{"/health", "/health/ready"} {
		if response := call(t, verifier, path, ""); response.Code != http.StatusOK {
			t.Errorf("%s 의 상태 코드 = %d, 기대 = %d", path, response.Code, http.StatusOK)
		}
	}
	if len(verifier.tokens) != 0 {
		t.Errorf("상태 확인에서 검증기를 불렀다: %v", verifier.tokens)
	}
}

func TestMeWithARealTokenAndKeyServer(t *testing.T) {
	// 가짜 인증 서버(JWKS) → 캐시 → 검증기 → 라우터를 실제 것으로 이어서 본다
	key := testenv.NewSigningKey(t, 0, "key-1")
	var served atomic.Int32
	authServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		served.Add(1)
		_, _ = w.Write(testenv.JWKS(t, key))
	}))
	defer authServer.Close()
	cache := jwks.NewCache(jwks.HTTPFetcher{Client: authServer.Client(), URL: authServer.URL}, time.Now)
	verifier := auth.NewVerifier(cache, testenv.Issuer, testenv.Audience, time.Now)

	access := key.Token(t, testenv.AccessClaims(time.Now()))
	for range 3 {
		response := call(t, verifier, meURL, "Bearer "+access)
		if response.Code != http.StatusOK || body(response) != `{"user_id":"`+testenv.UserID+`"}` {
			t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
		}
	}
	// 요청마다 인증 서버를 부르지 않는다
	if served.Load() != 1 {
		t.Errorf("인증 서버를 %d번 불렀다. 한 번이어야 한다", served.Load())
	}

	refresh := testenv.AccessClaims(time.Now())
	refresh["token_type"] = "refresh"
	assertUnauthorized(t, call(t, verifier, meURL, "Bearer "+key.Token(t, refresh)))

	// 인증 서버가 죽어도 기억한 키로 계속 검증한다
	authServer.Close()
	if response := call(t, verifier, meURL, "Bearer "+access); response.Code != http.StatusOK {
		t.Errorf("인증 서버가 죽은 뒤의 상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
}

func TestKeyServerDownFromTheStartIsServiceUnavailable(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	authServer := httptest.NewServer(http.NotFoundHandler())
	authServer.Close()
	cache := jwks.NewCache(jwks.HTTPFetcher{Client: &http.Client{}, URL: authServer.URL}, time.Now)
	verifier := auth.NewVerifier(cache, testenv.Issuer, testenv.Audience, time.Now)

	response := call(t, verifier, meURL, "Bearer "+key.Token(t, testenv.AccessClaims(time.Now())))

	if response.Code != http.StatusServiceUnavailable {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusServiceUnavailable)
	}
}

// assertUnauthorized 는 401 응답의 모양을 본다. 이유를 싣지 않고, 인증 방식을 알려 준다.
func assertUnauthorized(t *testing.T, response *httptest.ResponseRecorder) {
	t.Helper()
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusUnauthorized)
	}
	if got := response.Header().Get("WWW-Authenticate"); got != "Bearer" {
		t.Errorf("WWW-Authenticate = %q, 기대 = %q", got, "Bearer")
	}
	if got, want := body(response), `{"detail":"인증이 필요합니다."}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
}

// 컴파일러가 확인한다: 진짜 검증기와 진짜 캐시가 라우터와 검증기가 받는 모양과 맞는다.
var (
	_ httpapi.TokenVerifier = (*auth.Verifier)(nil)
	_ auth.KeySource        = (*jwks.Cache)(nil)
)
