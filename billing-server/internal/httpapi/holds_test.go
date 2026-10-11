// billing-server/internal/httpapi/holds_test.go

package httpapi_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	holdsURL   = httpapi.APIPrefix + "/service/holds"
	captureURL = holdsURL + "/capture"
	releaseURL = holdsURL + "/release"
	// gameSecret 은 테스트의 게임 서버와 결제 서버가 함께 아는 비밀이다.
	gameSecret = "game-server-test-secret-of-32-chars"
	holdRef    = "table:7f3c:round:3"
	holdText   = `{"user_id":"` + testenv.UserID + `","reference":"` + holdRef + `","price_code":"narration.standard"}`
	settleText = `{"reference":"` + holdRef + `"}`
)

// fakeHolds 는 정해 둔 대로 답하는 가짜 홀드 서비스다. 무엇으로 불렸는지 적어 둔다.
type fakeHolds struct {
	hold  hold.Hold
	isNew bool
	err   error

	calls     int
	action    string
	source    string
	userID    uuid.UUID
	reference string
	priceCode string
}

func (f *fakeHolds) Place(_ context.Context, source string, userID uuid.UUID, reference string, priceCode string) (hold.Hold, bool, error) {
	f.calls++
	f.action, f.source, f.userID, f.reference, f.priceCode = "place", source, userID, reference, priceCode
	return f.hold, f.isNew, f.err
}

func (f *fakeHolds) Capture(_ context.Context, source string, reference string) (hold.Hold, error) {
	f.calls++
	f.action, f.source, f.reference = "capture", source, reference
	return f.hold, f.err
}

func (f *fakeHolds) Release(_ context.Context, source string, reference string) (hold.Hold, error) {
	f.calls++
	f.action, f.source, f.reference = "release", source, reference
	return f.hold, f.err
}

// aHold 는 응답의 모양을 볼 때 쓰는 홀드다.
func aHold(t *testing.T) hold.Hold {
	t.Helper()
	return hold.Hold{
		ID:        mustUUID(t, "0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b"),
		UserID:    mustUUID(t, testenv.UserID),
		Reference: holdRef,
		PriceCode: "narration.standard",
		Amount:    50,
		Status:    hold.StatusHeld,
		CreatedAt: webhookNow,
	}
}

// holdDeps 는 가짜 홀드 서비스를 끼운 서버의 부품이다.
func holdDeps(holds httpapi.HoldService) httpapi.Dependencies {
	return httpapi.Dependencies{Holds: holds, GameServerSecret: gameSecret, Now: func() time.Time { return webhookNow }}
}

// serviceSigned 는 게임 서버가 하듯 요청에 서명한 머리말을 만든다.
func serviceSigned(method string, path string, text string) map[string]string {
	return map[string]string{serviceauth.SignatureHeader: serviceauth.Sign(gameSecret, webhookNow, method, path, []byte(text))}
}

// asGame 은 게임 서버가 서명해 보낸 것처럼 POST 를 보낸다. 사용자의 토큰은 붙이지 않는다.
func asGame(t *testing.T, deps httpapi.Dependencies, path string, text string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, deps, request{
		method: http.MethodPost, path: path, body: text, anonymous: true,
		headers: serviceSigned(http.MethodPost, path, text),
	})
}

func TestPlacingAHoldAnswersCreated(t *testing.T) {
	holds := &fakeHolds{hold: aHold(t), isNew: true}

	response := asGame(t, holdDeps(holds), holdsURL, holdText)

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	// 크레딧은 글자다. 아직 끝나지 않은 홀드의 settled_at 은 null 이다
	want := `{"id":"0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b","user_id":"` + testenv.UserID + `","reference":"` + holdRef +
		`","price_code":"narration.standard","amount":"50","status":"held","created_at":"2026-03-02T09:00:00Z","settled_at":null}`
	if body(response) != want {
		t.Errorf("본문 = %s\n기대 = %s", body(response), want)
	}
	// 누가 걸었는지는 본문이 아니라 서명에서 온다. 부르는 쪽이 다른 서버의 이름을 댈 수 없다
	if holds.action != "place" || holds.source != httpapi.GameServer || holds.userID != mustUUID(t, testenv.UserID) ||
		holds.reference != holdRef || holds.priceCode != "narration.standard" {
		t.Errorf("서비스에 넘긴 값 = %+v", holds)
	}
}

