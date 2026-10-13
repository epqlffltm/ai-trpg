// billing-server/internal/order/toss_test.go

// 주문을 토스페이먼츠(payment.Toss)에 이어 본다. 실제 토스페이먼츠 대신, 승인한 결제를 기억하는 가짜 서버를 띄운다.
// payment 패키지의 테스트가 답 하나하나의 판단을 본다면, 여기서는 주문의 상태와 크레딧까지 이어지는지 본다.
package order_test

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// tossDouble 은 승인한 결제를 기억하는 가짜 토스페이먼츠다.
type tossDouble struct {
	mu sync.Mutex
	// payments 는 승인한 결제들이다. 결제 번호로 찾는다
	payments map[string]map[string]any
	confirms int
	// rejectCode 가 있으면 승인 요청을 그 코드로 거절한다(403)
	rejectCode string
	// loseAnswer 가 true 면 승인은 하되 답으로 500 을 준다. 답을 잃은 것과 같다
	loseAnswer bool
	// loseCancels 는 취소를 하되 답으로 500 을 줄 횟수다. 0 이 되면 제대로 답한다
	loseCancels int
	cancels     int
}

func (d *tossDouble) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	d.mu.Lock()
	defer d.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	if r.Method == http.MethodPost && r.URL.Path == "/v1/payments/confirm" {
		d.confirm(w, r)
		return
	}
	if paymentKey, ok := strings.CutSuffix(strings.TrimPrefix(r.URL.Path, "/v1/payments/"), "/cancel"); ok && r.Method == http.MethodPost {
		d.cancel(w, paymentKey)
		return
	}
	found, ok := d.payments[strings.TrimPrefix(r.URL.Path, "/v1/payments/")]
	if r.Method != http.MethodGet || !ok {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"code":"NOT_FOUND_PAYMENT","message":"없음"}`))
		return
	}
	_ = json.NewEncoder(w).Encode(found)
}

// confirm 은 승인 요청을 받는다. 거절하거나, 승인해 기억하고 답한다.
func (d *tossDouble) confirm(w http.ResponseWriter, r *http.Request) {
	d.confirms++
	var body struct {
		PaymentKey string `json:"paymentKey"`
		OrderID    string `json:"orderId"`
		Amount     int64  `json:"amount"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if d.rejectCode != "" {
		w.WriteHeader(http.StatusForbidden)
		_, _ = fmt.Fprintf(w, `{"code":%q,"message":"거절"}`, d.rejectCode)
		return
	}
	approved := map[string]any{"paymentKey": body.PaymentKey, "orderId": body.OrderID, "status": "DONE", "totalAmount": body.Amount}
	d.payments[body.PaymentKey] = approved
	if d.loseAnswer {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"code":"FAILED_INTERNAL_SYSTEM_PROCESSING","message":"오류"}`))
		return
	}
	_ = json.NewEncoder(w).Encode(approved)
}

// cancel 은 취소 요청을 받는다. 승인한 결제면 취소해 기억한다. 몇 번을 받아도 한 번만 취소된다(멱등키와 같다).
func (d *tossDouble) cancel(w http.ResponseWriter, paymentKey string) {
	d.cancels++
	found, ok := d.payments[paymentKey]
	if !ok {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"code":"NOT_FOUND_PAYMENT","message":"없음"}`))
		return
	}
	found["status"] = "CANCELED"
	if d.loseCancels > 0 {
		d.loseCancels--
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"code":"FAILED_INTERNAL_SYSTEM_PROCESSING","message":"오류"}`))
		return
	}
	_ = json.NewEncoder(w).Encode(found)
}

// notification 은 그 결제의 상태가 바뀌었다는 알림의 본문이다. 토스페이먼츠가 보내는 모양이다.
func (d *tossDouble) notification(paymentKey string) []byte {
	d.mu.Lock()
	defer d.mu.Unlock()
	raw, _ := json.Marshal(map[string]any{
		"eventType": payment.TossPaymentStatusChanged, "createdAt": "2026-03-02T09:00:00.000000", "data": d.payments[paymentKey],
	})
	return raw
}

// approvedPayment 는 그 결제 번호로 승인한 결제다. 없으면 nil 이다.
func (d *tossDouble) approvedPayment(paymentKey string) map[string]any {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.payments[paymentKey]
}

// setUpToss 는 가짜 토스페이먼츠를 띄우고, 그것에 붙은 주문 서비스를 만든다.
func setUpToss(t *testing.T, double *tossDouble) fixture {
	t.Helper()
	double.payments = map[string]map[string]any{}
	server := httptest.NewServer(double)
	t.Cleanup(server.Close)
	f := setUp(t, approving())
	f.service = newService(t, f.pool, f.clock.Now, payment.NewToss("test_gsk_sandbox_0123456789", server.URL, server.Client()), f.wallet)
	return f
}

func TestTossApprovalPaysTheOrder(t *testing.T) {
	double := &tossDouble{}
	f := setUpToss(t, double)
	created := f.create()
	paymentKey := newPaymentKey()

	confirmed := f.confirm(created.ID, paymentKey)

	if confirmed.Status != order.StatusPaid {
		t.Fatalf("주문의 상태 = %s, 기대 = paid", confirmed.Status)
	}
	f.wantPaidCredits(credits, 1)
	// 토스페이먼츠에는 이 주문의 번호와 주문에 적힌 값이 갔다
	approved := double.approvedPayment(paymentKey)
	if approved["orderId"] != created.ID.String() || approved["totalAmount"] != price {
		t.Errorf("승인한 결제 = %v", approved)
	}
}

func TestTossRejectionFailsTheOrderWithItsCode(t *testing.T) {
	f := setUpToss(t, &tossDouble{rejectCode: "REJECT_CARD_PAYMENT"})
	created := f.create()

	confirmed := f.confirm(created.ID, newPaymentKey())

	if confirmed.Status != order.StatusFailed || confirmed.FailureCode != "REJECT_CARD_PAYMENT" {
		t.Errorf("주문 = %s(%s), 기대 = failed(REJECT_CARD_PAYMENT)", confirmed.Status, confirmed.FailureCode)
	}
	f.wantPaidCredits(0, 0)
}

func TestTossLostAnswerIsFinishedByLookup(t *testing.T) {
	double := &tossDouble{loseAnswer: true}
	f := setUpToss(t, double)
	created := f.create()
	paymentKey := newPaymentKey()

	// 토스페이먼츠는 승인했지만 답을 잃었다. 거절로 적지 않고 모르는 채로 둔다
	if first := f.confirm(created.ID, paymentKey); first.Status != order.StatusConfirming {
		t.Fatalf("첫 승인 요청의 상태 = %s, 기대 = confirming", first.Status)
	}
	f.wantPaidCredits(0, 0)

	// 같은 결제 번호로 다시 오면 승인을 다시 요청하지 않고 조회해서 끝낸다
	again := f.confirm(created.ID, paymentKey)

	if again.Status != order.StatusPaid {
		t.Errorf("다시 요청한 뒤의 상태 = %s, 기대 = paid", again.Status)
	}
	f.wantPaidCredits(credits, 1)
	double.mu.Lock()
	defer double.mu.Unlock()
	if double.confirms != 1 {
		t.Errorf("승인 요청을 %d 번 보냈다. 기대 = 1 번", double.confirms)
	}
}

// notify 는 알림의 본문을 읽어 주문 서비스에 넘긴다. 서버의 알림 주소가 하는 일과 같다.
func (f fixture) notify(raw []byte) error {
	f.t.Helper()
	notification, relevant, err := payment.ReadTossNotification(raw)
	if err != nil || !relevant {
		f.t.Fatalf("알림을 읽지 못했다: %v, %v", relevant, err)
	}
	return f.service.Notify(ctx(f.t), notification.OrderID, notification.PaymentKey)
}

func TestTossNotificationFinishesALostApproval(t *testing.T) {
	double := &tossDouble{loseAnswer: true}
	f := setUpToss(t, double)
	created := f.create()
	paymentKey := newPaymentKey()
	if first := f.confirm(created.ID, paymentKey); first.Status != order.StatusConfirming {
		t.Fatalf("첫 승인 요청의 상태 = %s, 기대 = confirming", first.Status)
	}

	// 사용자는 돌아오지 않았다. 토스페이먼츠가 결제의 상태가 바뀌었다고 알려 온다
	if err := f.notify(double.notification(paymentKey)); err != nil {
		t.Fatalf("알림을 처리하지 못했다: %v", err)
	}

	f.wantStatus(created.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
}

func TestTossNotificationFinishesALostCancel(t *testing.T) {
	double := &tossDouble{loseCancels: 1}
	f := setUpToss(t, double)
	paid := f.paid()
	if refunding, err := f.refund(paid.ID); err != nil || refunding.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v. refunding 이어야 한다", refunding, err)
	}

	// 토스페이먼츠는 취소했지만 답을 잃었다. 취소되었다는 알림이 온다. 같은 취소를 다시 보내 끝낸다
	if err := f.notify(double.notification(paid.PaymentKey)); err != nil {
		t.Fatalf("알림을 처리하지 못했다: %v", err)
	}

	f.wantStatus(paid.ID, order.StatusRefunded)
	f.wantPaidCredits(0, 1)
	double.mu.Lock()
	defer double.mu.Unlock()
	if double.cancels != 2 {
		t.Errorf("취소 요청을 %d 번 받았다. 기대 = 2 번", double.cancels)
	}
}
