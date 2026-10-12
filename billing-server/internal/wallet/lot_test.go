// billing-server/internal/wallet/lot_test.go

// 산 크레딧의 묶음을 시험한다. 들어올 때마다 묶음 하나, 먼저 들어온 묶음부터 쓰기, 홀드는 뺐던 묶음으로 돌아가기.
// 청약철회(#150)가 "그 주문의 크레딧이 하나도 줄지 않았나"를 이 묶음으로 본다.
package wallet_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// lotOf 는 원장의 줄이 가리키는 묶음의 번호다. 묶음이 없으면 테스트를 멈춘다.
func lotOf(t *testing.T, r row) int64 {
	t.Helper()
	if r.LotID == nil {
		t.Fatalf("원장의 줄에 묶음이 없다: %+v", r)
	}
	return *r.LotID
}

func TestEachDepositOpensItsOwnLot(t *testing.T) {
	f := setUp(t, freeFirst)
	orderID := f.newOrder()

	f.deposit(100)
	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		t.Fatalf("주문의 크레딧을 넣지 못했다: %v", err)
	}

	got := f.lots()
	if len(got) != 2 {
		t.Fatalf("묶음이 %d 개다. 기대 = 2 개: %+v", len(got), got)
	}
	// 주문 없이 넣은 것은 주문이 없는 묶음, 주문으로 넣은 것은 그 주문의 묶음이다
	if got[0].OrderID != nil || got[0].Amount != 100 || got[0].Remaining != 100 {
		t.Errorf("첫 묶음 = %+v", got[0])
	}
	if got[1].OrderID == nil || *got[1].OrderID != orderID || got[1].Amount != 1000 || got[1].Remaining != 1000 {
		t.Errorf("주문의 묶음 = %+v", got[1])
	}
	// 들어온 줄은 그 묶음을 가리킨다
	ledger := f.wantLedger(line{wallet.KindPaid, wallet.ReasonDeposit, 100}, line{wallet.KindPaid, wallet.ReasonDeposit, 1000})
	if lotOf(t, ledger[0]) != got[0].ID || lotOf(t, ledger[1]) != got[1].ID {
		t.Errorf("원장의 묶음 = %v, %v. 기대 = %d, %d", *ledger[0].LotID, *ledger[1].LotID, got[0].ID, got[1].ID)
	}
	f.wantBalance(1100, 0)
}

func TestSpendingTakesTheOldestLotFirst(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(100)
	f.deposit(50)
	f.deposit(70)

	f.spend(120)

	// 먼저 들어온 묶음을 다 쓴 뒤에 다음 묶음으로 넘어간다. 마지막 묶음은 그대로다
	f.wantRemaining(0, 30, 70)
	lots := f.lots()
	ledger := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindPaid, wallet.ReasonDeposit, 50},
		line{wallet.KindPaid, wallet.ReasonDeposit, 70},
		line{wallet.KindPaid, wallet.ReasonSpend, -100},
		line{wallet.KindPaid, wallet.ReasonSpend, -20},
	)
	if lotOf(t, ledger[3]) != lots[0].ID || lotOf(t, ledger[4]) != lots[1].ID {
		t.Errorf("쓴 줄의 묶음 = %d, %d. 기대 = %d, %d", *ledger[3].LotID, *ledger[4].LotID, lots[0].ID, lots[1].ID)
	}
	// 한 번 쓴 것이므로 두 줄은 같은 작업 번호다
	if ledger[3].OperationID != ledger[4].OperationID {
		t.Error("한 번 쓴 줄들의 작업 번호가 다르다")
	}
	f.wantBalance(100, 0)
}

func TestSpendingMixesLotsAndGrantsByThePolicy(t *testing.T) {
	cases := []struct {
		name          string
		policy        wallet.Policy
		wantRemaining []credit.Amount
		wantFree      credit.Amount
	}{
		// 무료 30 을 먼저 다 쓰고, 남은 50 을 산 묶음에서 먼저 들어온 것부터(40, 그다음 10)
		{"무료부터", freeFirst, []credit.Amount{0, 30}, 0},
		// 산 묶음 80 을 먼저 다 쓰고, 무료는 그대로
		{"산 것부터", paidFirst, []credit.Amount{0, 0}, 30},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := setUp(t, tc.policy)
			f.deposit(40)
			f.deposit(40)
			f.grant(30)

			f.spend(80)

			f.wantRemaining(tc.wantRemaining...)
			var paid credit.Amount
			for _, r := range tc.wantRemaining {
				paid += r
			}
			f.wantBalance(paid, tc.wantFree)
		})
	}
}

func TestReturnForHoldGoesBackToTheLotsItCameFrom(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(50)
	f.deposit(50)
	holdID := f.mustHold(70)
	f.wantRemaining(0, 30)
	// 홀드가 걸린 사이에 새로 들어온 묶음은 돌아오는 크레딧을 받지 않는다
	f.deposit(10)

	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	f.wantRemaining(50, 50, 10)
	lots := f.lots()
	ledger := f.ledger()
	// 돌아온 줄은 뺐던 줄과 같은 묶음을 같은 양만큼 가리킨다
	returned := map[int64]credit.Amount{}
	for _, r := range ledger {
		if r.Reason == wallet.ReasonRelease {
			returned[lotOf(t, r)] += r.Amount
		}
	}
	if returned[lots[0].ID] != 50 || returned[lots[1].ID] != 20 || len(returned) != 2 {
		t.Errorf("돌아온 양 = %v. 기대 = 첫 묶음 50, 둘째 묶음 20", returned)
	}
	f.wantBalance(110, 0)
}

func TestAnUntouchedOrderLotStaysFull(t *testing.T) {
	// 청약철회의 바탕이다. 먼저 산 것부터 쓰므로, 나중에 산 주문의 묶음은 앞의 것을 다 쓸 때까지 그대로다
	f := setUp(t, paidFirst)
	first, second := f.newOrder(), f.newOrder()
	if err := f.depositForOrder(first, 1000, nil); err != nil {
		t.Fatalf("첫 주문을 넣지 못했다: %v", err)
	}
	if err := f.depositForOrder(second, 1000, nil); err != nil {
		t.Fatalf("둘째 주문을 넣지 못했다: %v", err)
	}

	f.spend(999)
	f.wantRemaining(1, 1000)

	f.spend(2)
	f.wantRemaining(0, 999)
}
