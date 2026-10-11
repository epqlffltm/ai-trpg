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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const welcomeURL = httpapi.APIPrefix + "/wallet/welcome"

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

// claim 은 환영 크레딧을 달라고 요청한다. amount 는 서버의 설정에 적힌 양이다.
func claim(t *testing.T, granter httpapi.WelcomeGranter, amount credit.Amount, r request) *httptest.ResponseRecorder {
	t.Helper()
	r.method, r.path = http.MethodPost, welcomeURL
	return send(t, httpapi.Dependencies{Welcome: granter, WelcomeCredits: amount}, r)
}

func TestWelcomeGivesTheConfiguredCreditsToTheTokenOwner(t *testing.T) {
	granter := &fakeGranter{}

	response := claim(t, granter, 1000, request{})

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if got, want := body(response), `{"granted":"1000","expires_at":"2026-03-09T09:00:00Z"}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
	// 토큰의 주인에게, 설정에 적힌 양을, welcome 이라는 이름으로 준다
	if granter.user.String() != testenv.UserID || granter.amount != 1000 || granter.key != httpapi.WelcomeGrantKey {
		t.Errorf("지급기가 받은 것 = %v, %d, %q", granter.user, granter.amount, granter.key)
	}
}

func TestWelcomeIgnoresAmountsAndOwnersFromTheRequest(t *testing.T) {
	// 본문이나 쿼리에 양이나 다른 사용자를 적어 보내도 쓰지 않는다
	granter := &fakeGranter{}
	const someoneElse = "11111111-2222-4333-8444-555555555555"

	send(t, httpapi.Dependencies{Welcome: granter, WelcomeCredits: 1000}, request{
		method: http.MethodPost, path: welcomeURL + "?amount=999999&user_id=" + someoneElse,
		body: `{"amount":"999999","granted":"999999","user_id":"` + someoneElse + `","key":"other"}`,
	})

	if granter.user.String() != testenv.UserID || granter.amount != 1000 || granter.key != httpapi.WelcomeGrantKey {
		t.Errorf("지급기가 받은 것 = %v, %d, %q", granter.user, granter.amount, granter.key)
	}
}

func TestWelcomeTwiceIsAConflict(t *testing.T) {
	granter := &fakeGranter{err: wallet.ErrAlreadyGranted}

	response := claim(t, granter, 1000, request{})

	if response.Code != http.StatusConflict || !strings.Contains(body(response), `"detail"`) {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestWelcomeTurnedOffIsNotFound(t *testing.T) {
	// 설정의 양이 0 이면 주지 않는다. 지급기를 부르지도 않는다
	granter := &fakeGranter{}

	response := claim(t, granter, 0, request{})

	if response.Code != http.StatusNotFound || granter.calls != 0 {
		t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
	}
}

func TestWelcomeNeedsAToken(t *testing.T) {
	granter := &fakeGranter{}

	response := claim(t, granter, 1000, request{anonymous: true})

	assertUnauthorized(t, response)
	if granter.calls != 0 {
		t.Error("토큰이 없는데 크레딧을 줬다")
	}
}

func TestWelcomeFailureIsAnInternalErrorWithoutTheCause(t *testing.T) {
	granter := &fakeGranter{err: errors.New(`relation "free_grants" does not exist`)}

	response := claim(t, granter, 1000, request{})

	if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "free_grants") {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestWelcomeIsNotGivenByGET(t *testing.T) {
	// 주소를 열어 보는 것(GET)만으로 크레딧이 생기면 안 된다. 링크를 미리 읽는 프로그램도 GET 을 보낸다
	granter := &fakeGranter{}

	response := send(t, httpapi.Dependencies{Welcome: granter, WelcomeCredits: 1000}, request{method: http.MethodGet, path: welcomeURL})

	if response.Code != http.StatusNotFound || granter.calls != 0 {
		t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
	}
}

func TestWelcomeWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않고 실제 지갑과 DB 로 끝까지 지난다
	pool := testenv.Pool(t)
	now := func() time.Time { return webhookNow }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: 7 * 24 * time.Hour})
	deps := httpapi.Dependencies{Wallet: wallets, Welcome: wallets, WelcomeCredits: 1000}
	user := uuid.NewString()

	first := sendAs(t, deps, user, request{method: http.MethodPost, path: welcomeURL})
	if got, want := body(first), `{"granted":"1000","expires_at":"2026-03-09T09:00:00Z"}`; first.Code != http.StatusCreated || got != want {
		t.Fatalf("첫 요청 = %d %s, 기대 = 201 %s", first.Code, got, want)
	}
	second := sendAs(t, deps, user, request{method: http.MethodPost, path: welcomeURL})
	if second.Code != http.StatusConflict {
		t.Errorf("둘째 요청 = %d %s. 409 여야 한다", second.Code, body(second))
	}
	// 한 번만 들어갔다
	balance := sendAs(t, deps, user, request{method: http.MethodGet, path: walletURL})
	if got, want := body(balance), `{"paid":"0","free":"1000","total":"1000"}`; got != want {
		t.Errorf("잔액 = %s, 기대 = %s", got, want)
	}
	// 다른 사용자는 따로 받는다
	if other := sendAs(t, deps, uuid.NewString(), request{method: http.MethodPost, path: welcomeURL}); other.Code != http.StatusCreated {
		t.Errorf("다른 사용자 = %d %s", other.Code, body(other))
	}
}
