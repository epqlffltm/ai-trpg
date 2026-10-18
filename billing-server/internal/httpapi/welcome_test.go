// billing-server/internal/httpapi/welcome_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	welcomeURL = httpapi.APIPrefix + "/service/grants/welcome"
	// authSecret 은 테스트의 인증 서버와 결제 서버가 함께 아는 비밀이다.
	authSecret  = "auth-server-test-secret-of-32-chars"
	welcomeText = `{"user_id":"` + testenv.UserID + `"}`
)

// fakeGranter 는 정해 둔 대로 답하는 가짜 지급기다. 무엇을 받았는지 적어 둔다.
type fakeGranter struct {
	err error

	calls  int
	user   uuid.UUID
	amount credit.Amount
	key    string
}

func (f *fakeGranter) GrantFreeOnce(_ context.Context, userID uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error) {
	f.calls++
	f.user, f.amount, f.key = userID, amount, key
	if f.err != nil {
		return wallet.Grant{}, f.err
	}
	return wallet.Grant{Amount: amount, ExpiresAt: time.Date(2026, 3, 9, 9, 0, 0, 0, time.UTC)}, nil
}

// welcomeDeps 는 가짜 지급기를 끼운 서버의 부품이다. amount 는 서버의 설정에 적힌 양이다.
func welcomeDeps(granter httpapi.WelcomeGranter, amount credit.Amount) httpapi.Dependencies {
	return httpapi.Dependencies{
		Welcome: granter, WelcomeCredits: amount,
		AuthServerSecret: authSecret, GameServerSecret: gameSecret, WebhookSecret: webhookSecret,
		Now: func() time.Time { return webhookNow },
	}
}

// signedBy 는 그 비밀을 가진 서버가 하듯 POST 에 서명한 머리말을 만든다.
func signedBy(secret string, path string, text string) map[string]string {
	return map[string]string{serviceauth.SignatureHeader: serviceauth.Sign(secret, webhookNow, http.MethodPost, path, []byte(text))}
}

// asAuth 는 인증 서버가 서명해 보낸 것처럼 환영 크레딧을 달라고 요청한다. 사용자의 토큰은 붙이지 않는다.
func asAuth(t *testing.T, deps httpapi.Dependencies, text string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, deps, request{
		method: http.MethodPost, path: welcomeURL, body: text, anonymous: true,
		headers: signedBy(authSecret, welcomeURL, text),
	})
}

