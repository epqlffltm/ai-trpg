// billing-server/internal/wallet/refund_test.go

// 청약철회에 쓰는 것을 시험한다. 그 주문의 묶음이 하나도 줄지 않았을 때만 비우고, 거절되면 다시 채운다.
package wallet_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// paidOrder 는 이 사용자의 주문을 만들고 크레딧 1,000 을 넣는다.
func (f fixture) paidOrder() uuid.UUID {
	f.t.Helper()
	orderID := f.newOrder()
	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		f.t.Fatalf("주문의 크레딧을 넣지 못했다: %v", err)
	}
	return orderID
}

// inTx 는 트랜잭션을 열어 run 을 부르고, run 의 오류에 따라 확정하거나 되돌린다.
func (f fixture) inTx(run func(pgx.Tx) error) error {
	f.t.Helper()
	return pgx.BeginFunc(ctx(f.t), f.pool, run)
}

func (f fixture) takeForRefund(orderID uuid.UUID) error {
	f.t.Helper()
	return f.inTx(func(tx pgx.Tx) error { return f.service.TakeForRefund(ctx(f.t), tx, f.user, orderID) })
}

func (f fixture) returnRefund(orderID uuid.UUID) error {
	f.t.Helper()
	return f.inTx(func(tx pgx.Tx) error { return f.service.ReturnRefund(ctx(f.t), tx, f.user, orderID) })
}

// lotFull 은 OrderLotFull 의 답이다.
func (f fixture) lotFull(orderID uuid.UUID) bool {
	f.t.Helper()
	full, err := f.service.OrderLotFull(ctx(f.t), f.user, orderID)
	if err != nil {
		f.t.Fatalf("묶음을 읽지 못했다: %v", err)
	}
	return full
}

func TestTakeForRefundEmptiesAnUntouchedOrderLot(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(50)
	orderID := f.paidOrder()
	if !f.lotFull(orderID) {
		t.Fatal("넣자마자 묶음이 가득 차 있지 않다")
	}

	if err := f.takeForRefund(orderID); err != nil {
		t.Fatalf("비우지 못했다: %v", err)
	}

	// 그 주문의 묶음만 비운다. 다른 묶음은 그대로다
	f.wantRemaining(50, 0)
	ledger := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 50},
		line{wallet.KindPaid, wallet.ReasonDeposit, 1000},
		line{wallet.KindPaid, wallet.ReasonRefund, -1000},
	)
	if *ledger[2].LotID != f.lots()[1].ID {
		t.Errorf("refund 줄의 묶음 = %d, 기대 = 주문의 묶음 %d", *ledger[2].LotID, f.lots()[1].ID)
	}
	if f.lotFull(orderID) {
		t.Error("비운 묶음이 가득 차 있다고 한다")
	}
	f.wantBalance(50, 0)
}

func TestReturnRefundRefillsTheOrderLot(t *testing.T) {
	f := setUp(t, paidFirst)
	orderID := f.paidOrder()
	if err := f.takeForRefund(orderID); err != nil {
		t.Fatalf("비우지 못했다: %v", err)
	}

	if err := f.returnRefund(orderID); err != nil {
		t.Fatalf("다시 채우지 못했다: %v", err)
	}

	f.wantRemaining(1000)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 1000},
		line{wallet.KindPaid, wallet.ReasonRefund, -1000},
		line{wallet.KindPaid, wallet.ReasonUnrefund, 1000},
	)
	if !f.lotFull(orderID) {
		t.Error("다시 채운 묶음이 가득 차 있지 않다")
	}
	f.wantBalance(1000, 0)

	// 비우지 않은 묶음을 또 채우면 넣은 양을 넘는다. DB 가 막고 아무것도 바뀌지 않는다
	var pgErr *pgconn.PgError
	if err := f.returnRefund(orderID); !errors.As(err, &pgErr) || pgErr.Code != checkViolation {
		t.Errorf("오류 = %v. SQLSTATE %s 로 거절해야 한다", err, checkViolation)
	}
	f.wantBalance(1000, 0)
}

func TestTakeForRefundRefusesALotThatWasTouched(t *testing.T) {
	cases := []struct {
		name  string
		touch func(f fixture)
	}{
		{"하나라도 썼다", func(f fixture) { f.spend(1) }},
		{"홀드로 묶였다", func(f fixture) { f.mustHold(1) }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := setUp(t, paidFirst)
			orderID := f.paidOrder()
			tc.touch(f)
			if f.lotFull(orderID) {
				t.Fatal("줄어든 묶음이 가득 차 있다고 한다")
			}

			err := f.takeForRefund(orderID)

			if !errors.Is(err, wallet.ErrLotUsed) {
				t.Errorf("오류 = %v. ErrLotUsed 이어야 한다", err)
			}
			f.wantRemaining(999)
			if f.count("ledger_entries") != 2 {
				t.Errorf("원장의 줄이 %d 개다. 바뀐 것이 없어야 한다", f.count("ledger_entries"))
			}
		})
	}
}

func TestTakeForRefundNeedsTheUsersOwnOrderLot(t *testing.T) {
	owner := setUp(t, paidFirst)
	orderID := owner.paidOrder()
	other := setUpAt(t, owner.pool, owner.clock, paidFirst)
	other.deposit(10)

	// 남의 주문은 없는 것과 같다. 주인의 묶음은 그대로다
	if err := other.takeForRefund(orderID); !errors.Is(err, wallet.ErrNoOrderLot) {
		t.Errorf("오류 = %v. ErrNoOrderLot 이어야 한다", err)
	}
	if err := other.returnRefund(orderID); !errors.Is(err, wallet.ErrNoOrderLot) {
		t.Errorf("오류 = %v. ErrNoOrderLot 이어야 한다", err)
	}
	if other.lotFull(orderID) {
		t.Error("남의 주문의 묶음이 보인다")
	}
	owner.wantRemaining(1000)
	other.wantBalance(10, 0)
}
