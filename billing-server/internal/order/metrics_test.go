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

// measureWallet 는 이 테스트의 지갑이 원장에 적은 일을 메모리에 모은다. 주문이 txn.Run 으로 연 트랜잭션의 일이 세어지는지 본다.
func (f fixture) measureWallet() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := f.wallet.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("원장의 메트릭을 만들지 못했다: %v", err)
	}
	return recorder
}

// ledgerCount 는 원장의 일 가운데 reason, result 인 것의 수다. 세지 않았으면 0 이다.
func ledgerCount(recorder *metricstest.Recorder, reason string, result string) int64 {
	labels := []attribute.KeyValue{attribute.String("reason", reason), attribute.String("result", result)}
	if !recorder.HasPoint("billing_ledger_operations", labels...) {
		return 0
	}
	return recorder.Int64("billing_ledger_operations", labels...)
}

func TestPayingAnOrderCountsTheDepositAfterCommit(t *testing.T) {
	f := setUp(t, approving())
	recorder := f.measureWallet()

	f.paid()

	if got := ledgerCount(recorder, "deposit", "success"); got != 1 {
		t.Errorf("deposit/success = %d. 1 이어야 한다", got)
	}
}

func TestARefundAndARefusedRefundAreCountedInTheLedger(t *testing.T) {
	f := setUp(t, approving())
	refunded, refused := f.paid(), f.paid()
	recorder := f.measureWallet()

	if _, err := f.refund(refunded.ID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}
	f.provider.answerCancel(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil)
	if _, err := f.refund(refused.ID); !errors.Is(err, order.ErrRefundRefused) {
		t.Fatalf("오류 = %v. ErrRefundRefused 이어야 한다", err)
	}

	want := map[string]int64{"refund": 2, "unrefund": 1}
	for reason, count := range want {
		if got := ledgerCount(recorder, reason, "success"); got != count {
			t.Errorf("%s/success = %d. %d 여야 한다", reason, got, count)
		}
	}
}

// keyCount 는 주문의 중복 방지 키 가운데 outcome 인 것의 수다.
func keyCount(t *testing.T, recorder *metricstest.Recorder, outcome string) int64 {
	t.Helper()
	return recorder.Int64("billing_idempotency", attribute.String("kind", "order"), attribute.String("outcome", outcome))
}

func TestOrderKeysAreCountedAsFirstReplayedOrConflict(t *testing.T) {
	f := setUp(t, approving())
	recorder := f.measure()
	key := newKey()

	for range 2 {
		if _, _, err := f.service.Create(ctx(t), f.user, productID, key); err != nil {
			t.Fatalf("주문을 만들지 못했다: %v", err)
		}
	}
	// 같은 키로 다른 상품을 산다. 다시 보낸 것이 아니라 다른 요청이다
	if _, _, err := f.service.Create(ctx(t), f.user, "credits-5000", key); !errors.Is(err, order.ErrKeyReused) {
		t.Fatalf("오류 = %v. ErrKeyReused 여야 한다", err)
	}
	// 키의 모양이 틀린 것은 키의 결과가 아니다. 세지 않는다
	if _, _, err := f.service.Create(ctx(t), f.user, productID, "bad key!"); !errors.Is(err, order.ErrInvalidKey) {
		t.Fatalf("오류 = %v. ErrInvalidKey 여야 한다", err)
	}

	want := map[string]int64{"first": 1, "replayed": 1, "conflict": 1}
	for outcome, count := range want {
		if got := keyCount(t, recorder, outcome); got != count {
			t.Errorf("%s = %d. %d 여야 한다", outcome, got, count)
		}
	}
}
