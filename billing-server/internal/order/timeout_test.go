// billing-server/internal/order/timeout_test.go

// 결제 작업 전체의 시간 제한(#273)을 시험한다.
//
// 작업(승인, 알림, 청약철회, 운영자의 판정)은 요청의 취소와 떨어져 끝까지 가지만, 끝이 없지는 않다.
// 주문의 줄을 다른 트랜잭션이 잠가 두면 작업이 그 잠금을 기다린다. 그 기다림이 작업의 마감에서 멈추는지,
// 멈춘 뒤에 상태가 적어 둔 그대로 남는지, 잠금이 풀린 뒤 다시 보내면 크레딧과 환불이 한 번씩만 되는지 본다.
package order_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// shortTimeout 은 시험에서 작업에 주는 시간이다. 잠금을 기다리다 이만큼 지나면 멈춰야 한다.
const shortTimeout = 300 * time.Millisecond

// stopsWithin 은 작업이 마감에서 멈췄다고 볼 수 있는 가장 긴 시간이다. 마감보다 넉넉하다. 마감이 없으면 잠금이 풀릴 때까지 멈춰 있다.
const stopsWithin = 5 * time.Second

// lockOrder 는 다른 트랜잭션에서 주문의 줄을 잠근다. 돌려준 함수를 부르면 풀린다.
func lockOrder(t *testing.T, pool *pgxpool.Pool, orderID uuid.UUID) func() {
	t.Helper()
	tx, err := pool.Begin(ctx(t))
	if err != nil {
		t.Fatalf("트랜잭션을 열지 못했다: %v", err)
	}
	if _, err := tx.Exec(ctx(t), "SELECT id FROM orders WHERE id = $1 FOR UPDATE", orderID); err != nil {
		t.Fatalf("주문을 잠그지 못했다: %v", err)
	}
	released := false
	release := func() {
		if !released {
			released = true
			_ = tx.Rollback(ctx(t))
		}
	}
	t.Cleanup(release)
	return release
}

// wantTimedOutQuickly 는 작업이 ErrTimedOut 으로, 마감 근처에서 멈췄는지 본다.
func wantTimedOutQuickly(t *testing.T, err error, elapsed time.Duration) {
	t.Helper()
	if !errors.Is(err, order.ErrTimedOut) {
		t.Errorf("오류 = %v. ErrTimedOut 이어야 한다", err)
	}
	if elapsed < shortTimeout || elapsed > stopsWithin {
		t.Errorf("멈추기까지 %v. %v 와 %v 사이여야 한다", elapsed, shortTimeout, stopsWithin)
	}
}

func TestTheProviderGetsNoMoreTimeThanTheOperation(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	limit := 2 * time.Second

	if _, err := f.service.WithOperationTimeout(limit).Confirm(ctx(t), f.user, created.ID, newPaymentKey()); err != nil {
		t.Fatalf("승인을 요청하지 못했다: %v", err)
	}

	// 결제 대행사의 제한(10초)보다 작업의 남은 시간이 짧으면 그것이 결제 대행사의 제한이 된다
	if f.provider.deadline <= 0 || f.provider.deadline > limit {
		t.Errorf("결제 대행사에 준 시간 = %v. 0 보다 크고 %v 이하여야 한다", f.provider.deadline, limit)
	}
}

func TestAConfirmWaitingForALockedOrderStopsAtTheDeadline(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()
	release := lockOrder(t, f.pool, created.ID)

	started := time.Now()
	_, err := f.service.WithOperationTimeout(shortTimeout).Confirm(ctx(t), f.user, created.ID, paymentKey)
	elapsed := time.Since(started)
	release()

	wantTimedOutQuickly(t, err, elapsed)
	// 결제 대행사를 부르기 전에 멈췄다. 돈은 움직이지 않았다
	if confirms, _ := f.provider.calls(); confirms != 0 {
		t.Errorf("결제 대행사를 %d번 불렀다", confirms)
	}
	// 주문은 pending 이거나 confirming 이다. 이쪽이 기다림을 그만두어도 DB 는 취소 신호를 받기 전까지 그 쿼리를 쥐고 있다.
	// 그 사이에 잠금이 풀리면 결제 번호를 적는 한 줄짜리 쿼리(트랜잭션 밖)가 마저 적힌다.
	// 어느 쪽이든 결과를 모르는 상태라 다시 보내기와 대사가 끝낸다. DB 쪽의 시간 제한은 따로 잰다(#273 의 B)
	if stored := f.stored(created.ID); stored.Status != order.StatusPending && stored.Status != order.StatusConfirming {
		t.Errorf("주문의 상태 = %s. pending 이나 confirming 이어야 한다", stored.Status)
	}

	// 잠금이 풀린 뒤 같은 요청을 다시 보내면 끝난다. 크레딧은 한 번만 들어간다
	if again := f.confirm(created.ID, paymentKey); again.Status != order.StatusPaid {
		t.Errorf("다시 보낸 승인 = %+v", again)
	}
	f.wantPaidCredits(credits, 1)
}

