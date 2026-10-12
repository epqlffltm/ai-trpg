// billing-server/internal/httpapi/webhook_test.go

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

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const (
	webhookURL    = httpapi.APIPrefix + "/webhooks/payment"
	webhookSecret = "this-is-a-test-secret-of-32-chars!"
	webhookText   = `{"order_id":"` + orderID + `","payment_key":"fake_timeout_ok_1"}`
)

// webhookNow 는 테스트의 서버가 아는 지금 시각이다.
var webhookNow = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

// fakeNotifier 는 정해 둔 대로 답하는 가짜 알림 처리기다.
type fakeNotifier struct {
	err        error
	calls      int
	orderID    uuid.UUID
	paymentKey string
}

func (f *fakeNotifier) Notify(_ context.Context, id uuid.UUID, paymentKey string) error {
	f.calls++
	f.orderID, f.paymentKey = id, paymentKey
	return f.err
}

// webhook 은 알림을 보낸다. 토큰은 붙이지 않는다. signature 가 비어 있으면 서명 머리말도 붙이지 않는다.
func webhook(t *testing.T, notifier httpapi.PaymentNotifier, text string, signature string) *httptest.ResponseRecorder {
	t.Helper()
	deps := httpapi.Dependencies{Notifier: notifier, WebhookSecret: webhookSecret, Now: func() time.Time { return webhookNow }}
	headers := map[string]string{}
	if signature != "" {
		headers[payment.SignatureHeader] = signature
	}
	return send(t, deps, request{method: http.MethodPost, path: webhookURL, body: text, headers: headers, anonymous: true})
}

// signed 는 본문에 지금 시각으로 서명한 머리말을 만든다.
func signed(text string) string {
	return payment.Sign(webhookSecret, webhookNow, []byte(text))
}

func TestASignedNotificationIsHandedToTheService(t *testing.T) {
	notifier := &fakeNotifier{}

	response := webhook(t, notifier, webhookText, signed(webhookText))

	// 토큰 없이도 받는다. 결제 대행사는 사용자의 토큰이 없다
	if response.Code != http.StatusOK || body(response) != `{"received":true}` {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if notifier.calls != 1 || notifier.orderID.String() != orderID || notifier.paymentKey != "fake_timeout_ok_1" {
		t.Errorf("서비스가 받은 것 = %d 번, %v, %q", notifier.calls, notifier.orderID, notifier.paymentKey)
	}
}

func TestNotificationsWithoutAValidSignatureAreRefusedUnread(t *testing.T) {
	other := `{"order_id":"` + orderID + `","payment_key":"fake_timeout_ok_2"}`
	cases := map[string]struct {
		text      string
		signature string
	}{
		"서명이 없다":         {webhookText, ""},
		"다른 본문의 서명이다":    {webhookText, signed(other)},
		"다른 비밀로 서명했다":    {webhookText, payment.Sign("another-secret-that-is-32-chars!!", webhookNow, []byte(webhookText))},
		"한 시간 전의 서명이다":   {webhookText, payment.Sign(webhookSecret, webhookNow.Add(-time.Hour), []byte(webhookText))},
		"서명의 모양이 아니다":    {webhookText, "Bearer the-token"},
		"본문 끝에 빈칸을 붙였다":  {webhookText + " ", signed(webhookText)},
		"본문이 JSON 도 아니다": {"not json", ""},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			notifier := &fakeNotifier{}

			response := webhook(t, notifier, tc.text, tc.signature)

			if response.Code != http.StatusUnauthorized || notifier.calls != 0 {
				t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d. 401 이고 부르지 않아야 한다", response.Code, notifier.calls)
			}
		})
	}
}

func TestAUserTokenDoesNotReplaceTheSignature(t *testing.T) {
	// 로그인한 사용자가 자기 주문을 치른 것으로 만들려고 알림을 흉내 낸다. 토큰은 서명이 아니다
	notifier := &fakeNotifier{}
	deps := httpapi.Dependencies{Notifier: notifier, WebhookSecret: webhookSecret, Now: func() time.Time { return webhookNow }}

	response := send(t, deps, request{method: http.MethodPost, path: webhookURL, body: webhookText})

	if response.Code != http.StatusUnauthorized || notifier.calls != 0 {
		t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, notifier.calls)
	}
}

func TestAServerWithoutASecretAcceptsNoNotifications(t *testing.T) {
	// 비밀이 빠진 서버다. 빈 비밀로 만든 서명이 통하면 누구나 알림을 꾸며 낼 수 있다
	notifier := &fakeNotifier{}
	deps := httpapi.Dependencies{Notifier: notifier, WebhookSecret: "", Now: func() time.Time { return webhookNow }}
	forged := payment.Sign("", webhookNow, []byte(webhookText))

	response := send(t, deps, request{
		method: http.MethodPost, path: webhookURL, body: webhookText, anonymous: true,
		headers: map[string]string{payment.SignatureHeader: forged},
	})

	if response.Code != http.StatusUnauthorized || notifier.calls != 0 {
		t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, notifier.calls)
	}
}

func TestSignedButUnusableNotificationsAreBadRequests(t *testing.T) {
	texts := map[string]string{
		"JSON 이 아니다":        "order_id=1",
		"주문 번호가 없다":         `{"payment_key":"fake_ok_1"}`,
		"주문 번호가 UUID 가 아니다": `{"order_id":"42","payment_key":"fake_ok_1"}`,
		"결제 번호가 없다":         `{"order_id":"` + orderID + `"}`,
		"결제 번호가 비었다":        `{"order_id":"` + orderID + `","payment_key":""}`,
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			notifier := &fakeNotifier{}

			response := webhook(t, notifier, text, signed(text))

			if response.Code != http.StatusBadRequest || notifier.calls != 0 {
				t.Errorf("상태 코드 = %d, 서비스를 부른 횟수 = %d", response.Code, notifier.calls)
			}
		})
	}
}

