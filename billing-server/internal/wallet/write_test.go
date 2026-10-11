// billing-server/internal/wallet/write_test.go

package wallet_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestDepositAddsPaidCredits(t *testing.T) {
	f := setUp(t, freeFirst)

	f.deposit(100)
	f.deposit(50)

	f.wantBalance(150, 0)
	rows := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindPaid, wallet.ReasonDeposit, 50},
	)
	// 따로 일어난 두 번의 충전은 작업 번호가 다르다. 산 크레딧의 줄에는 지급 묶음이 없다
	if rows[0].OperationID == rows[1].OperationID || rows[0].OperationID == uuid.Nil {
		t.Errorf("작업 번호가 줄마다 다르지 않다: %v, %v", rows[0].OperationID, rows[1].OperationID)
	}
	if rows[0].GrantID != nil {
		t.Errorf("산 크레딧의 줄에 지급 묶음 %d 가 적혔다", *rows[0].GrantID)
	}
	if !rows[0].CreatedAt.Equal(f.clock.Now()) {
		t.Errorf("줄의 시각 = %v, 기대 = %v", rows[0].CreatedAt, f.clock.Now())
	}
}

func TestGrantFreeAddsCreditsThatExpire(t *testing.T) {
	f := setUp(t, freeFirst)

	f.grant(30)

	f.wantBalance(0, 30)
	rows := f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 30})
	if rows[0].GrantID == nil {
		t.Fatal("무료 크레딧의 줄에 지급 묶음이 적히지 않았다")
	}

	// 사라지는 시각은 지급한 시각에서 기한만큼 뒤다
	var amount, remaining int64
	var expiresAt time.Time
	const query = "SELECT amount, remaining, expires_at FROM free_grants WHERE id = $1"
	if err := f.pool.QueryRow(ctx(t), query, *rows[0].GrantID).Scan(&amount, &remaining, &expiresAt); err != nil {
		t.Fatalf("지급 묶음을 읽지 못했다: %v", err)
	}
	if amount != 30 || remaining != 30 || !expiresAt.Equal(f.clock.Now().Add(week)) {
		t.Errorf("지급 묶음 = (%d, %d, %v), 기대 = (30, 30, %v)", amount, remaining, expiresAt, f.clock.Now().Add(week))
	}
}

func TestAmountsOutOfRangeAreRejected(t *testing.T) {
	for _, amount := range []credit.Amount{0, -1, -100, wallet.MaxAmount + 1} {
		f := setUp(t, freeFirst)
		calls := map[string]error{
			"Deposit":   f.service.Deposit(ctx(t), f.user, amount),
			"GrantFree": f.service.GrantFree(ctx(t), f.user, amount),
			"Spend":     f.service.Spend(ctx(t), f.user, amount),
		}
		for name, err := range calls {
			if !errors.Is(err, wallet.ErrInvalidAmount) {
				t.Errorf("%s(%d) = %v. ErrInvalidAmount 이어야 한다", name, amount, err)
			}
		}
		// 거절된 요청은 지갑조차 만들지 않는다
		if f.count("wallets") != 0 || f.count("ledger_entries") != 0 {
			t.Errorf("양 %d: 거절했는데 DB 에 줄이 생겼다", amount)
		}
	}
}

func TestTheLargestAmountIsAccepted(t *testing.T) {
	f := setUp(t, freeFirst)

	f.deposit(wallet.MaxAmount)
	f.grant(wallet.MaxAmount)
	f.spend(wallet.MaxAmount)

	f.wantBalance(wallet.MaxAmount, 0)
}

func TestSpendTakesFreeCreditsFirstByDefault(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)

	f.spend(50)

	f.wantBalance(80, 0)
	rows := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonSpend, -30},
		line{wallet.KindPaid, wallet.ReasonSpend, -20},
	)
	// 한 번에 쓴 것은 두 줄이어도 작업 번호가 같다
	if rows[2].OperationID != rows[3].OperationID {
		t.Errorf("한 번에 쓴 두 줄의 작업 번호가 다르다: %v, %v", rows[2].OperationID, rows[3].OperationID)
	}
	if rows[2].GrantID == nil || rows[1].GrantID == nil || *rows[2].GrantID != *rows[1].GrantID {
		t.Error("쓴 줄이 준 줄과 같은 지급 묶음을 가리키지 않는다")
	}
}

func TestSpendLeavesPaidCreditsAloneWhileFreeOnesLast(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)

	f.spend(20)

	f.wantBalance(100, 10)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonSpend, -20},
	)
}

func TestSpendTakesPaidCreditsFirstWhenConfigured(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(100)
	f.grant(30)

	f.spend(50)
	f.wantBalance(50, 30)

	f.spend(60)
	f.wantBalance(0, 20)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindPaid, wallet.ReasonSpend, -50},
		line{wallet.KindFree, wallet.ReasonSpend, -10},
		line{wallet.KindPaid, wallet.ReasonSpend, -50},
	)
}

