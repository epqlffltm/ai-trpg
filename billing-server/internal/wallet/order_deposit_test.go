// billing-server/internal/wallet/order_deposit_test.go

package wallet_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// newOrder 는 이 사용자의 주문 한 줄을 DB 에 직접 넣고 그 번호를 돌려준다.
// 지갑의 테스트는 주문 서비스를 쓰지 않는다. 원장이 가리킬 주문의 줄만 있으면 된다.
func (f fixture) newOrder() uuid.UUID {
	f.t.Helper()
	id := uuid.New()
	const insert = `INSERT INTO orders (id, user_id, product_id, price, credits, status, idempotency_key, created_at, updated_at, expires_at)
		VALUES ($1, $2, 'credits-1000', 1000, 1000, 'pending', $3, $4, $4, $4::TIMESTAMPTZ + interval '1 day')`
	if _, err := f.pool.Exec(ctx(f.t), insert, id, f.user, "key-"+id.String(), f.clock.Now()); err != nil {
		f.t.Fatalf("주문을 넣지 못했다: %v", err)
	}
	return id
}

// depositForOrder 는 트랜잭션을 열어 주문의 크레딧을 넣고, after 가 돌려준 오류에 따라 확정하거나 되돌린다.
func (f fixture) depositForOrder(orderID uuid.UUID, amount credit.Amount, after error) error {
	f.t.Helper()
	return pgx.BeginFunc(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		if err := f.service.DepositForOrder(ctx(f.t), tx, f.user, amount, orderID); err != nil {
			return err
		}
		return after
	})
}

func TestDepositForOrderAddsPaidCreditsAndNamesTheOrder(t *testing.T) {
	f := setUp(t, freeFirst)
	orderID := f.newOrder()

	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		t.Fatalf("크레딧을 넣지 못했다: %v", err)
	}

	f.wantBalance(1000, 0)
	f.wantLedger(line{wallet.KindPaid, wallet.ReasonDeposit, 1000})
	// 원장을 읽으면 그 줄이 어느 주문의 것인지 나온다
	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 10)
	if err != nil || len(page.Entries) != 1 || page.Entries[0].OrderID == nil || *page.Entries[0].OrderID != orderID {
		t.Errorf("원장 = %+v, %v", page.Entries, err)
	}
}

func TestOtherLinesNameNoOrder(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)
	f.spend(120)

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 10)

	if err != nil || len(page.Entries) != 4 {
		t.Fatalf("원장 = %+v, %v", page.Entries, err)
	}
	for _, entry := range page.Entries {
		if entry.OrderID != nil {
			t.Errorf("주문으로 들어온 줄이 아닌데 주문 %v 가 적혔다: %+v", *entry.OrderID, entry)
		}
	}
}

func TestDepositForOrderIsUndoneWithTheCallersTransaction(t *testing.T) {
	// 부르는 쪽이 트랜잭션을 되돌리면 크레딧도 함께 없던 일이 된다. 지갑이 스스로 확정하지 않는다
	f := setUp(t, freeFirst)
	orderID := f.newOrder()
	rollback := errors.New("the caller changed its mind")

	err := f.depositForOrder(orderID, 1000, rollback)

	if !errors.Is(err, rollback) {
		t.Fatalf("오류 = %v", err)
	}
	f.wantBalance(0, 0)
	if f.count("wallets") != 0 || f.count("ledger_entries") != 0 {
		t.Error("되돌렸는데 지갑이나 원장에 줄이 남았다")
	}
}

func TestDepositForOrderRefusesTheSameOrderTwice(t *testing.T) {
	f := setUp(t, freeFirst)
	orderID := f.newOrder()
	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		t.Fatalf("크레딧을 넣지 못했다: %v", err)
	}

	err := f.depositForOrder(orderID, 1000, nil)

	// 부르는 쪽의 실수로 두 번 불러도 DB 가 둘째를 거절하고, 잔액도 함께 되돌려진다
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) || pgErr.Code != "23505" {
		t.Fatalf("오류 = %v. 중복이라는 오류(23505)여야 한다", err)
	}
	f.wantBalance(1000, 0)
	f.wantLedger(line{wallet.KindPaid, wallet.ReasonDeposit, 1000})
}

func TestDepositForOrderRejectsAmountsOutOfRange(t *testing.T) {
	f := setUp(t, freeFirst)
	orderID := f.newOrder()

	for _, amount := range []credit.Amount{0, -1, wallet.MaxAmount + 1} {
		if err := f.depositForOrder(orderID, amount, nil); !errors.Is(err, wallet.ErrInvalidAmount) {
			t.Errorf("양 %d: 오류 = %v. ErrInvalidAmount 이어야 한다", amount, err)
		}
	}
	f.wantBalance(0, 0)
}

func TestDepositForOrderRecordsWhatExpiredFirst(t *testing.T) {
	// 주문으로 넣을 때도 다른 변경과 같다. 기한이 지난 무료 크레딧을 먼저 정리한다
	f := setUp(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week)
	orderID := f.newOrder()

	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		t.Fatalf("크레딧을 넣지 못했다: %v", err)
	}

	f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonExpire, -30},
		line{wallet.KindPaid, wallet.ReasonDeposit, 1000},
	)
	f.wantBalance(1000, 0)
}
