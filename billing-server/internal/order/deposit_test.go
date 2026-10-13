// billing-server/internal/order/deposit_test.go

// 가상계좌(입금 대기)로 온 결제를 취소하고 끝내는 것을 시험한다.
package order_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// awaitingDeposit 은 승인과 조회에 "입금 대기"로 답하는 결제 대행사다. 취소에는 cancel 로 답한다.
func awaitingDeposit(cancel payment.Result, cancelErr error) *scripted {
	waiting := payment.Result{Status: payment.StatusAwaitingDeposit}
	return &scripted{confirm: waiting, lookup: waiting, cancel: cancel, cancelErr: cancelErr}
}

func TestAVirtualAccountIsCanceledAndTheOrderFails(t *testing.T) {
	f := setUp(t, awaitingDeposit(payment.Result{Status: payment.StatusCanceled}, nil))
	created := f.create()

	got := f.confirm(created.ID, newPaymentKey())

	if got.Status != order.StatusFailed || got.FailureCode != order.FailureCodeDepositUnsupported {
		t.Fatalf("주문 = %s(%s). failed(%s) 여야 한다", got.Status, got.FailureCode, order.FailureCodeDepositUnsupported)
	}
	f.wantPaidCredits(0, 0)
	// 그 주문의 결제를, 이유를 적어 취소했다
	if f.provider.cancelCalls() != 1 {
		t.Fatalf("취소를 %d 번 요청했다. 기대 = 1 번", f.provider.cancelCalls())
	}
	sent := f.provider.cancels[0]
	if sent.OrderID != created.ID || sent.Amount != price || sent.CancelReason != "가상계좌 미지원" {
		t.Errorf("취소 요청 = %+v", sent)
	}
}

func TestAVirtualAccountThatCannotBeCanceledStaysUnknown(t *testing.T) {
	cases := map[string]*scripted{
		"취소의 답이 없다":            awaitingDeposit(payment.Result{}, payment.ErrUnknownOutcome),
		"취소가 거절됐다(입금되었을 수 있다)": awaitingDeposit(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil),
	}
	for name, provider := range cases {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, provider)
			created := f.create()

			got := f.confirm(created.ID, newPaymentKey())

			// 돈이 오갔는지 모른다. 거절로 적지 않는다. 조회가 다시 본다
			if got.Status != order.StatusConfirming {
				t.Errorf("주문 = %s. confirming 이어야 한다", got.Status)
			}
			f.wantPaidCredits(0, 0)
		})
	}
}

func TestADepositMadeBeforeTheCancelIsPaid(t *testing.T) {
	f := setUp(t, awaitingDeposit(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil))
	created := f.create()
	paymentKey := newPaymentKey()
	f.confirm(created.ID, paymentKey)

	// 그사이 입금되었다. 같은 결제 번호로 다시 오면 조회하고 승인으로 끝낸다
	f.provider.mu.Lock()
	f.provider.lookup = payment.Result{Status: payment.StatusApproved}
	f.provider.mu.Unlock()
	got := f.confirm(created.ID, paymentKey)

	if got.Status != order.StatusPaid {
		t.Errorf("주문 = %s. paid 여야 한다", got.Status)
	}
	f.wantPaidCredits(credits, 1)
}

func TestANotificationOfAVirtualAccountCancelsIt(t *testing.T) {
	// 승인 요청의 답을 잃었다. 알림이 와서 조회하니 입금 대기다
	f := setUp(t, silent(payment.Result{Status: payment.StatusAwaitingDeposit}))
	f.provider.answerCancel(payment.Result{Status: payment.StatusCanceled}, nil)
	created, paymentKey := f.unanswered()

	if err := f.service.Notify(ctx(t), created.ID, paymentKey); err != nil {
		t.Fatalf("알림을 처리하지 못했다: %v", err)
	}

	if got := f.wantStatus(created.ID, order.StatusFailed); got.FailureCode != order.FailureCodeDepositUnsupported {
		t.Errorf("거절 이유 = %q", got.FailureCode)
	}
}

func TestARefundCarriesNoReasonOfItsOwn(t *testing.T) {
	// 청약철회의 취소는 이유를 따로 적지 않는다. 결제 대행사가 기본값(청약철회)을 쓴다
	f := setUp(t, approving())
	paid := f.paid()

	if _, err := f.refund(paid.ID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}

	if sent := f.provider.cancels[0]; sent.CancelReason != "" {
		t.Errorf("취소의 이유 = %q. 비어 있어야 한다", sent.CancelReason)
	}
}