func TestPlacingTheSameHoldAgainAnswersOk(t *testing.T) {
	holds := &fakeHolds{hold: aHold(t), isNew: false}

	response := asGame(t, holdDeps(holds), holdsURL, holdText)

	// 새로 걸지 않았다는 것을 상태 코드로 알린다. 본문은 같은 홀드다
	if response.Code != http.StatusOK || !strings.Contains(body(response), `"status":"held"`) {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestTheCallerCannotNameThePriceOrTheSource(t *testing.T) {
	// 금액과 부르는 서버의 이름을 본문에 실어 보낸다. 둘 다 읽지 않는다
	holds := &fakeHolds{hold: aHold(t), isNew: true}
	text := `{"user_id":"` + testenv.UserID + `","reference":"` + holdRef + `","price_code":"narration.standard","amount":"1","source":"auth-server"}`

	response := asGame(t, holdDeps(holds), holdsURL, text)

	if response.Code != http.StatusCreated || holds.source != httpapi.GameServer || !strings.Contains(body(response), `"amount":"50"`) {
		t.Errorf("상태 코드 = %d, 부른 서버 = %q, 본문 = %s", response.Code, holds.source, body(response))
	}
}

func TestCapturingAndReleasingAnswerWithTheSettledHold(t *testing.T) {
	settled := webhookNow.Add(40 * time.Second)
	cases := map[string]struct {
		url    string
		status hold.Status
	}{
		"capture": {captureURL, hold.StatusCaptured},
		"release": {releaseURL, hold.StatusReleased},
	}
	for action, tc := range cases {
		t.Run(action, func(t *testing.T) {
			done := aHold(t)
			done.Status, done.SettledAt = tc.status, &settled
			holds := &fakeHolds{hold: done}

			response := asGame(t, holdDeps(holds), tc.url, settleText)

			if response.Code != http.StatusOK || holds.action != action || holds.source != httpapi.GameServer || holds.reference != holdRef {
				t.Fatalf("상태 코드 = %d, 서비스에 넘긴 값 = %+v", response.Code, holds)
			}
			want := `"status":"` + string(tc.status) + `","created_at":"2026-03-02T09:00:00Z","settled_at":"2026-03-02T09:00:40Z"}`
			if !strings.HasSuffix(body(response), want) {
				t.Errorf("본문 = %s", body(response))
			}
		})
	}
}

func TestHoldErrorsBecomeStatusCodes(t *testing.T) {
	cases := map[string]struct {
		url  string
		text string
		err  error
		want int
	}{
		"이름표의 모양이 틀렸다":     {holdsURL, holdText, hold.ErrInvalidReference, http.StatusBadRequest},
		"가격표에 없는 이름이다":     {holdsURL, holdText, hold.ErrUnknownPrice, http.StatusBadRequest},
		"크레딧이 모자란다":        {holdsURL, holdText, wallet.ErrInsufficient, http.StatusPaymentRequired},
		"이름표를 다른 사용자에게 썼다": {holdsURL, holdText, hold.ErrReferenceReused, http.StatusConflict},
		"확정할 홀드가 없다":       {captureURL, settleText, hold.ErrNotFound, http.StatusNotFound},
		"돌려줄 홀드가 없다":       {releaseURL, settleText, hold.ErrNotFound, http.StatusNotFound},
		"돌려준 것을 확정한다":      {captureURL, settleText, hold.ErrAlreadyReleased, http.StatusConflict},
		"확정한 것을 돌려 달라고 한다": {releaseURL, settleText, hold.ErrAlreadyCaptured, http.StatusConflict},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			response := asGame(t, holdDeps(&fakeHolds{err: tc.err}), tc.url, tc.text)

			if response.Code != tc.want || !strings.Contains(body(response), `"detail":"`) {
				t.Errorf("상태 코드 = %d, 본문 = %s. 기대 = %d", response.Code, body(response), tc.want)
			}
		})
	}
}

func TestAnUnexpectedHoldErrorHidesItsCause(t *testing.T) {
	for _, url := range []string{holdsURL, captureURL, releaseURL} {
		holds := &fakeHolds{err: errors.New("pq: connection refused at 10.0.0.7")}
		text := settleText
		if url == holdsURL {
			text = holdText
		}

		response := asGame(t, holdDeps(holds), url, text)

		if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "10.0.0.7") {
			t.Errorf("%s: 상태 코드 = %d, 본문 = %s", url, response.Code, body(response))
		}
	}
}

