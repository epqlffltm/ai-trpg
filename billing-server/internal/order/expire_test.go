// billing-server/internal/order/expire_test.go

// 주문의 만료와 정리 작업(ExpireDue), 대사(ResolveStale)를 시험한다.
// 정리 작업이나 대사를 부르는 테스트는 setUpSweep 을 쓴다. 둘은 사용자를 가리지 않아서 다른 테스트의 주문에 닿을 수 있다.
package order_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// staleAfter 는 대사가 "오래된 confirming"으로 보는 시간이다.
const staleAfter = 10 * time.Minute

// expiresAt 은 DB 에 적힌 주문의 만료 시각을 읽는다.
func (f fixture) expiresAt(orderID any) time.Time {
	f.t.Helper()
	var at time.Time
	if err := f.pool.QueryRow(ctx(f.t), "SELECT expires_at FROM orders WHERE id = $1", orderID).Scan(&at); err != nil {
		f.t.Fatalf("주문을 읽지 못했다: %v", err)
	}
	return at
}

// unsure 는 승인을 요청했지만 답을 받지 못해 confirming 에 남은 주문을 만든다.
func (f fixture) unsure() order.Order {
	f.t.Helper()
	created := f.create()
	f.provider.mu.Lock()
	f.provider.confirmErr = payment.ErrUnknownOutcome
	f.provider.mu.Unlock()
	defer func() {
		f.provider.mu.Lock()
		f.provider.confirmErr = nil
		f.provider.mu.Unlock()
	}()
	if got := f.confirm(created.ID, newPaymentKey()); got.Status != order.StatusConfirming {
		f.t.Fatalf("주문의 상태 = %s, 기대 = confirming", got.Status)
	}
	return created
}

// answer 는 결제 대행사가 조회에 줄 답을 바꾼다.
func (f fixture) answer(result payment.Result, err error) {
	f.provider.mu.Lock()
	defer f.provider.mu.Unlock()
	f.provider.lookup, f.provider.lookupErr = result, err
}

func TestCreateSetsTheExpiryOneTTLAhead(t *testing.T) {
	f := setUp(t, approving())

	created := f.create()

	want := f.clock.Now().Add(ttl)
	if !created.ExpiresAt.Equal(want) || !f.expiresAt(created.ID).Equal(want) {
		t.Errorf("만료 시각 = %v (DB %v), 기대 = %v", created.ExpiresAt, f.expiresAt(created.ID), want)
	}
}

func TestConfirmingAnExpiredOrderIsRefused(t *testing.T) {
	// 결제창을 열어 두고 하루가 지났다. 정리 작업보다 먼저 왔어도 승인을 요청하지 않는다
	f := setUp(t, approving())
	created := f.create()
	f.clock.Advance(ttl)

	_, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey())

	if !errors.Is(err, order.ErrExpired) {
		t.Fatalf("오류 = %v. ErrExpired 이어야 한다", err)
	}
	if confirms, lookups := f.provider.calls(); confirms != 0 || lookups != 0 {
		t.Errorf("결제 대행사를 불렀다: 승인 %d 번, 조회 %d 번", confirms, lookups)
	}
	// 거절하면서 expired 로 적는다. 다시 보내도 같은 답이다
	f.wantStatus(created.ID, order.StatusExpired)
	if _, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey()); !errors.Is(err, order.ErrExpired) {
		t.Errorf("다시 보낸 승인 요청 = %v", err)
	}
	f.wantPaidCredits(0, 0)
}

func TestConfirmingJustBeforeTheExpiryWorks(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	f.clock.Advance(ttl - time.Microsecond)

	paid := f.confirm(created.ID, newPaymentKey())

	if paid.Status != order.StatusPaid {
		t.Errorf("주문의 상태 = %s, 기대 = paid", paid.Status)
	}
	f.wantPaidCredits(credits, 1)
}

