// billing-server/internal/order/refund_test.go

// 청약철회를 시험한다. 실제 PostgreSQL 과 진짜 지갑에서 돌고, 결제 대행사만 정해 둔 대로 답한다.
package order_test

import (
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// paid 는 이 사용자의 주문을 만들어 치르고, 치른 주문을 돌려준다.
func (f fixture) paid() order.Order {
	f.t.Helper()
	created := f.create()
	paid := f.confirm(created.ID, newPaymentKey())
	if paid.Status != order.StatusPaid {
		f.t.Fatalf("주문을 치르지 못했다: %+v", paid)
	}
	return paid
}

// refund 는 청약철회를 요청한다.
func (f fixture) refund(orderID uuid.UUID) (order.Order, error) {
	f.t.Helper()
	return f.service.Refund(ctx(f.t), f.user, orderID)
}

// reasons 는 이 사용자의 원장에 적힌 이유들을 적힌 차례로 돌려준다.
func (f fixture) reasons() []string {
	f.t.Helper()
	rows, err := f.pool.Query(ctx(f.t), "SELECT reason FROM ledger_entries WHERE user_id = $1 ORDER BY id", f.user)
	if err != nil {
		f.t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	var list []string
	for rows.Next() {
		var reason string
		if err := rows.Scan(&reason); err != nil {
			f.t.Fatalf("원장을 읽지 못했다: %v", err)
		}
		list = append(list, reason)
	}
	return list
}

// wantReasons 는 원장의 이유들이 기대와 같은지 본다.
func (f fixture) wantReasons(want ...string) {
	f.t.Helper()
	got := f.reasons()
	if len(got) != len(want) {
		f.t.Errorf("원장 = %v, 기대 = %v", got, want)
		return
	}
	for i := range want {
		if got[i] != want[i] {
			f.t.Errorf("원장 = %v, 기대 = %v", got, want)
			return
		}
	}
}

func TestRefundCancelsThePaymentAndTakesTheCreditsBack(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	if !paid.Refundable || paid.RefundableUntil == nil || !paid.RefundableUntil.Equal(paid.PaidAt.Add(order.RefundWindow)) {
		t.Fatalf("치른 주문의 청약철회 = %v, %v", paid.Refundable, paid.RefundableUntil)
	}

	refunded, err := f.refund(paid.ID)

	if err != nil || refunded.Status != order.StatusRefunded || refunded.RefundedAt == nil || refunded.Refundable {
		t.Fatalf("주문 = %+v, %v", refunded, err)
	}
	f.wantStatus(paid.ID, order.StatusRefunded)
	f.wantPaidCredits(0, 1)
	f.wantReasons("deposit", "refund")
	// 결제 대행사에는 이 주문의 결제 번호, 주문 번호, 주문의 값으로 취소를 요청했다
	want := payment.Request{PaymentKey: paid.PaymentKey, OrderID: paid.ID, Amount: price}
	if f.provider.cancelCalls() != 1 || f.provider.cancels[0] != want {
		t.Errorf("취소 요청 = %+v, 기대 = %+v 한 번", f.provider.cancels, want)
	}
}

func TestRefundingAgainChangesNothing(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	if _, err := f.refund(paid.ID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}

	again, err := f.refund(paid.ID)

	if err != nil || again.Status != order.StatusRefunded {
		t.Errorf("주문 = %+v, %v", again, err)
	}
	if f.provider.cancelCalls() != 1 {
		t.Errorf("취소를 %d 번 요청했다. 기대 = 1 번", f.provider.cancelCalls())
	}
	f.wantReasons("deposit", "refund")
}

func TestARefusedRefundGivesTheCreditsBack(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	f.provider.answerCancel(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil)

	restored, err := f.refund(paid.ID)

	if !errors.Is(err, order.ErrRefundRefused) {
		t.Fatalf("오류 = %v. ErrRefundRefused 이어야 한다", err)
	}
	// 주문은 paid 로 돌아가고, 비웠던 크레딧이 같은 묶음으로 돌아온다. 다시 청약철회할 수 있다
	if restored.Status != order.StatusPaid {
		t.Errorf("주문의 상태 = %s, 기대 = paid", restored.Status)
	}
	f.wantStatus(paid.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
	f.wantReasons("deposit", "refund", "unrefund")
	if got, err := f.service.Get(ctx(t), f.user, paid.ID); err != nil || !got.Refundable {
		t.Errorf("되돌린 주문의 청약철회 = %+v, %v", got, err)
	}
}

func TestAnUnansweredRefundStaysRefundingUntilAskedAgain(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	f.provider.answerCancel(payment.Result{}, payment.ErrUnknownOutcome)

	first, err := f.refund(paid.ID)

	// 돈이 돌아갔는지 모른다. 크레딧은 비운 채로 둔다. 그사이에 그 크레딧을 쓸 수 없다
	if err != nil || first.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v", first, err)
	}
	f.wantPaidCredits(0, 1)
	if err := f.wallet.Spend(ctx(t), f.user, 1); !errors.Is(err, wallet.ErrInsufficient) {
		t.Errorf("환불 중인 크레딧을 썼다: %v", err)
	}

	// 다시 요청하면 같은 취소를 다시 보낸다. 취소는 다시 보내도 한 번만 된다
	f.provider.answerCancel(payment.Result{Status: payment.StatusCanceled}, nil)
	second, err := f.refund(paid.ID)

	if err != nil || second.Status != order.StatusRefunded {
		t.Errorf("주문 = %+v, %v", second, err)
	}
	if f.provider.cancelCalls() != 2 {
		t.Errorf("취소를 %d 번 요청했다. 기대 = 2 번", f.provider.cancelCalls())
	}
	f.wantReasons("deposit", "refund")
}

func TestAnUndecidedCancelStaysRefunding(t *testing.T) {
	// 결제 대행사가 답은 했지만 취소되었다고도 거절했다고도 하지 않는다(토스페이먼츠의 PARTIAL_CANCELED 같은 것)
	f := setUp(t, approving())
	paid := f.paid()
	f.provider.answerCancel(payment.Result{Status: payment.StatusPending}, nil)

	got, err := f.refund(paid.ID)

	if err != nil || got.Status != order.StatusRefunding || got.RefundedAt != nil {
		t.Errorf("주문 = %+v, %v. refunding 에 남아야 한다", got, err)
	}
	f.wantPaidCredits(0, 1)
	f.wantReasons("deposit", "refund")
}

func TestRefundIsOnlyWithinSevenDays(t *testing.T) {
	cases := []struct {
		name        string
		elapsed     time.Duration
		wantErr     error
		wantBlocked order.RefundBlock
	}{
		{"기한 바로 전(백만분의 1초 전)", order.RefundWindow - time.Microsecond, nil, ""},
		{"기한이 된 순간", order.RefundWindow, order.ErrRefundWindowClosed, order.RefundBlockWindowClosed},
		{"기한이 지난 뒤", order.RefundWindow + time.Hour, order.ErrRefundWindowClosed, order.RefundBlockWindowClosed},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := setUp(t, approving())
			paid := f.paid()
			f.clock.Advance(tc.elapsed)
			got, err := f.service.Get(ctx(t), f.user, paid.ID)
			if err != nil || got.Refundable != (tc.wantErr == nil) || got.RefundBlocked != tc.wantBlocked {
				t.Errorf("읽은 주문의 청약철회 = %v, 까닭 = %q, %v", got.Refundable, got.RefundBlocked, err)
			}

			_, err = f.refund(paid.ID)

			if !errors.Is(err, tc.wantErr) {
				t.Fatalf("오류 = %v, 기대 = %v", err, tc.wantErr)
			}
			if tc.wantErr != nil {
				f.wantStatus(paid.ID, order.StatusPaid)
				f.wantPaidCredits(credits, 1)
				if f.provider.cancelCalls() != 0 {
					t.Error("기한이 지났는데 취소를 요청했다")
				}
			}
		})
	}
}