func TestWelcomeGivesTheConfiguredCreditsToTheNamedUser(t *testing.T) {
	granter := &fakeGranter{}

	response := asAuth(t, welcomeDeps(granter, 1000), welcomeText)

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if got, want := body(response), `{"status":"granted","granted":"1000","expires_at":"2026-03-09T09:00:00Z"}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
	// 본문의 사용자에게, 설정에 적힌 양을, welcome 이라는 이름으로 준다
	if granter.user.String() != testenv.UserID || granter.amount != 1000 || granter.key != httpapi.WelcomeGrantKey {
		t.Errorf("지급기가 받은 것 = %v, %d, %q", granter.user, granter.amount, granter.key)
	}
}

func TestWelcomeIgnoresAmountsAndKeysFromTheRequest(t *testing.T) {
	// 인증 서버가 양이나 지급의 이름을 실어 보내도 쓰지 않는다. 양은 이 서버의 설정이 정한다
	granter := &fakeGranter{}
	text := `{"user_id":"` + testenv.UserID + `","amount":"999999","granted":"999999","key":"other"}`

	response := asAuth(t, welcomeDeps(granter, 1000), text)

	if response.Code != http.StatusCreated || granter.amount != 1000 || granter.key != httpapi.WelcomeGrantKey {
		t.Errorf("상태 코드 = %d, 지급기가 받은 것 = %d, %q", response.Code, granter.amount, granter.key)
	}
}

func TestWelcomeForAUserWhoAlreadyHasItIsNotAnError(t *testing.T) {
	// 인증 서버가 응답을 못 받아 다시 보낸 요청일 수 있다. 다시 주지 않고, 끝난 일이라고 답한다
	granter := &fakeGranter{err: wallet.ErrAlreadyGranted}

	response := asAuth(t, welcomeDeps(granter, 1000), welcomeText)

	if got, want := body(response), `{"status":"already_granted","granted":"0","expires_at":null}`; response.Code != http.StatusOK || got != want {
		t.Errorf("응답 = %d %s, 기대 = 200 %s", response.Code, got, want)
	}
}

func TestWelcomeTurnedOffGivesNothing(t *testing.T) {
	// 설정의 양이 0 이면 주지 않는다. 지급기를 부르지도 않는다. 부르는 서버에게는 끝난 일이다
	granter := &fakeGranter{}

	response := asAuth(t, welcomeDeps(granter, 0), welcomeText)

	if got, want := body(response), `{"status":"disabled","granted":"0","expires_at":null}`; response.Code != http.StatusOK || got != want {
		t.Errorf("응답 = %d %s, 기대 = 200 %s", response.Code, got, want)
	}
	if granter.calls != 0 {
		t.Errorf("꺼 두었는데 지급기를 %d 번 불렀다", granter.calls)
	}
}

func TestWelcomeFailureIsAnInternalErrorWithoutTheCause(t *testing.T) {
	granter := &fakeGranter{err: errors.New(`relation "free_grants" does not exist`)}

	response := asAuth(t, welcomeDeps(granter, 1000), welcomeText)

	// 2xx 가 아니어야 인증 서버가 나중에 다시 부른다
	if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "free_grants") {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestSignedButUnusableWelcomeRequestsAreBadRequests(t *testing.T) {
	texts := map[string]string{
		"JSON 이 아니다":      "user_id=1",
		"본문이 비었다":         "",
		"사용자가 없다":         `{}`,
		"사용자가 0 인 UUID 다": `{"user_id":"00000000-0000-0000-0000-000000000000"}`,
		"사용자가 UUID 가 아니다": `{"user_id":"42"}`,
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			granter := &fakeGranter{}

			response := asAuth(t, welcomeDeps(granter, 1000), text)

			if response.Code != http.StatusBadRequest || granter.calls != 0 {
				t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
			}
		})
	}
}

func TestWelcomeNeedsTheAuthServersSignature(t *testing.T) {
	cases := map[string]map[string]string{
		"서명이 없다":           {},
		"게임 서버의 비밀로 서명했다":  signedBy(gameSecret, welcomeURL, welcomeText),
		"결제 알림의 비밀로 서명했다":  signedBy(webhookSecret, welcomeURL, welcomeText),
		"다른 사용자의 요청에 서명했다": signedBy(authSecret, welcomeURL, `{"user_id":"99999999-8888-4777-8666-555555555555"}`),
		"다른 주소에 서명했다":      signedBy(authSecret, holdsURL, welcomeText),
		"한 시간 전에 서명했다": {serviceauth.SignatureHeader: serviceauth.Sign(
			authSecret, webhookNow.Add(-time.Hour), http.MethodPost, welcomeURL, []byte(welcomeText))},
	}
	for name, headers := range cases {
		t.Run(name, func(t *testing.T) {
			granter := &fakeGranter{}

			response := send(t, welcomeDeps(granter, 1000), request{
				method: http.MethodPost, path: welcomeURL, body: welcomeText, headers: headers, anonymous: true,
			})

			if response.Code != http.StatusUnauthorized || granter.calls != 0 {
				t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d. 401 이고 부르지 않아야 한다", response.Code, granter.calls)
			}
		})
	}
}

func TestAUserCannotClaimWelcomeCreditsDirectly(t *testing.T) {
	// 로그인한 사용자가 직접 부른다. 새 주소도, 전에 있던 사용자용 주소도 받지 않는다.
	// 사용자가 직접 받을 수 있으면 인증 서버가 "이 사람은 이미 받았다"고 막아도 소용이 없다
	granter := &fakeGranter{}
	deps := welcomeDeps(granter, 1000)

	service := send(t, deps, request{method: http.MethodPost, path: welcomeURL, body: welcomeText})
	old := send(t, deps, request{method: http.MethodPost, path: httpapi.APIPrefix + "/wallet/welcome"})

	if service.Code != http.StatusUnauthorized || old.Code != http.StatusNotFound || granter.calls != 0 {
		t.Errorf("새 주소 = %d, 옛 주소 = %d, 지급기를 부른 횟수 = %d", service.Code, old.Code, granter.calls)
	}
}

func TestTheAuthServersSignatureDoesNotOpenTheHoldRoutes(t *testing.T) {
	// 서버마다 부를 수 있는 주소가 다르다. 인증 서버의 비밀이 새도 남의 크레딧을 빼거나 홀드를 붙잡아 둘 수 없다
	for _, tc := range []struct{ url, text string }{{holdsURL, holdText}, {extendURL, settleText}} {
		holds := &fakeHolds{hold: aHold(t), isNew: true}
		deps := welcomeDeps(&fakeGranter{}, 1000)
		deps.Holds = holds

		response := send(t, deps, request{
			method: http.MethodPost, path: tc.url, body: tc.text, anonymous: true,
			headers: signedBy(authSecret, tc.url, tc.text),
		})

		if response.Code != http.StatusUnauthorized || holds.calls != 0 {
			t.Errorf("%s: 상태 코드 = %d, 홀드 서비스를 부른 횟수 = %d", tc.url, response.Code, holds.calls)
		}
	}
}

func TestAServerWithoutAnAuthSecretGivesNoWelcomeCredits(t *testing.T) {
	// 비밀이 빠진 서버다. 빈 비밀로 만든 서명이 통하면 누구나 크레딧을 만들어 낸다
	granter := &fakeGranter{}
	deps := welcomeDeps(granter, 1000)
	deps.AuthServerSecret = ""

	response := send(t, deps, request{
		method: http.MethodPost, path: welcomeURL, body: welcomeText, anonymous: true,
		headers: signedBy("", welcomeURL, welcomeText),
	})

	if response.Code != http.StatusUnauthorized || granter.calls != 0 {
		t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
	}
}

func TestWelcomeIsNotGivenByGET(t *testing.T) {
	granter := &fakeGranter{}

	response := send(t, welcomeDeps(granter, 1000), request{
		method: http.MethodGet, path: welcomeURL, anonymous: true,
		headers: map[string]string{serviceauth.SignatureHeader: serviceauth.Sign(authSecret, webhookNow, http.MethodGet, welcomeURL, nil)},
	})

	if response.Code != http.StatusNotFound || granter.calls != 0 {
		t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
	}
}

func TestWelcomeWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않고 실제 지갑과 DB 로 끝까지 지난다
	pool := testenv.Pool(t)
	now := func() time.Time { return webhookNow }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: 7 * 24 * time.Hour})
	deps := welcomeDeps(wallets, 1000)
	deps.Wallet = wallets
	user := uuid.NewString()
	text := `{"user_id":"` + user + `"}`

	first := asAuth(t, deps, text)
	if got, want := body(first), `{"status":"granted","granted":"1000","expires_at":"2026-03-09T09:00:00Z"}`; first.Code != http.StatusCreated || got != want {
		t.Fatalf("첫 요청 = %d %s, 기대 = 201 %s", first.Code, got, want)
	}
	second := asAuth(t, deps, text)
	if second.Code != http.StatusOK || !strings.Contains(body(second), `"status":"already_granted"`) {
		t.Errorf("둘째 요청 = %d %s. 200 already_granted 여야 한다", second.Code, body(second))
	}
	// 한 번만 들어갔다. 사용자는 자기 토큰으로 잔액을 보고, 그 크레딧이 언제 사라지는지도 본다
	balance := sendAs(t, deps, user, request{method: http.MethodGet, path: walletURL})
	wantBody := `{"paid":"0","free":"1000","total":"1000","next_expiry":{"amount":"1000","expires_at":"2026-03-09T09:00:00Z"}}`
	if got, want := body(balance), wantBody; got != want {
		t.Errorf("잔액 = %s, 기대 = %s", got, want)
	}
	// 다른 사용자는 따로 받는다
	if other := asAuth(t, deps, `{"user_id":"`+uuid.NewString()+`"}`); other.Code != http.StatusCreated {
		t.Errorf("다른 사용자 = %d %s", other.Code, body(other))
	}
}
