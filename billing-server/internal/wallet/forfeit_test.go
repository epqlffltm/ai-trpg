// billing-server/internal/wallet/forfeit_test.go

// 탈퇴로 남은 크레딧을 없애는 일(forfeit.go)을 시험한다.
package wallet_test

import (
	"testing"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// forfeit 는 트랜잭션을 열어 남은 크레딧을 모두 없앤다.
func (f fixture) forfeit() wallet.Forfeited {
	f.t.Helper()
	var forfeited wallet.Forfeited
	err := txn.Run(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		var err error
		forfeited, err = f.service.ForfeitInTx(ctx(f.t), tx, f.user)
		return err
	})
	if err != nil {
		f.t.Fatalf("크레딧을 없애지 못했다: %v", err)
	}
	return forfeited
}

// lockExisting 은 트랜잭션을 열어 지갑을 잠가 본다.
func (f fixture) lockExisting() bool {
	f.t.Helper()
	var found bool
	err := txn.Run(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		var err error
		found, err = f.service.LockExisting(ctx(f.t), tx, f.user)
		return err
	})
	if err != nil {
		f.t.Fatalf("지갑을 잠그지 못했다: %v", err)
	}
	return found
}

func TestForfeitEmptiesEveryLotAndGrant(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(300)
	f.deposit(200)
	f.grant(50)
	f.spend(70) // 무료 50 을 먼저, 그다음 먼저 산 묶음에서 20

	got := f.forfeit()

	if got != (wallet.Forfeited{Paid: 480, Free: 0}) {
		t.Errorf("없앤 것 = %+v. 산 것 480(280 + 200), 무료 0 이어야 한다", got)
	}
	f.wantBalance(0, 0)
	f.wantRemaining(0, 0)
}

func TestForfeitIsWrittenAsOneOperationPerLine(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(100)
	f.grant(40)

	f.forfeit()

	rows := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 40},
		line{wallet.KindPaid, wallet.ReasonForfeit, -100},
		line{wallet.KindFree, wallet.ReasonForfeit, -40},
	)
	if rows[2].OperationID != rows[3].OperationID {
		t.Error("한 번에 없앤 줄들은 같은 작업 번호여야 한다")
	}
	if rows[2].LotID == nil || rows[3].GrantID == nil {
		t.Error("없앤 줄은 그 묶음을 가리켜야 한다")
	}
	f.wantBalance(0, 0)
}

func TestExpiredSilverIsExpiredNotForfeited(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week / 2)
	f.grant(20)
	f.clock.Advance(week / 2)

	got := f.forfeit()

	if got.Free != 20 {
		t.Errorf("없앤 무료 크레딧 = %d. 기한이 지난 30 은 사라진 것(expire)이고 없앤 것은 20 이다", got.Free)
	}
	f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonGrant, 20},
		line{wallet.KindFree, wallet.ReasonExpire, -30},
		line{wallet.KindFree, wallet.ReasonForfeit, -20},
	)
}

func TestForfeitTwiceWritesNothingMore(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.forfeit()
	before := len(f.ledger())

	got := f.forfeit()

	if got != (wallet.Forfeited{}) || len(f.ledger()) != before {
		t.Errorf("두 번째 = %+v, 원장 %d 줄 -> %d 줄. 남은 것이 없으면 아무것도 적지 않는다", got, before, len(f.ledger()))
	}
}

func TestLockExistingDoesNotCreateAWallet(t *testing.T) {
	f := setUp(t, freeFirst)

	if f.lockExisting() {
		t.Error("지갑이 없는 사람인데 있다고 했다")
	}
	if n := f.count("wallets"); n != 0 {
		t.Errorf("지갑이 %d 개 생겼다. 없는 지갑은 만들지 않는다", n)
	}
}

func TestLockExistingFindsAWallet(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(10)

	if !f.lockExisting() {
		t.Error("지갑이 있는데 없다고 했다")
	}
}