func TestANotificationThatCannotBeHandledAsksForARetry(t *testing.T) {
	notifier := &fakeNotifier{err: errors.New("provider is down: secret-detail")}

	response := webhook(t, notifier, webhookText, signed(webhookText))

	// 2xx 가 아니어야 결제 대행사가 다시 보낸다. 원인은 싣지 않는다
	if response.Code != http.StatusServiceUnavailable || strings.Contains(body(response), "secret-detail") {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestBuyingCreditsEndToEndWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않는다. 실제 주문 서비스, 지갑, DB, 가짜 결제 대행사로 주소들을 끝까지 지난다
	pool := testenv.Pool(t)
	now := func() time.Time { return webhookNow }
	services := realServices(t, pool, now)
	wallets, orders := services.Wallet, services.Orders
	deps := httpapi.Dependencies{Wallet: wallets, Orders: orders, Notifier: orders, WebhookSecret: webhookSecret, Now: now}
	user := uuid.NewString()
	// 토큰의 주인을 테스트마다 새 사용자로 바꾼다
	as := func(r request) *httptest.ResponseRecorder {
		t.Helper()
		return sendAs(t, deps, user, r)
	}
	// placeOrder 는 주문을 만들고 그 번호를 돌려준다.
	placeOrder := func() string {
		t.Helper()
		response := as(request{
			method: http.MethodPost, path: ordersURL, body: `{"product_id":"credits-5000"}`,
			headers: map[string]string{httpapi.IdempotencyHeader: "key-" + uuid.NewString()},
		})
		var created struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &created); err != nil || response.Code != http.StatusCreated {
			t.Fatalf("주문 = %d %s, %v", response.Code, response.Body.String(), err)
		}
		return created.ID
	}

	// 바로 승인되는 결제
	first := placeOrder()
	confirmed := as(request{
		method: http.MethodPost, path: ordersURL + "/" + first + "/confirm",
		body: `{"payment_key":"` + payment.FakeApproved + uuid.NewString() + `"}`,
	})
	if confirmed.Code != http.StatusOK || !strings.Contains(body(confirmed), `"status":"paid"`) {
		t.Fatalf("승인 = %d %s", confirmed.Code, body(confirmed))
	}
	if got := body(as(request{method: http.MethodGet, path: walletURL})); got != `{"paid":"5000","free":"0","total":"5000"}` {
		t.Errorf("잔액 = %s", got)
	}
	// 원장의 줄이 그 주문을 가리킨다
	if got := body(as(request{method: http.MethodGet, path: entriesURL})); !strings.Contains(got, `"reason":"deposit","amount":"5000","order_id":"`+first+`"`) {
		t.Errorf("원장 = %s", got)
	}

	// 답이 오지 않는 결제. 202 로 끝나고 크레딧은 아직 없다
	second := placeOrder()
	lateKey := payment.FakeTimeoutApproved + uuid.NewString()
	late := as(request{method: http.MethodPost, path: ordersURL + "/" + second + "/confirm", body: `{"payment_key":"` + lateKey + `"}`})
	if late.Code != http.StatusAccepted || !strings.Contains(body(late), `"status":"confirming"`) {
		t.Fatalf("답이 없는 승인 = %d %s", late.Code, body(late))
	}
	// 결제 대행사의 알림이 오면 마저 끝난다
	notice := `{"order_id":"` + second + `","payment_key":"` + lateKey + `"}`
	signedNotice := request{
		method: http.MethodPost, path: webhookURL, body: notice, anonymous: true,
		headers: map[string]string{payment.SignatureHeader: signed(notice)},
	}
	if response := as(signedNotice); response.Code != http.StatusOK {
		t.Fatalf("알림 = %d %s", response.Code, body(response))
	}
	if got := body(as(request{method: http.MethodGet, path: ordersURL + "/" + second})); !strings.Contains(got, `"status":"paid"`) {
		t.Errorf("알림 뒤의 주문 = %s", got)
	}
	if got := body(as(request{method: http.MethodGet, path: walletURL})); got != `{"paid":"10000","free":"0","total":"10000"}` {
		t.Errorf("알림 뒤의 잔액 = %s", got)
	}

	// 거절되는 결제. 크레딧은 그대로다
	third := placeOrder()
	declined := as(request{
		method: http.MethodPost, path: ordersURL + "/" + third + "/confirm",
		body: `{"payment_key":"` + payment.FakeDeclined + uuid.NewString() + `"}`,
	})
	if declined.Code != http.StatusOK || !strings.Contains(body(declined), `"status":"failed","failure_code":"card_declined"`) {
		t.Errorf("거절 = %d %s", declined.Code, body(declined))
	}
	if got := body(as(request{method: http.MethodGet, path: walletURL})); got != `{"paid":"10000","free":"0","total":"10000"}` {
		t.Errorf("거절 뒤의 잔액 = %s", got)
	}

	// 다른 사용자는 이 주문을 보지 못한다
	if response := sendAs(t, deps, uuid.NewString(), request{method: http.MethodGet, path: ordersURL + "/" + first}); response.Code != http.StatusNotFound {
		t.Errorf("남의 주문 = %d %s", response.Code, body(response))
	}
}
