// billing-server/internal/wallet/expiry_test.go

package wallet_test

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestFreeCreditsLastUntilTheMomentTheyExpire(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)

	// 기한이 되기 바로 전까지는 그대로 있다. DB 가 적는 가장 작은 시간(백만분의 1초)만큼 모자라게 돌린다
	f.clock.Advance(week - time.Microsecond)
	f.wantBalance(0, 30)

	// 기한이 되는 그 순간에 사라진다
	f.clock.Advance(time.Microsecond)
	f.wantBalance(0, 0)
}

func TestPaidCreditsNeverExpire(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)

	f.clock.Advance(10 * 365 * 24 * time.Hour)

	f.wantBalance(100, 0)
	f.spend(100)
	f.wantBalance(0, 0)
}

func TestExpiredCreditsCannotBeSpent(t *testing.T) {
	for name, policy := range map[string]wallet.Policy{"무료부터": freeFirst, "산 것부터": paidFirst} {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, policy)
			f.deposit(10)
			f.grant(30)
			f.clock.Advance(week)

			// 사라진 30 을 보태야 되는 양은 쓸 수 없다
			if err := f.service.Spend(ctx(t), f.user, 11); !errors.Is(err, wallet.ErrInsufficient) {
				t.Fatalf("사라진 크레딧을 썼다: %v", err)
			}
			f.spend(10)
			f.wantBalance(0, 0)
		})
	}
}

func TestEachGrantExpiresOnItsOwnSchedule(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)
	f.clock.Advance(3 * 24 * time.Hour)
	f.grant(20)

	// 첫 묶음의 기한이 지났다. 둘째 묶음은 사흘 뒤에 준 것이라 아직 남아 있다
	f.clock.Advance(4 * 24 * time.Hour)
	f.wantBalance(0, 20)

	f.clock.Advance(3 * 24 * time.Hour)
	f.wantBalance(0, 0)
}

func TestReadingTheBalanceWritesNothing(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week)

	f.wantBalance(0, 0)

	// 읽기는 기한이 지난 것을 세지 않을 뿐이다. 사라졌다는 기록은 다음 변경이 남긴다
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 30})
}

func TestTheNextChangeRecordsWhatExpired(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)
	f.spend(10)
	f.clock.Advance(week)

	f.deposit(5)

	// 쓰고 남은 20 만 사라진 것으로 적힌다. 충전보다 먼저 적힌다
	f.wantBalance(5, 0)
	rows := f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonSpend, -10},
		line{wallet.KindFree, wallet.ReasonExpire, -20},
		line{wallet.KindPaid, wallet.ReasonDeposit, 5},
	)
	if rows[2].OperationID == rows[3].OperationID {
		t.Error("사라진 것과 충전이 같은 작업 번호로 묶였다. 서로 다른 일이다")
	}
	if rows[2].GrantID == nil || *rows[2].GrantID != *rows[0].GrantID {
		t.Error("사라진 줄이 준 줄과 같은 지급 묶음을 가리키지 않는다")
	}

	// 한 번 적은 것을 다음 변경이 또 적지 않는다
	f.deposit(5)
	if got := len(f.ledger()); got != 5 {
		t.Errorf("원장이 %d 줄이다. 기대 = 5 줄: %+v", got, lines(f.ledger()))
	}
}

func TestGrantsExpiringTogetherShareOneOperation(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)
	f.clock.Advance(time.Hour)
	f.grant(20)
	f.clock.Advance(week)

	f.grant(1)

	rows := f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 10},
		line{wallet.KindFree, wallet.ReasonGrant, 20},
		line{wallet.KindFree, wallet.ReasonExpire, -10},
		line{wallet.KindFree, wallet.ReasonExpire, -20},
		line{wallet.KindFree, wallet.ReasonGrant, 1},
	)
	if rows[2].OperationID != rows[3].OperationID {
		t.Error("한 번에 사라진 두 묶음의 작업 번호가 다르다")
	}
	f.wantBalance(0, 1)
}

func TestAFailedSpendDoesNotLeaveAHalfWrittenExpiry(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week)

	// 실패한 요청은 정리하던 것까지 모두 되돌린다
	if err := f.service.Spend(ctx(t), f.user, 1); !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 30})

	// 다음에 성공하는 변경이 남긴다
	f.deposit(1)
	f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonExpire, -30},
		line{wallet.KindPaid, wallet.ReasonDeposit, 1},
	)
	f.wantBalance(1, 0)
}

func TestChangingTheLifetimeAffectsOnlyNewGrants(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)

	// 기한을 하루로 바꾼 서버가 같은 사용자에게 또 준다
	shorter := wallet.NewService(f.pool, f.clock.Now, wallet.Policy{FreeFirst: true, FreeTTL: 24 * time.Hour})
	if err := shorter.GrantFree(ctx(t), f.user, 20); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}

	// 하루 뒤에는 새로 준 20 만 사라진다. 먼저 준 10 의 기한은 그대로 1주일이다
	f.clock.Advance(24 * time.Hour)
	f.wantBalance(0, 10)
}