func TestAnExpiredOrderIsStillReturnedForItsKey(t *testing.T) {
	// 같은 키로 다시 만들면 새로 만들지 않고 만료된 주문을 돌려준다. 새로 사려면 새 키로 만든다
	f := setUp(t, approving())
	key := newKey()
	first, _, err := f.service.Create(ctx(t), f.user, productID, key)
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	f.clock.Advance(ttl)
	if _, err := f.service.Confirm(ctx(t), f.user, first.ID, newPaymentKey()); !errors.Is(err, order.ErrExpired) {
		t.Fatalf("오류 = %v", err)
	}

	again, isNew, err := f.service.Create(ctx(t), f.user, productID, key)

	if err != nil || isNew || again.ID != first.ID || again.Status != order.StatusExpired {
		t.Errorf("다시 만든 주문 = %+v, 새것 = %v, %v", again, isNew, err)
	}
	if f.count() != 1 {
		t.Errorf("주문이 %d 개다. 기대 = 1 개", f.count())
	}
}

func TestExpireDueEndsOnlyOverduePendingOrders(t *testing.T) {
	f := setUpSweep(t, approving())
	overdue := f.create()
	confirming := f.unsure()
	f.clock.Advance(time.Hour)
	fresh := f.create()
	f.clock.Advance(ttl - time.Hour)

	if _, err := f.service.ExpireDue(ctx(t), 100); err != nil {
		t.Fatalf("정리 작업이 실패했다: %v", err)
	}

	f.wantStatus(overdue.ID, order.StatusExpired)
	f.wantStatus(fresh.ID, order.StatusPending)
	// confirming 은 돈이 나갔을 수 있다. 만료 시각이 지나도 정리 작업이 끝내지 않는다. 대사가 결제 대행사에 묻는다
	f.wantStatus(confirming.ID, order.StatusConfirming)
	// 정리 작업이 끝낸 주문에 늦게 온 승인 요청도 거절한다
	if _, err := f.service.Confirm(ctx(t), f.user, overdue.ID, newPaymentKey()); !errors.Is(err, order.ErrExpired) {
		t.Errorf("오류 = %v. ErrExpired 이어야 한다", err)
	}
}

func TestExpireDueTakesTheOldestFirstUpToTheLimit(t *testing.T) {
	f := setUpSweep(t, approving())
	// 시각이 같으면 순서가 정해지지 않는다. 1분씩 띄워 만든다
	var orders []order.Order
	for range 3 {
		orders = append(orders, f.create())
		f.clock.Advance(time.Minute)
	}
	f.clock.Advance(ttl)

	expired, err := f.service.ExpireDue(ctx(t), 2)

	if err != nil || expired != 2 {
		t.Fatalf("끝낸 수 = %d, %v. 기대 = 2", expired, err)
	}
	f.wantStatus(orders[0].ID, order.StatusExpired)
	f.wantStatus(orders[1].ID, order.StatusExpired)
	f.wantStatus(orders[2].ID, order.StatusPending)
}

func TestResolveStaleFinishesOldConfirmingOrders(t *testing.T) {
	f := setUpSweep(t, approving())
	paid := f.unsure()
	f.clock.Advance(time.Minute)
	declined := f.unsure()
	f.clock.Advance(staleAfter)
	recent := f.unsure()

	// 결제 대행사는 첫 주문만 승인했다고 답한다(가짜는 모든 조회에 같은 답이라 차례로 바꾼다)
	f.answer(payment.Result{Status: payment.StatusApproved}, nil)
	first, err := f.service.ResolveStale(ctx(t), staleAfter, 1)
	if err != nil || first != (order.StaleReport{Found: 1, Paid: 1}) {
		t.Fatalf("첫 대사 = %+v, %v", first, err)
	}
	f.answer(payment.Result{Status: payment.StatusDeclined, Code: "card_declined"}, nil)
	second, err := f.service.ResolveStale(ctx(t), staleAfter, 100)

	if err != nil || second != (order.StaleReport{Found: 1, Failed: 1}) {
		t.Errorf("둘째 대사 = %+v, %v", second, err)
	}
	f.wantStatus(paid.ID, order.StatusPaid)
	f.wantStatus(declined.ID, order.StatusFailed)
	// 방금 confirming 이 된 주문은 아직 묻지 않는다. 승인을 요청한 쪽이 곧 다시 올 수 있다
	f.wantStatus(recent.ID, order.StatusConfirming)
	f.wantPaidCredits(credits, 1)
	// 승인을 다시 요청하지 않고 결과만 물었다
	if confirms, lookups := f.provider.calls(); confirms != 3 || lookups != 2 {
		t.Errorf("승인 %d 번, 조회 %d 번. 기대 = 승인 3 번(처음 요청), 조회 2 번", confirms, lookups)
	}
}