func TestSignedButUnusableHoldRequestsAreBadRequests(t *testing.T) {
	cases := map[string]struct {
		url  string
		text string
	}{
		"JSON 이 아니다":       {holdsURL, "user_id=1"},
		"본문이 비었다":          {holdsURL, ""},
		"사용자가 없다":          {holdsURL, `{"reference":"` + holdRef + `","price_code":"narration.standard"}`},
		"사용자가 0 인 UUID 다":  {holdsURL, `{"user_id":"00000000-0000-0000-0000-000000000000","reference":"` + holdRef + `","price_code":"narration.standard"}`},
		"사용자가 UUID 가 아니다":  {holdsURL, `{"user_id":"42","reference":"` + holdRef + `","price_code":"narration.standard"}`},
		"확정: JSON 이 아니다":   {captureURL, "reference=1"},
		"반환: 이름표가 글자가 아니다": {releaseURL, `{"reference":3}`},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			holds := &fakeHolds{}

			response := asGame(t, holdDeps(holds), tc.url, tc.text)

			if response.Code != http.StatusBadRequest || holds.calls != 0 {
				t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, holds.calls)
			}
		})
	}
}

func TestRequestsWithoutAValidServiceSignatureAreUnauthorized(t *testing.T) {
	sign := func(secret string, at time.Time, method string, path string, text string) string {
		return serviceauth.Sign(secret, at, method, path, []byte(text))
	}
	other := strings.Replace(holdText, testenv.UserID, "99999999-8888-4777-8666-555555555555", 1)
	cases := map[string]struct {
		path      string
		text      string
		signature string
	}{
		"서명이 없다":            {holdsURL, holdText, ""},
		"다른 비밀로 서명했다":       {holdsURL, holdText, sign("another-secret-that-is-32-chars!!", webhookNow, http.MethodPost, holdsURL, holdText)},
		"한 시간 전의 서명이다":      {holdsURL, holdText, sign(gameSecret, webhookNow.Add(-time.Hour), http.MethodPost, holdsURL, holdText)},
		"한 시간 뒤의 서명이다":      {holdsURL, holdText, sign(gameSecret, webhookNow.Add(time.Hour), http.MethodPost, holdsURL, holdText)},
		"다른 사용자로 본문을 고쳤다":   {holdsURL, other, sign(gameSecret, webhookNow, http.MethodPost, holdsURL, holdText)},
		"본문 끝에 빈칸을 붙였다":     {holdsURL, holdText + " ", sign(gameSecret, webhookNow, http.MethodPost, holdsURL, holdText)},
		"확정의 서명을 반환에 붙였다":   {releaseURL, settleText, sign(gameSecret, webhookNow, http.MethodPost, captureURL, settleText)},
		"GET 의 서명을 붙였다":     {holdsURL, holdText, sign(gameSecret, webhookNow, http.MethodGet, holdsURL, holdText)},
		"주소 뒤에 값을 붙였다":      {holdsURL + "?retry=1", holdText, sign(gameSecret, webhookNow, http.MethodPost, holdsURL, holdText)},
		"본문만 서명했다":          {holdsURL, holdText, payment.Sign(gameSecret, webhookNow, []byte(holdText))},
		"결제 알림의 비밀로 서명했다":   {holdsURL, holdText, sign(webhookSecret, webhookNow, http.MethodPost, holdsURL, holdText)},
		"비밀을 그대로 실었다":       {holdsURL, holdText, gameSecret},
		"서명의 모양이 아니다":       {holdsURL, holdText, "Bearer the-token"},
		"서명이 없고 JSON 도 아니다": {holdsURL, "not json", ""},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			holds := &fakeHolds{hold: aHold(t), isNew: true}
			deps := holdDeps(holds)
			deps.WebhookSecret = webhookSecret
			headers := map[string]string{}
			if tc.signature != "" {
				headers[serviceauth.SignatureHeader] = tc.signature
			}

			response := send(t, deps, request{method: http.MethodPost, path: tc.path, body: tc.text, headers: headers, anonymous: true})

			if response.Code != http.StatusUnauthorized || holds.calls != 0 {
				t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d. 401 이고 부르지 않아야 한다", response.Code, holds.calls)
			}
			// 무엇이 틀렸는지 말하지 않는다
			if want := `{"detail":"요청의 서명이 맞지 않습니다."}`; body(response) != want {
				t.Errorf("본문 = %s", body(response))
			}
		})
	}
}

func TestASignatureThatCoversTheQueryIsAccepted(t *testing.T) {
	// 주소 뒤에 값이 붙어도, 그것까지 서명했으면 받는다. 서명하는 주소는 경로와 그 뒤의 값이다
	holds := &fakeHolds{hold: aHold(t), isNew: true}
	path := holdsURL + "?retry=1"

	response := asGame(t, holdDeps(holds), path, holdText)

	if response.Code != http.StatusCreated || holds.calls != 1 {
		t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, holds.calls)
	}
}

