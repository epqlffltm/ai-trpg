// billing-server/internal/wallet/sweep_test.go

// 변경이 없는 사용자의 사라진 무료 크레딧을 원장에 적는 정리 작업(ExpireIdle)을 시험한다.
package wallet_test

import (
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// expireIdle 은 정리 작업을 한 번 돌리고 정리한 사용자의 수를 돌려준다.
func (f fixture) expireIdle() int {
	f.t.Helper()
	done, err := f.service.ExpireIdle(ctx(f.t), 1000)
	if err != nil {
		f.t.Fatalf("정리 작업이 실패했다: %v", err)
	}
	return done
}

func TestExpireIdleRecordsWhatExpiredForAnIdleUser(t *testing.T) {
	// 무료 크레딧을 받고 아무것도 하지 않은 사용자다. 원장에는 사라진 줄이 끝내 적히지 않는다. 정리 작업이 적는다
	f := setUpSweep(t, freeFirst)
	f.grant(30)
	f.spend(10)
	f.clock.Advance(week)

	if done := f.expireIdle(); done < 1 {
		t.Errorf("정리한 사용자가 %d 명이다", done)
	}

	f.wantBalance(0, 0)
	f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonSpend, -10},
		line{wallet.KindFree, wallet.ReasonExpire, -20},
	)
	// 다시 돌려도 또 적지 않는다
	f.expireIdle()
	if got := len(f.ledger()); got != 3 {
		t.Errorf("원장이 %d 줄이다. 기대 = 3 줄", got)
	}
}

func TestExpireIdleLeavesGrantsThatHaveNotExpired(t *testing.T) {
	f := setUpSweep(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week - time.Second)

	f.expireIdle()

	f.wantBalance(0, 30)
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 30})
}

func TestExpireIdleTouchesOnlyFreeCredits(t *testing.T) {
	// 산 크레딧은 사라지지 않는다. 다 쓴 무료 크레딧도 적을 것이 없다
	f := setUpSweep(t, freeFirst)
	f.deposit(100)
	f.grant(20)
	f.spend(20)
	f.clock.Advance(2 * week)

	f.expireIdle()

	f.wantBalance(100, 0)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 20},
		line{wallet.KindFree, wallet.ReasonSpend, -20},
	)
}

func TestExpireIdleRespectsTheLimit(t *testing.T) {
	f := setUpSweep(t, freeFirst)
	users := []uuid.UUID{uuid.New(), uuid.New(), uuid.New()}
	for _, user := range users {
		other := f
		other.user = user
		other.grant(10)
	}
	f.clock.Advance(week)

	done, err := f.service.ExpireIdle(ctx(t), 2)

	if err != nil || done != 2 {
		t.Fatalf("정리한 사용자 = %d, %v. 기대 = 2", done, err)
	}
	expired := 0
	for _, user := range users {
		other := f
		other.user = user
		if len(other.ledger()) == 2 {
			expired++
		}
	}
	if expired != 2 {
		t.Errorf("사라진 줄이 적힌 사용자가 %d 명이다. 기대 = 2 명", expired)
	}
	// 남은 한 명은 다음 번에 적힌다
	if done := f.expireIdle(); done != 1 {
		t.Errorf("다음 번에 정리한 사용자 = %d, 기대 = 1", done)
	}
}

func TestConcurrentSweepsRecordAnExpiryOnce(t *testing.T) {
	// 정리 작업 둘과 그 사용자의 충전이 한꺼번에 온다. 지갑을 잠그고 하므로 사라진 줄은 한 번만 적힌다
	f := setUpSweep(t, freeFirst)
	f.grant(30)
	f.clock.Advance(week)

	var started atomic.Int32
	errs := together(5, func() error {
		if started.Add(1) == 1 {
			return f.service.Deposit(ctx(t), f.user, 5)
		}
		_, err := f.service.ExpireIdle(ctx(t), 1000)
		return err
	})

	for index, err := range errs {
		if err != nil {
			t.Errorf("%d 번째: %v", index, err)
		}
	}
	f.wantBalance(5, 0)
	expires := 0
	for _, row := range f.ledger() {
		if row.Reason == wallet.ReasonExpire {
			expires++
		}
	}
	if expires != 1 {
		t.Errorf("사라진 줄이 %d 개다. 기대 = 1 개", expires)
	}
}