func TestARefundWaitingForALockedOrderStopsAtTheDeadline(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	release := lockOrder(t, f.pool, paid.ID)

	started := time.Now()
	_, err := f.service.WithOperationTimeout(shortTimeout).Refund(ctx(t), f.user, paid.ID)
	elapsed := time.Since(started)
	release()

	wantTimedOutQuickly(t, err, elapsed)
	if calls := f.provider.cancelCalls(); calls != 0 {
		t.Errorf("결제 대행사에 취소를 %d번 보냈다", calls)
	}
	f.wantStatus(paid.ID, order.StatusPaid)

	// 다시 보내면 한 번만 취소된다
	refunded, err := f.refund(paid.ID)
	if err != nil || refunded.Status != order.StatusRefunded {
		t.Errorf("다시 보낸 청약철회 = %+v, %v", refunded, err)
	}
	if calls := f.provider.cancelCalls(); calls != 1 {
		t.Errorf("결제 대행사에 취소를 %d번 보냈다. 한 번이어야 한다", calls)
	}
}

func TestANotificationWaitingForALockedOrderStopsAtTheDeadline(t *testing.T) {
	f := setUp(t, silent(payment.Result{Status: payment.StatusApproved}))
	created := f.create()
	paymentKey := newPaymentKey()
	// 승인 요청에 답이 없어 결과를 모르는 채로 남았다
	if unanswered := f.confirm(created.ID, paymentKey); unanswered.Status != order.StatusConfirming {
		t.Fatalf("주문 = %+v", unanswered)
	}
	release := lockOrder(t, f.pool, created.ID)

	started := time.Now()
	err := f.service.WithOperationTimeout(shortTimeout).Notify(ctx(t), created.ID, paymentKey)
	elapsed := time.Since(started)
	release()

	// 알림을 보낸 결제 대행사는 오류를 받고 다시 보낸다
	wantTimedOutQuickly(t, err, elapsed)
	f.wantStatus(created.ID, order.StatusConfirming)

	if err := f.service.Notify(ctx(t), created.ID, paymentKey); err != nil {
		t.Fatalf("다시 온 알림을 처리하지 못했다: %v", err)
	}
	f.wantStatus(created.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
}

func TestADecisionWaitingForALockedOrderStopsAtTheDeadline(t *testing.T) {
	f := setUp(t, stillUnknown())
	created, _ := f.unanswered()
	release := lockOrder(t, f.pool, created.ID)

	decision := order.Decision{OrderID: created.ID, Outcome: order.OutcomePaid, Reason: "상점관리자에서 확인", DecidedBy: "cli:tester"}
	started := time.Now()
	_, err := f.service.WithOperationTimeout(shortTimeout).Decide(ctx(t), decision)
	elapsed := time.Since(started)
	release()

	wantTimedOutQuickly(t, err, elapsed)
	f.wantStatus(created.ID, order.StatusConfirming)

	if decided, err := f.decide(created.ID, order.OutcomePaid); err != nil || decided.Status != order.StatusPaid {
		t.Errorf("다시 정한 결과 = %+v, %v", decided, err)
	}
	f.wantPaidCredits(credits, 1)
}

func TestAnOperationThatFinishesInTimeIsNotMarkedTimedOut(t *testing.T) {
	// 거절은 오류지만 마감에 걸린 것이 아니다. ErrTimedOut 을 붙이지 않는다
	f := setUp(t, approving())
	_, err := f.service.WithOperationTimeout(shortTimeout).Refund(ctx(t), f.user, uuid.New())

	if !errors.Is(err, order.ErrNotFound) || errors.Is(err, order.ErrTimedOut) {
		t.Errorf("오류 = %v. ErrNotFound 만이어야 한다", err)
	}
}
