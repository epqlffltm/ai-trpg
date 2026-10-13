// billing-server/internal/order/decide_test.go

// 결과를 모르는 주문을 찾는 것(ListStuck)과 운영자가 결과를 정하는 것(Decide)을 시험한다.
package order_test

import (
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// stillUnknown 은 승인 요청에 답하지 않고, 조회에도 아직 모른다고 답하는 결제 대행사다.
func stillUnknown() *scripted {
	return silent(payment.Result{Status: payment.StatusPending})
}

// decide 는 운영자로서 결과를 정한다.
func (f fixture) decide(orderID uuid.UUID, outcome order.Outcome) (order.Order, error) {
	f.t.Helper()
	return f.service.Decide(ctx(f.t), order.Decision{OrderID: orderID, Outcome: outcome, Reason: "상점관리자에서 확인", DecidedBy: "cli:tester"})
}

func TestDecidePaidCreditsTheOrder(t *testing.T) {
	f := setUp(t, stillUnknown())
	created, _ := f.unanswered()

	got, err := f.decide(created.ID, order.OutcomePaid)

	if err != nil || got.Status != order.StatusPaid || got.PaidAt == nil {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	// 결제 대행사가 승인했을 때와 같은 줄이 남는다
	f.wantPaidCredits(credits, 1)
	f.wantReasons("deposit")
}

func TestDecideFailedLeavesNoCredits(t *testing.T) {
	f := setUp(t, stillUnknown())
	created, _ := f.unanswered()

	got, err := f.decide(created.ID, order.OutcomeFailed)

	if err != nil || got.Status != order.StatusFailed || got.FailureCode != order.FailureCodeManual {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	f.wantPaidCredits(0, 0)
}

func TestDecideRefundedFinishesTheRefund(t *testing.T) {
	f := setUp(t, approving())
	paid, _ := f.unansweredRefund()

	got, err := f.decide(paid.ID, order.OutcomeRefunded)

	if err != nil || got.Status != order.StatusRefunded || got.RefundedAt == nil {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	f.wantPaidCredits(0, 1)
	f.wantReasons("deposit", "refund")
}

func TestDecidePaidOnARefundGivesTheCreditsBack(t *testing.T) {
	f := setUp(t, approving())
	paid, _ := f.unansweredRefund()

	got, err := f.decide(paid.ID, order.OutcomePaid)

	// 취소되지 않았다. 결제 대행사가 거절했을 때와 같이 크레딧이 그 묶음으로 돌아온다. 운영자가 고른 것이라 오류가 아니다
	if err != nil || got.Status != order.StatusPaid {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	f.wantPaidCredits(credits, 1)
	f.wantReasons("deposit", "refund", "unrefund")
}

func TestDecideRefusesOutcomesThatDoNotFitTheStatus(t *testing.T) {
	f := setUp(t, approving())
	refunding, _ := f.unansweredRefund()
	g := setUp(t, stillUnknown())
	confirming, _ := g.unanswered()

	if _, err := f.decide(refunding.ID, order.OutcomeFailed); !errors.Is(err, order.ErrOutcomeNotAllowed) {
		t.Errorf("refunding 을 failed 로: %v", err)
	}
	if _, err := g.decide(confirming.ID, order.OutcomeRefunded); !errors.Is(err, order.ErrOutcomeNotAllowed) {
		t.Errorf("confirming 을 refunded 로: %v", err)
	}
	if _, err := g.decide(confirming.ID, order.Outcome("expired")); !errors.Is(err, order.ErrOutcomeNotAllowed) {
		t.Errorf("모르는 결과: %v", err)
	}
	f.wantStatus(refunding.ID, order.StatusRefunding)
	g.wantStatus(confirming.ID, order.StatusConfirming)
	g.wantPaidCredits(0, 0)
}

func TestDecideRefusesFinishedAndMissingOrders(t *testing.T) {
	f := setUp(t, approving())
	paid := f.paid()

	if _, err := f.decide(paid.ID, order.OutcomeFailed); !errors.Is(err, order.ErrNotUndecided) {
		t.Errorf("끝난 주문: %v. ErrNotUndecided 여야 한다", err)
	}
	if _, err := f.decide(uuid.New(), order.OutcomePaid); !errors.Is(err, order.ErrNotFound) {
		t.Errorf("없는 주문: %v. ErrNotFound 여야 한다", err)
	}
	f.wantStatus(paid.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)
}

func TestDecideNeedsAReasonAndAName(t *testing.T) {
	f := setUp(t, stillUnknown())
	created, _ := f.unanswered()
	cases := map[string]order.Decision{
		"이유가 없다":    {OrderID: created.ID, Outcome: order.OutcomePaid, DecidedBy: "cli:tester"},
		"이유가 빈칸이다":  {OrderID: created.ID, Outcome: order.OutcomePaid, Reason: "  ", DecidedBy: "cli:tester"},
		"정한 사람이 없다": {OrderID: created.ID, Outcome: order.OutcomePaid, Reason: "확인"},
	}
	for name, decision := range cases {
		if _, err := f.service.Decide(ctx(t), decision); !errors.Is(err, order.ErrDecisionIncomplete) {
			t.Errorf("%s: %v. ErrDecisionIncomplete 여야 한다", name, err)
		}
	}
	f.wantStatus(created.ID, order.StatusConfirming)
	f.wantPaidCredits(0, 0)
}

func TestTwoDecisionsAtOnceTakeOnlyOne(t *testing.T) {
	// 운영자 둘이 같은 주문을 서로 다르게 정해도 하나만 쓰인다. 진 쪽은 오류를 받는다.
	// 둘이 함께 출발하게 한다. 둘 다 "아직 결과를 모른다"를 읽은 뒤에 하나가 먼저 끝내는 때가 생긴다
	for round := range 20 {
		f := setUp(t, stillUnknown())
		created, _ := f.unanswered()
		outcomes := []order.Outcome{order.OutcomePaid, order.OutcomeFailed}
		errs := make([]error, len(outcomes))
		start := make(chan struct{})
		var wg sync.WaitGroup
		for i, outcome := range outcomes {
			wg.Add(1)
			go func() {
				defer wg.Done()
				<-start
				_, errs[i] = f.decide(created.ID, outcome)
			}()
		}
		close(start)
		wg.Wait()

		won := 0
		for i, err := range errs {
			switch {
			case err == nil:
				won++
				f.wantStatus(created.ID, order.Status(outcomes[i]))
			case !errors.Is(err, order.ErrDecidedElsewhere) && !errors.Is(err, order.ErrNotUndecided):
				t.Errorf("%d 번째: 오류 = %v", round, err)
			}
		}
		if won != 1 {
			t.Fatalf("%d 번째: 쓰인 결정이 %d 개다: %v", round, won, errs)
		}
	}
}

func TestADecisionThatLosesTheRaceIsRefused(t *testing.T) {
	// 운영자가 "아직 결과를 모른다"를 읽은 뒤, 바꾸기 전에 다른 길(알림, 대사)이 먼저 다른 결과로 끝낸다.
	// 그 주문의 줄을 이 테스트가 잠가 두고, 운영자의 변경이 그 잠금을 기다리는 것을 본 뒤에 먼저 끝낸다
	f := setUp(t, stillUnknown())
	created, _ := f.unanswered()
	tx, err := f.pool.Begin(ctx(t))
	if err != nil {
		t.Fatalf("트랜잭션을 열지 못했다: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx(t)) }()
	if _, err := tx.Exec(ctx(t), "SELECT 1 FROM orders WHERE id = $1 FOR UPDATE", created.ID); err != nil {
		t.Fatalf("주문을 잠그지 못했다: %v", err)
	}
	type answer struct {
		order order.Order
		err   error
	}
	done := make(chan answer, 1)
	go func() {
		decided, err := f.decide(created.ID, order.OutcomePaid)
		done <- answer{decided, err}
	}()
	f.waitForLockOn("MarkPaid")
	if _, err := tx.Exec(ctx(t), "UPDATE orders SET status = 'failed', failure_code = 'card_declined', updated_at = $2 WHERE id = $1",
		created.ID, f.clock.Now()); err != nil {
		t.Fatalf("주문을 끝내지 못했다: %v", err)
	}
	if err := tx.Commit(ctx(t)); err != nil {
		t.Fatalf("커밋하지 못했다: %v", err)
	}

	got := <-done

	if !errors.Is(got.err, order.ErrDecidedElsewhere) || got.order.Status != order.StatusFailed {
		t.Errorf("주문 = %+v, 오류 = %v. 먼저 끝난 failed 와 ErrDecidedElsewhere 여야 한다", got.order, got.err)
	}
	f.wantPaidCredits(0, 0)
}

// waitForLockOn 은 이름이 query 인 SQL 이 잠금을 기다리기 시작할 때까지 기다린다(5초까지).
func (f fixture) waitForLockOn(query string) {
	f.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		var waiting int
		err := f.pool.QueryRow(ctx(f.t), `SELECT count(*) FROM pg_stat_activity
			WHERE wait_event_type = 'Lock' AND query LIKE '%name: '||$1||' %'`, query).Scan(&waiting)
		if err != nil {
			f.t.Fatalf("잠금을 보지 못했다: %v", err)
		}
		if waiting > 0 {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	f.t.Fatalf("%s 가 잠금을 기다리지 않았다", query)
}

func TestListStuckFindsOnlyWhatIsUnknownForADay(t *testing.T) {
	f := setUpSweep(t, approving())
	paid, _ := f.unansweredRefund()
	refundedAt := f.clock.Now()
	g := setUpAt(t, f.pool, refundedAt, stillUnknown())
	confirming, _ := g.unanswered()
	finished := f.paid()

	// 하루가 되기 바로 전에는 없다
	f.clock.Advance(order.StuckAfter - time.Microsecond)
	before, err := f.service.ListStuck(ctx(t), order.StuckAfter, 1000)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	f.clock.Advance(time.Microsecond)
	after, err := f.service.ListStuck(ctx(t), order.StuckAfter, 1000)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}

	if contains(before, paid.ID) || contains(before, confirming.ID) {
		t.Errorf("하루가 되기 전인데 목록에 있다: %v", ids(before))
	}
	if !contains(after, paid.ID) || !contains(after, confirming.ID) || contains(after, finished.ID) {
		t.Errorf("하루가 지난 목록 = %v. refunding %v 와 confirming %v 만 있어야 한다", ids(after), paid.ID, confirming.ID)
	}
}

// contains 는 주문들 가운데 그 번호가 있는지 본다.
func contains(orders []order.Order, id uuid.UUID) bool {
	for _, o := range orders {
		if o.ID == id {
			return true
		}
	}
	return false
}

// ids 는 주문들의 번호다. 실패를 알릴 때 쓴다.
func ids(orders []order.Order) []uuid.UUID {
	list := make([]uuid.UUID, 0, len(orders))
	for _, o := range orders {
		list = append(list, o.ID)
	}
	return list
}
