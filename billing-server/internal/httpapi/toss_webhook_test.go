// billing-server/internal/httpapi/toss_webhook_test.go

package httpapi_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
)

// tossPaymentChanged 는 문서의 모양을 따른 토스페이먼츠의 결제 상태 알림이다.
const tossPaymentChanged = `{"eventType":"PAYMENT_STATUS_CHANGED","createdAt":"2026-03-02T09:00:00.000000",` +
	`"data":{"paymentKey":"tgen_20260302abcd","orderId":"` + orderID + `","status":"DONE","totalAmount":1000}}`

// tossNotify 는 토스페이먼츠의 알림을 보낸다. 토큰도 서명도 붙이지 않는다. 토스페이먼츠는 둘 다 없다.
func tossNotify(t *testing.T, notifier httpapi.PaymentNotifier, text string) *httptest.ResponseRecorder {
	t.Helper()
	deps := httpapi.Dependencies{Notifier: notifier, TossWebhook: true}
	return send(t, deps, request{method: http.MethodPost, path: httpapi.TossWebhookPath, body: text, anonymous: true})
}

func TestTossNotificationAsksAboutThatPayment(t *testing.T) {
	notifier := &fakeNotifier{}

	response := tossNotify(t, notifier, tossPaymentChanged)

	if response.Code != http.StatusOK || body(response) != `{"received":true}` {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if notifier.calls != 1 || notifier.orderID.String() != orderID || notifier.paymentKey != "tgen_20260302abcd" {
		t.Errorf("처리기가 받은 것 = %d 번, %v, %q", notifier.calls, notifier.orderID, notifier.paymentKey)
	}
}

func TestTossNotificationsItDoesNotHandleAreAcknowledged(t *testing.T) {
	// 다시 보낼 까닭이 없는 알림이다. 200 으로 받고 아무것도 하지 않는다
	texts := map[string]string{
		"가상계좌의 입금 알림":      `{"createdAt":"x","secret":"s","status":"DONE","transactionKey":"t","orderId":"` + orderID + `"}`,
		"다른 종류의 알림":        `{"eventType":"CANCEL_STATUS_CHANGED","createdAt":"x","data":{}}`,
		"이 서버의 주문 번호가 아니다": `{"eventType":"PAYMENT_STATUS_CHANGED","data":{"paymentKey":"tgen_1","orderId":"order-1"}}`,
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			notifier := &fakeNotifier{}

			response := tossNotify(t, notifier, text)

			if response.Code != http.StatusOK || notifier.calls != 0 {
				t.Errorf("상태 코드 = %d, 처리기를 부른 횟수 = %d", response.Code, notifier.calls)
			}
		})
	}
}

func TestUnreadableTossNotificationsAreBadRequests(t *testing.T) {
	texts := map[string]string{
		"JSON 이 아니다": "eventType=PAYMENT_STATUS_CHANGED",
		"결제 번호가 없다":  `{"eventType":"PAYMENT_STATUS_CHANGED","data":{"orderId":"` + orderID + `"}}`,
		"너무 크다":      `{"eventType":"PAYMENT_STATUS_CHANGED","pad":"` + strings.Repeat("x", 70<<10) + `"}`,
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			notifier := &fakeNotifier{}

			response := tossNotify(t, notifier, text)

			if response.Code != http.StatusBadRequest || notifier.calls != 0 {
				t.Errorf("상태 코드 = %d, 처리기를 부른 횟수 = %d", response.Code, notifier.calls)
			}
		})
	}
}

func TestTossNotificationThatCouldNotBeAskedIsRetried(t *testing.T) {
	notifier := &fakeNotifier{err: errors.New(`dial tcp: lookup api.tosspayments.com: no such host`)}

	response := tossNotify(t, notifier, tossPaymentChanged)

	// 503 이면 토스페이먼츠가 같은 알림을 다시 보낸다. 오류의 내용은 싣지 않는다
	if response.Code != http.StatusServiceUnavailable || strings.Contains(body(response), "tosspayments.com") {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestTheTossAddressIsClosedUnlessTossIsPlugged(t *testing.T) {
	notifier := &fakeNotifier{}
	deps := httpapi.Dependencies{Notifier: notifier}

	response := send(t, deps, request{method: http.MethodPost, path: httpapi.TossWebhookPath, body: tossPaymentChanged, anonymous: true})

	if response.Code != http.StatusNotFound || notifier.calls != 0 {
		t.Errorf("상태 코드 = %d, 처리기를 부른 횟수 = %d", response.Code, notifier.calls)
	}
}

func TestALargePaymentObjectStillFits(t *testing.T) {
	// Payment 객체는 다른 주소들의 본문보다 크다(카드, 영수증, 취소 내역). 주문 주소의 한도(16KB)보다 커도 받는다
	notifier := &fakeNotifier{}
	text := `{"eventType":"PAYMENT_STATUS_CHANGED","data":{"paymentKey":"tgen_1","orderId":"` + orderID +
		`","cancels":[{"cancelReason":"` + strings.Repeat("x", 30<<10) + `"}]}}`

	response := tossNotify(t, notifier, text)

	if response.Code != http.StatusOK || notifier.calls != 1 {
		t.Errorf("상태 코드 = %d, 처리기를 부른 횟수 = %d", response.Code, notifier.calls)
	}
}