func TestRefundNeedsUntouchedCredits(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()
	if err := f.wallet.Spend(ctx(t), f.user, 1); err != nil {
		t.Fatalf("크레딧을 쓰지 못했다: %v", err)
	}
	if got, _ := f.service.Get(ctx(t), f.user, paid.ID); got.Refundable || got.RefundBlocked != order.RefundBlockCreditsUsed {
		t.Errorf("하나 쓴 주문의 청약철회 = %v, 까닭 = %q. credits_used 여야 한다", got.Refundable, got.RefundBlocked)
	}

	_, err := f.refund(paid.ID)

	// 아무것도 바뀌지 않는다. 결제 대행사도 부르지 않는다
	if !errors.Is(err, order.ErrCreditsUsed) {
		t.Fatalf("오류 = %v. ErrCreditsUsed 이어야 한다", err)
	}
	f.wantStatus(paid.ID, order.StatusPaid)
	f.wantPaidCredits(credits-1, 1)
	if f.provider.cancelCalls() != 0 {
		t.Error("크레딧을 썼는데 취소를 요청했다")
	}
}

func TestOnlyPaidOrdersCanBeRefunded(t *testing.T) {
	f := setUp(t, declining())
	pending := f.create()
	failed := f.create()
	f.confirm(failed.ID, newPaymentKey())

	for name, id := range map[string]uuid.UUID{"pending": pending.ID, "failed": failed.ID} {
		if _, err := f.refund(id); !errors.Is(err, order.ErrNotRefundable) {
			t.Errorf("%s: 오류 = %v. ErrNotRefundable 이어야 한다", name, err)
		}
	}
	// 치르지 않은 주문은 까닭을 적지 않는다. 상태가 말한다
	if got, _ := f.service.Get(ctx(t), f.user, pending.ID); got.Refundable || got.RefundableUntil != nil || got.RefundBlocked != "" {
		t.Errorf("치르지 않은 주문의 청약철회 = %v, %v, %q", got.Refundable, got.RefundableUntil, got.RefundBlocked)
	}
	// 남의 주문과 없는 주문은 없는 것과 같다
	other := setUpAt(t, f.pool, startedAt, approving())
	if _, err := other.service.Refund(ctx(t), other.user, pending.ID); !errors.Is(err, order.ErrNotFound) {
		t.Errorf("남의 주문: %v", err)
	}
	if _, err := f.refund(uuid.New()); !errors.Is(err, order.ErrNotFound) {
		t.Errorf("없는 주문: %v", err)
	}
}