func TestAUserTokenCannotReachTheServiceRoutes(t *testing.T) {
	// 로그인한 사용자가 자기 홀드를 돌려받으려고, 또는 남의 크레딧을 빼려고 직접 부른다. 토큰은 서명이 아니다
	for _, tc := range []struct{ url, text string }{{holdsURL, holdText}, {captureURL, settleText}, {releaseURL, settleText}} {
		holds := &fakeHolds{hold: aHold(t), isNew: true}

		response := send(t, holdDeps(holds), request{method: http.MethodPost, path: tc.url, body: tc.text})

		if response.Code != http.StatusUnauthorized || holds.calls != 0 {
			t.Errorf("%s: 상태 코드 = %d, 서비스를 부른 횟수 = %d", tc.url, response.Code, holds.calls)
		}
	}
}

func TestAServerWithoutAGameSecretAcceptsNoServiceRequests(t *testing.T) {
	// 비밀이 빠진 서버다. 빈 비밀로 만든 서명이 통하면 누구나 남의 크레딧을 뺄 수 있다
	holds := &fakeHolds{hold: aHold(t), isNew: true}
	deps := httpapi.Dependencies{Holds: holds, GameServerSecret: "", Now: func() time.Time { return webhookNow }}
	forged := serviceauth.Sign("", webhookNow, http.MethodPost, holdsURL, []byte(holdText))

	response := send(t, deps, request{
		method: http.MethodPost, path: holdsURL, body: holdText, anonymous: true,
		headers: map[string]string{serviceauth.SignatureHeader: forged},
	})

	if response.Code != http.StatusUnauthorized || holds.calls != 0 {
		t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, holds.calls)
	}
}

func TestAServiceSignatureDoesNotOpenTheUserRoutesOrTheWebhook(t *testing.T) {
	// 게임 서버의 서명으로 사용자의 주소나 결제 알림의 주소를 열 수 없다. 자리마다 확인하는 것이 다르다
	notifier := &fakeNotifier{}
	deps := holdDeps(&fakeHolds{})
	deps.Notifier, deps.WebhookSecret = notifier, webhookSecret

	wallet := send(t, deps, request{
		method: http.MethodGet, path: httpapi.APIPrefix + "/wallet", anonymous: true,
		headers: serviceSigned(http.MethodGet, httpapi.APIPrefix+"/wallet", ""),
	})
	notified := send(t, deps, request{
		method: http.MethodPost, path: webhookURL, body: webhookText, anonymous: true,
		headers: map[string]string{payment.SignatureHeader: serviceauth.Sign(gameSecret, webhookNow, http.MethodPost, webhookURL, []byte(webhookText))},
	})

	if wallet.Code != http.StatusUnauthorized || notified.Code != http.StatusUnauthorized || notifier.calls != 0 {
		t.Errorf("지갑 = %d, 알림 = %d, 알림을 처리한 횟수 = %d", wallet.Code, notified.Code, notifier.calls)
	}
}

func TestOnlyPostReachesTheHoldRoutes(t *testing.T) {
	for _, method := range []string{http.MethodGet, http.MethodPut, http.MethodDelete} {
		holds := &fakeHolds{}
		response := send(t, holdDeps(holds), request{
			method: method, path: holdsURL, body: holdText, anonymous: true,
			headers: serviceSigned(method, holdsURL, holdText),
		})
		if response.Code != http.StatusNotFound && response.Code != http.StatusMethodNotAllowed || holds.calls != 0 {
			t.Errorf("%s: 상태 코드 = %d, 서비스를 부른 횟수 = %d", method, response.Code, holds.calls)
		}
	}
}

func TestHoldingCreditsEndToEndWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않는다. 실제 홀드 서비스, 지갑, DB 로 주소들을 끝까지 지난다
	pool := testenv.Pool(t)
	now := func() time.Time { return webhookNow }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: time.Hour})
	deps := httpapi.Dependencies{Wallet: wallets, Holds: hold.NewService(pool, now, wallets), GameServerSecret: gameSecret, Now: now}
	user := uuid.New()
	ctx := context.Background()
	if err := wallets.Deposit(ctx, user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	if err := wallets.GrantFree(ctx, user, 30); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}
	// placeText 는 이 사용자의 홀드를 거는 본문이다.
	placeText := func(reference string) string {
		return `{"user_id":"` + user.String() + `","reference":"` + reference + `","price_code":"narration.standard"}`
	}
	// balance 는 사용자가 자기 토큰으로 보는 잔액이다.
	balance := func() string {
		t.Helper()
		return body(sendAs(t, deps, user.String(), request{method: http.MethodGet, path: httpapi.APIPrefix + "/wallet"}))
	}
	wantBalance := func(when string, paid string, free string) {
		t.Helper()
		if got := balance(); !strings.Contains(got, `"paid":"`+paid+`"`) || !strings.Contains(got, `"free":"`+free+`"`) {
			t.Errorf("%s: 잔액 = %s. 기대 = 산 것 %s, 무료 %s", when, got, paid, free)
		}
	}

	// 서술이 끝난 라운드: 걸고, 응답을 못 받아 다시 걸고, 확정한다
	told := "table:" + uuid.NewString() + ":round:1"
	first := asGame(t, deps, holdsURL, placeText(told))
	again := asGame(t, deps, holdsURL, placeText(told))
	var placed, repeated struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(first.Body.Bytes(), &placed); err != nil || first.Code != http.StatusCreated {
		t.Fatalf("홀드 = %d %s, %v", first.Code, body(first), err)
	}
	if err := json.Unmarshal(again.Body.Bytes(), &repeated); err != nil || again.Code != http.StatusOK || repeated.ID != placed.ID {
		t.Fatalf("다시 건 홀드 = %d %s, %v", again.Code, body(again), err)
	}
	wantBalance("홀드를 건 뒤", "80", "0")
	captured := asGame(t, deps, captureURL, `{"reference":"`+told+`"}`)
	if captured.Code != http.StatusOK || !strings.Contains(body(captured), `"status":"captured"`) {
		t.Fatalf("확정 = %d %s", captured.Code, body(captured))
	}
	if refused := asGame(t, deps, releaseURL, `{"reference":"`+told+`"}`); refused.Code != http.StatusConflict {
		t.Errorf("확정한 홀드의 반환 = %d %s", refused.Code, body(refused))
	}
	wantBalance("확정한 뒤", "80", "0")

	// 서술이 실패한 라운드: 걸고, 돌려준다. 두 번 돌려 달라고 해도 한 번만 돌아간다
	failed := "table:" + uuid.NewString() + ":round:2"
	if response := asGame(t, deps, holdsURL, placeText(failed)); response.Code != http.StatusCreated {
		t.Fatalf("두 번째 홀드 = %d %s", response.Code, body(response))
	}
	wantBalance("두 번째 홀드를 건 뒤", "30", "0")
	for range 2 {
		released := asGame(t, deps, releaseURL, `{"reference":"`+failed+`"}`)
		if released.Code != http.StatusOK || !strings.Contains(body(released), `"status":"released"`) {
			t.Fatalf("반환 = %d %s", released.Code, body(released))
		}
	}
	wantBalance("돌려준 뒤", "80", "0")

	// 크레딧이 모자란 라운드: 402 이고 아무것도 남지 않는다
	if response := asGame(t, deps, holdsURL, placeText("table:"+uuid.NewString()+":round:3")); response.Code != http.StatusCreated {
		t.Fatalf("세 번째 홀드 = %d %s", response.Code, body(response))
	}
	short := "table:" + uuid.NewString() + ":round:4"
	if response := asGame(t, deps, holdsURL, placeText(short)); response.Code != http.StatusPaymentRequired {
		t.Errorf("모자랄 때의 홀드 = %d %s. 402 이어야 한다", response.Code, body(response))
	}
	if response := asGame(t, deps, captureURL, `{"reference":"`+short+`"}`); response.Code != http.StatusNotFound {
		t.Errorf("걸리지 않은 홀드의 확정 = %d %s. 404 이어야 한다", response.Code, body(response))
	}
	wantBalance("끝", "30", "0")

	// 사용자는 자기 내역에서 홀드와 반환을 본다
	history := body(sendAs(t, deps, user.String(), request{method: http.MethodGet, path: httpapi.APIPrefix + "/wallet/entries"}))
	if strings.Count(history, `"reason":"hold"`) != 4 || strings.Count(history, `"reason":"release"`) != 1 {
		t.Errorf("내역 = %s", history)
	}
	// 첫 홀드는 무료와 산 것에서 한 줄씩 뺐다. 두 줄 다 그 홀드의 번호를 갖는다
	if strings.Count(history, `"hold_id":"`+placed.ID+`"`) != 2 {
		t.Errorf("첫 홀드를 가리키는 줄이 둘이 아니다: %s", history)
	}
}
