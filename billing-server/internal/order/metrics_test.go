// billing-server/internal/order/metrics_test.go

// 주문이 어느 상태가 되었는지 세는 것(billing_orders)을 시험한다. 실제 PostgreSQL 에서 돈다.
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
package order_test

import (
	"errors"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// measure 는 이 테스트의 주문 서비스가 바꾼 상태를 메모리에 모은다.
func (f fixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := f.service.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("주문의 메트릭을 만들지 못했다: %v", err)
	}
	return recorder
}

// wantBecame 는 상태마다 센 수가 기대와 같은지 본다. 적지 않은 상태는 세지 않았어야 한다.
func wantBecame(t *testing.T, recorder *metricstest.Recorder, want map[order.Status]int64) {
	t.Helper()
	all := []order.Status{
		order.StatusConfirming, order.StatusPaid, order.StatusFailed, order.StatusExpired, order.StatusRefunding, order.StatusRefunded,
	}
	for _, status := range all {
		label := attribute.String("status", string(status))
		count, counted := want[status]
		if !counted {
			if recorder.HasPoint("billing_orders", label) {
				t.Errorf("%s 를 셌다. 바뀌지 않은 상태다", status)
			}
			continue
		}
		if got := recorder.Int64("billing_orders", label); got != count {
			t.Errorf("%s = %d. %d 여야 한다", status, got, count)
		}
	}
}

func TestAPaidOrderIsCountedAsConfirmingThenPaid(t *testing.T) {
	f := setUp(t, approving())
	recorder := f.measure()
	created := f.create()

	paymentKey := newPaymentKey()
	f.confirm(created.ID, paymentKey)
	// 다시 보낸 승인 요청은 상태를 바꾸지 않는다. 다시 세지 않는다
	f.confirm(created.ID, paymentKey)

	wantBecame(t, recorder, map[order.Status]int64{order.StatusConfirming: 1, order.StatusPaid: 1})
}

func TestADeclinedOrderIsCountedAsFailed(t *testing.T) {
	f := setUp(t, declining())
	recorder := f.measure()

	f.confirm(f.create().ID, newPaymentKey())

	wantBecame(t, recorder, map[order.Status]int64{order.StatusConfirming: 1, order.StatusFailed: 1})
}

func TestAnUnansweredOrderIsOnlyConfirmingUntilAskedAgain(t *testing.T) {
	f := setUp(t, silent(payment.Result{Status: payment.StatusApproved}))
	recorder := f.measure()
	created := f.create()
	paymentKey := newPaymentKey()

	f.confirm(created.ID, paymentKey)
	wantBecame(t, recorder, map[order.Status]int64{order.StatusConfirming: 1})

	// 다시 보내면 결제 대행사에 물어 끝낸다. confirming 은 다시 세지 않는다
	f.confirm(created.ID, paymentKey)
	wantBecame(t, recorder, map[order.Status]int64{order.StatusConfirming: 1, order.StatusPaid: 1})
}

func TestAnOrderThatCouldNotBeCreditedIsNotCountedAsPaid(t *testing.T) {
	// 크레딧을 넣지 못해 트랜잭션을 되돌렸다. 주문은 confirming 에 남는다
	f := setUp(t, approving())
	f.service = newService(t, f.pool, f.clock.Now, f.provider, &brokenWallet{})
	recorder := f.measure()
	created := f.create()

	if _, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey()); err == nil {
		t.Fatal("크레딧을 넣지 못했는데 오류가 없다")
	}

	f.wantStatus(created.ID, order.StatusConfirming)
	wantBecame(t, recorder, map[order.Status]int64{order.StatusConfirming: 1})
}

func TestAnOrderConfirmedTooLateIsCountedAsExpiredOnce(t *testing.T) {
	f := setUp(t, approving())
	recorder := f.measure()
	created := f.create()
	f.clock.Advance(ttl)

	for range 2 {
		if _, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey()); !errors.Is(err, order.ErrExpired) {
			t.Fatalf("오류 = %v. ErrExpired 이어야 한다", err)
		}
	}

	wantBecame(t, recorder, map[order.Status]int64{order.StatusExpired: 1})
}

func TestExpireDueCountsTheOrdersItEnded(t *testing.T) {
	f := setUpSweep(t, approving())
	recorder := f.measure()
	for range 3 {
		f.create()
	}
	f.clock.Advance(ttl)

	if expired, err := f.service.ExpireDue(ctx(t), 2); err != nil || expired != 2 {
		t.Fatalf("끝낸 수 = %d, %v. 기대 = 2", expired, err)
	}

	wantBecame(t, recorder, map[order.Status]int64{order.StatusExpired: 2})
}

func TestARefundIsCountedAsRefundingThenRefunded(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	recorder := f.measure()

	if _, err := f.refund(paid.ID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}
	if _, err := f.refund(paid.ID); err != nil {
		t.Fatalf("다시 보낸 청약철회 = %v", err)
	}

	wantBecame(t, recorder, map[order.Status]int64{order.StatusRefunding: 1, order.StatusRefunded: 1})
}

func TestARefusedRefundCountsTheOrderAsPaidAgain(t *testing.T) {
	// 되돌린 주문은 다시 paid 가 된 것이다. 치른 주문의 수(rate)를 볼 때는 refunding 과 함께 본다
	f := setUp(t, approving())
	paid := f.paid()
	recorder := f.measure()
	f.provider.answerCancel(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil)

	if _, err := f.refund(paid.ID); !errors.Is(err, order.ErrRefundRefused) {
		t.Fatalf("오류 = %v. ErrRefundRefused 이어야 한다", err)
	}

	wantBecame(t, recorder, map[order.Status]int64{order.StatusRefunding: 1, order.StatusPaid: 1})
}