func TestConcurrentRefundsTakeTheCreditsOnce(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()

	var wg sync.WaitGroup
	results := make([]error, 10)
	for i := range results {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			_, results[i] = f.refund(paid.ID)
		}(i)
	}
	wg.Wait()

	// 늦게 온 요청은 진행 중인 환불을 마저 끝내거나(같은 취소를 다시 보낸다), 끝난 것을 받거나, 엇갈렸다는 답을 받는다
	for _, err := range results {
		if err != nil && !errors.Is(err, order.ErrRefundBusy) {
			t.Errorf("오류 = %v", err)
		}
	}
	f.wantStatus(paid.ID, order.StatusRefunded)
	f.wantPaidCredits(0, 1)
	f.wantReasons("deposit", "refund")
}

func TestResolveStaleFinishesOldRefunds(t *testing.T) {
	f := setUpSweep(t, approving())
	canceled, refused, recent := f.paid(), f.paid(), f.paid()
	f.provider.answerCancel(payment.Result{}, payment.ErrUnknownOutcome)
	for _, o := range []order.Order{canceled, refused} {
		if got, err := f.refund(o.ID); err != nil || got.Status != order.StatusRefunding {
			t.Fatalf("주문 = %+v, %v", got, err)
		}
		// 오래된 것부터 다룬다. 둘의 차례가 정해지게 시계를 민다
		f.clock.Advance(time.Minute)
	}
	f.clock.Advance(staleAfter)
	if got, err := f.refund(recent.ID); err != nil || got.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v", got, err)
	}

	// 결제 대행사는 첫 주문의 취소를 받아들인다
	f.provider.answerCancel(payment.Result{Status: payment.StatusCanceled}, nil)
	first, err := f.service.ResolveStale(ctx(t), staleAfter, 1)
	if err != nil || first != (order.StaleReport{Found: 1, Refunded: 1}) {
		t.Fatalf("첫 대사 = %+v, %v", first, err)
	}
	// 둘째 주문의 취소는 거절한다. 크레딧을 돌려놓고 paid 로 되돌린다. 대사에게는 오류가 아니다
	f.provider.answerCancel(payment.Result{Status: payment.StatusDeclined, Code: "NOT_CANCELABLE_PAYMENT"}, nil)
	second, err := f.service.ResolveStale(ctx(t), staleAfter, 100)

	if err != nil || second != (order.StaleReport{Found: 1, RefundRefused: 1}) {
		t.Errorf("둘째 대사 = %+v, %v", second, err)
	}
	f.wantStatus(canceled.ID, order.StatusRefunded)
	f.wantStatus(refused.ID, order.StatusPaid)
	// 방금 refunding 이 된 주문은 아직 다루지 않는다
	f.wantStatus(recent.ID, order.StatusRefunding)
	f.wantPaidCredits(credits, 3)
}