func TestSpendTakesTheFreeCreditsThatExpireSoonestFirst(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)
	f.clock.Advance(24 * time.Hour)
	f.grant(10)
	f.clock.Advance(24 * time.Hour)
	f.grant(10)

	f.spend(15)

	// 가장 먼저 준 묶음이 비고, 둘째 묶음에서 5 가 빠지고, 셋째 묶음은 그대로다
	f.wantBalance(0, 15)
	var remaining []int64
	rows, err := f.pool.Query(ctx(t), "SELECT remaining FROM free_grants WHERE user_id = $1 ORDER BY expires_at", f.user)
	if err != nil {
		t.Fatalf("지급 묶음을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var value int64
		if err := rows.Scan(&value); err != nil {
			t.Fatalf("지급 묶음의 줄을 읽지 못했다: %v", err)
		}
		remaining = append(remaining, value)
	}
	if len(remaining) != 3 || remaining[0] != 0 || remaining[1] != 5 || remaining[2] != 10 {
		t.Errorf("묶음마다 남은 양 = %v, 기대 = [0 5 10]", remaining)
	}
}

func TestSpendOrderFollowsExpiryNotTheOrderOfGranting(t *testing.T) {
	f := setUp(t, freeFirst)
	// 먼저 준 것의 기한이 더 길다. 기한이 하루인 서버가 나중에 준 것이 먼저 사라진다
	f.grant(10)
	shorter := wallet.NewService(f.pool, f.clock.Now, wallet.Policy{FreeFirst: true, FreeTTL: 24 * time.Hour})
	if err := shorter.GrantFree(ctx(t), f.user, 10); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}

	f.spend(4)

	// 나중에 줬어도 먼저 사라지는 묶음에서 빠진다
	rows := f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 10},
		line{wallet.KindFree, wallet.ReasonGrant, 10},
		line{wallet.KindFree, wallet.ReasonSpend, -4},
	)
	if *rows[2].GrantID != *rows[1].GrantID {
		t.Error("먼저 사라지는 묶음이 아니라 먼저 준 묶음에서 뺐다")
	}
	f.wantBalance(0, 16)
}

func TestSpendingEverythingLeavesZero(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(40)
	f.grant(60)

	f.spend(100)

	f.wantBalance(0, 0)
	if err := f.service.Spend(ctx(t), f.user, 1); !errors.Is(err, wallet.ErrInsufficient) {
		t.Errorf("빈 지갑에서 썼다: %v", err)
	}
}

func TestSpendingMoreThanHeldChangesNothing(t *testing.T) {
	for name, policy := range map[string]wallet.Policy{"무료부터": freeFirst, "산 것부터": paidFirst} {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, policy)
			f.deposit(40)
			f.grant(60)

			err := f.service.Spend(ctx(t), f.user, 101)

			if !errors.Is(err, wallet.ErrInsufficient) {
				t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
			}
			// 되는 데까지 빼다가 멈추지 않는다. 한 줄도 바뀌지 않는다
			f.wantBalance(40, 60)
			f.wantLedger(
				line{wallet.KindPaid, wallet.ReasonDeposit, 40},
				line{wallet.KindFree, wallet.ReasonGrant, 60},
			)
		})
	}
}

func TestSpendingFromAWalletThatWasNeverFilled(t *testing.T) {
	f := setUp(t, freeFirst)

	err := f.service.Spend(ctx(t), f.user, 1)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
	// 실패한 요청이 만들던 지갑도 함께 되돌려진다
	if f.count("wallets") != 0 {
		t.Error("실패했는데 지갑이 생겼다")
	}
}

func TestUsersDoNotShareCredits(t *testing.T) {
	f := setUp(t, freeFirst)
	other := uuid.New()
	f.deposit(100)
	f.grant(30)

	// 다른 사용자는 이 크레딧을 보지도 쓰지도 못한다
	balance, err := f.service.Balance(ctx(t), other)
	if err != nil || balance != (wallet.Balance{}) {
		t.Errorf("다른 사용자의 잔액 = %+v, %v. 0 이어야 한다", balance, err)
	}
	if err := f.service.Spend(ctx(t), other, 1); !errors.Is(err, wallet.ErrInsufficient) {
		t.Errorf("다른 사용자가 썼다: %v", err)
	}
	f.wantBalance(100, 30)
}

func TestTheClockIsStoredAsTheDatabaseKeepsIt(t *testing.T) {
	// 서버의 시계는 다른 시간대이고 나노초까지 있다. DB 는 백만분의 1초까지만 적는다.
	// 맞추지 않고 쓰면 사라지는 시각의 비교가 어긋난다
	f := setUp(t, freeFirst)
	seoul := time.FixedZone("KST", 9*60*60)
	at := time.Date(2026, 3, 2, 18, 0, 0, 123456789, seoul)
	service := wallet.NewService(f.pool, func() time.Time { return at }, freeFirst)

	if err := service.GrantFree(ctx(t), f.user, 30); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}

	rows := f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 30})
	if want := at.Truncate(time.Microsecond); !rows[0].CreatedAt.Equal(want) {
		t.Errorf("줄의 시각 = %v, 기대 = %v", rows[0].CreatedAt, want)
	}
	f.wantBooksToMatch()
}
