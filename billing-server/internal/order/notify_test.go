// billing-server/internal/order/notify_test.go

package order_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// unanswered 는 승인을 요청했지만 답을 받지 못한 주문을 만든다. 결제 번호도 함께 돌려준다.
func (f fixture) unanswered() (order.Order, string) {
	f.t.Helper()
	created := f.create()
	paymentKey := newPaymentKey()
	if confirmed := f.confirm(created.ID, paymentKey); confirmed.Status != order.StatusConfirming {
		f.t.Fatalf("주문이 confirming 에 남지 않았다: %+v", confirmed)
	}
	return created, paymentKey
}

func TestANotificationFinishesAnUnansweredPayment(t *testing.T) {
	f := setUp(t, silent(payment.Result{Status: payment.StatusApproved}))
	created, paymentKey := f.unanswered()

	err := f.service.Notify(ctx(t), created.ID, paymentKey)

	if err != nil {
		t.Fatalf("알림을 처리하지 못했다: %v", err)
	}
	f.wantStatus(created.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
	// 알림을 믿지 않고 결제 대행사에 다시 물었다
	if _, lookups := f.provider.calls(); lookups != 1 {
		t.Errorf("조회 %d 번, 기대 = 1 번", lookups)
	}
	f.provider.lookedUp(t, created.ID, paymentKey)
}

func TestANotificationOfADeclineFailsTheOrder(t *testing.T) {
	f := setUp(t, silent(payment.Result{Status: payment.StatusDeclined, Code: "card_declined"}))
	created, paymentKey := f.unanswered()

	if err := f.service.Notify(ctx(t), created.ID, paymentKey); err != nil {
		t.Fatalf("알림을 처리하지 못했다: %v", err)
	}

	if failed := f.wantStatus(created.ID, order.StatusFailed); failed.FailureCode != "card_declined" {
		t.Errorf("거절된 이유 = %q", failed.FailureCode)
	}
	f.wantPaidCredits(0, 0)
}

func TestRepeatedNotificationsCreditOnce(t *testing.T) {
	// 결제 대행사는 같은 알림을 여러 번 보낸다
	f := setUp(t, silent(payment.Result{Status: payment.StatusApproved}))
	created, paymentKey := f.unanswered()

	for range 3 {
		if err := f.service.Notify(ctx(t), created.ID, paymentKey); err != nil {
			t.Fatalf("알림을 처리하지 못했다: %v", err)
		}
	}

	f.wantPaidCredits(credits, 1)
	// 끝난 주문의 알림은 결제 대행사에 묻지도 않는다
	if _, lookups := f.provider.calls(); lookups != 1 {
		t.Errorf("조회가 %d 번 갔다", lookups)
	}
}

func TestNotificationsWithNothingToFinishAreIgnored(t *testing.T) {
	f := setUp(t, approving())
	pending := f.create()
	paid := f.create()
	paidKey := newPaymentKey()
	f.confirm(paid.ID, paidKey)
	before, _ := f.provider.calls()

	cases := map[string]struct {
		orderID    uuid.UUID
		paymentKey string
	}{
		"모르는 주문": {uuid.New(), newPaymentKey()},
		"아직 승인을 요청하지 않은 주문": {pending.ID, newPaymentKey()},
		"이미 치른 주문":          {paid.ID, paidKey},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			if err := f.service.Notify(ctx(t), tc.orderID, tc.paymentKey); err != nil {
				t.Errorf("오류 = %v. 아무것도 하지 않고 nil 이어야 한다", err)
			}
		})
	}
	// 어느 주문도 바뀌지 않았고, 결제 대행사를 더 부르지도 않았다
	f.wantStatus(pending.ID, order.StatusPending)
	f.wantStatus(paid.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
	if confirms, lookups := f.provider.calls(); confirms != before || lookups != 0 {
		t.Errorf("승인 요청 %d 번, 조회 %d 번. 알림 때문에 더 부르면 안 된다", confirms, lookups)
	}
}

func TestANotificationForAnotherPaymentIsIgnored(t *testing.T) {
	// 주문 번호만 알아서는 그 주문을 치른 것으로 만들 수 없다. 결제 번호가 맞아야 한다
	f := setUp(t, silent(payment.Result{Status: payment.StatusApproved}))
	created, _ := f.unanswered()

	err := f.service.Notify(ctx(t), created.ID, newPaymentKey())

	if err != nil {
		t.Errorf("오류 = %v", err)
	}
	f.wantStatus(created.ID, order.StatusConfirming)
	f.wantPaidCredits(0, 0)
	if _, lookups := f.provider.calls(); lookups != 0 {
		t.Error("결제 번호가 다른 알림인데 결제 대행사에 물었다")
	}
}

func TestANotificationThatCannotBeCheckedIsAnError(t *testing.T) {
	// 결제 대행사에 묻지 못했다. 오류로 답해야 결제 대행사가 알림을 다시 보낸다
	f := setUp(t, &scripted{confirmErr: payment.ErrUnknownOutcome, lookupErr: errors.New("provider is down")})
	created, paymentKey := f.unanswered()

	err := f.service.Notify(ctx(t), created.ID, paymentKey)

	if err == nil {
		t.Error("결제 대행사에 묻지 못했는데 오류가 없다")
	}
	f.wantStatus(created.ID, order.StatusConfirming)
	f.wantPaidCredits(0, 0)
}

func TestANotificationWhileTheProviderStillDoesNotKnowChangesNothing(t *testing.T) {
	f := setUp(t, silent(payment.Result{Status: payment.StatusPending}))
	created, paymentKey := f.unanswered()

	if err := f.service.Notify(ctx(t), created.ID, paymentKey); err != nil {
		t.Errorf("오류 = %v", err)
	}

	f.wantStatus(created.ID, order.StatusConfirming)
	f.wantPaidCredits(0, 0)
}