func TestResolveStaleLeavesWhatTheProviderCannotAnswer(t *testing.T) {
	f := setUpSweep(t, approving())
	pendingAtProvider, unreachable := f.unsure(), f.unsure()
	f.clock.Advance(staleAfter)

	f.answer(payment.Result{Status: payment.StatusPending}, nil)
	first, firstErr := f.service.ResolveStale(ctx(t), staleAfter, 1)
	f.answer(payment.Result{}, errors.New("provider is down"))
	second, secondErr := f.service.ResolveStale(ctx(t), staleAfter, 100)

	// 결제 대행사도 모르거나 답하지 않으면 confirming 그대로 둔다. 오류가 아니다. 다음 대사에서 다시 묻는다
	if firstErr != nil || first != (order.StaleReport{Found: 1, Unknown: 1}) {
		t.Errorf("첫 대사 = %+v, %v", first, firstErr)
	}
	if secondErr != nil || second.Unknown != second.Found || second.Found < 2 {
		t.Errorf("둘째 대사 = %+v, %v", second, secondErr)
	}
	f.wantStatus(pendingAtProvider.ID, order.StatusConfirming)
	f.wantStatus(unreachable.ID, order.StatusConfirming)
}

func TestResolveStaleKeepsGoingPastAFailingOrder(t *testing.T) {
	// 지갑이 고장 나 첫 주문에 크레딧을 넣지 못한다. 그 주문은 confirming 에 남고, 뒤의 주문은 끝난다
	f := setUpSweep(t, approving())
	stuck := f.unsure()
	f.clock.Advance(time.Minute)
	finished := f.unsure()
	f.clock.Advance(staleAfter)
	f.answer(payment.Result{Status: payment.StatusApproved}, nil)
	broken := &flakyWallet{real: f.wallet, failFor: stuck.ID}
	resolver := newService(t, f.pool, f.clock.Now, f.provider, broken)

	report, err := resolver.ResolveStale(ctx(t), staleAfter, 100)

	if err == nil || !strings.Contains(err.Error(), "wallet is broken") {
		t.Errorf("오류 = %v. 실패한 주문을 알려야 한다", err)
	}
	if report.Errored != 1 || report.Paid != 1 {
		t.Errorf("대사 = %+v. 기대 = 오류 1, 치름 1", report)
	}
	f.wantStatus(stuck.ID, order.StatusConfirming)
	f.wantStatus(finished.ID, order.StatusPaid)
}

func TestTheDatabaseKeepsExpiredOrdersWithoutAPaymentKey(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	f.clock.Advance(ttl)
	if _, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey()); !errors.Is(err, order.ErrExpired) {
		t.Fatalf("오류 = %v", err)
	}

	// expired 는 결제 번호가 없다. 결제 대행사에 간 적이 없다
	_, err := f.pool.Exec(ctx(t), "UPDATE orders SET payment_key = $2 WHERE id = $1", created.ID, newPaymentKey())
	if err == nil || !strings.Contains(err.Error(), "23514") {
		t.Errorf("오류 = %v. CHECK(23514)로 거절해야 한다", err)
	}
	// 만료 시각은 만든 시각보다 뒤다
	_, err = f.pool.Exec(ctx(t), "UPDATE orders SET expires_at = created_at WHERE id = $1", created.ID)
	if err == nil || !strings.Contains(err.Error(), "23514") {
		t.Errorf("오류 = %v. CHECK(23514)로 거절해야 한다", err)
	}
}

func TestNewServiceRejectsANonPositiveTTL(t *testing.T) {
	f := setUp(t, approving())
	for _, bad := range []time.Duration{0, -time.Hour} {
		if _, err := order.NewService(f.pool, f.clock.Now, f.provider, f.wallet, bad); !errors.Is(err, order.ErrInvalidTTL) {
			t.Errorf("ttl %v: %v. ErrInvalidTTL 이어야 한다", bad, err)
		}
	}
}

// flakyWallet 은 한 주문에만 크레딧을 넣지 못하는 지갑이다. 나머지는 진짜 지갑에 넘긴다.
type flakyWallet struct {
	real    order.Depositor
	failFor uuid.UUID
}

func (w *flakyWallet) DepositForOrder(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, orderID uuid.UUID) error {
	if orderID == w.failFor {
		return errors.New("wallet is broken")
	}
	return w.real.DepositForOrder(ctx, tx, userID, amount, orderID)
}
