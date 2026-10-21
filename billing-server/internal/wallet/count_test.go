// billing-server/internal/wallet/count_test.go

// 명단 가운데 지급을 받은 사람과 지갑이 있는 사람을 세는 것(count.go)을 시험한다.
package wallet_test

import (
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// strangers 는 이 서버에 한 번도 오지 않은 사용자 n 명이다.
func strangers(n int) []uuid.UUID {
	users := make([]uuid.UUID, n)
	for i := range users {
		users[i] = uuid.New()
	}
	return users
}

func TestCountGrantedCountsOnlyThatKey(t *testing.T) {
	f := setUp(t, freeFirst)
	other := setUpAt(t, f.pool, f.clock, freeFirst)
	if _, err := f.grantOnce(100, "event-a"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}
	// 다른 사람은 다른 이름으로 받았다. 받은 것을 다 써도 받은 것이다
	if _, err := other.grantOnce(100, "event-b"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}
	other.spend(100)
	users := append([]uuid.UUID{f.user, other.user}, strangers(2)...)

	a, errA := f.service.CountGranted(ctx(t), "event-a", users)
	b, errB := f.service.CountGranted(ctx(t), "event-b", users)

	if errA != nil || errB != nil || a != 1 || b != 1 {
		t.Errorf("event-a = %d, %v. event-b = %d, %v. 둘 다 1 이어야 한다", a, errA, b, errB)
	}
}

func TestCountWalletsCountsThoseWhoseCreditsChanged(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(1)
	users := append([]uuid.UUID{f.user}, strangers(3)...)

	n, err := f.service.CountWallets(ctx(t), users)

	if err != nil || n != 1 {
		t.Errorf("지갑 = %d, %v. 1 이어야 한다", n, err)
	}
}

func TestCountingSplitsALongList(t *testing.T) {
	// 한 쿼리에 싣는 수를 넘는 명단이다. 나눈 경계의 바로 앞(첫 묶음의 끝)과 바로 뒤(둘째 묶음의 처음)에 받은 사람을 둔다
	f := setUp(t, freeFirst)
	last := setUpAt(t, f.pool, f.clock, freeFirst)
	for _, person := range []fixture{f, last} {
		if _, err := person.grantOnce(100, "event-long"); err != nil {
			t.Fatalf("주지 못했다: %v", err)
		}
	}
	users := append(append(strangers(wallet.CountChunk-1), f.user, last.user), strangers(1)...)

	granted, grantedErr := f.service.CountGranted(ctx(t), "event-long", users)
	wallets, walletsErr := f.service.CountWallets(ctx(t), users)

	if grantedErr != nil || walletsErr != nil || granted != 2 || wallets != 2 {
		t.Errorf("받은 사람 = %d, %v. 지갑 = %d, %v. 둘 다 2 여야 한다", granted, grantedErr, wallets, walletsErr)
	}
}

func TestCountingAnEmptyListIsZero(t *testing.T) {
	f := setUp(t, freeFirst)

	n, err := f.service.CountGranted(ctx(t), "event-a", nil)

	if err != nil || n != 0 {
		t.Errorf("받은 사람 = %d, %v", n, err)
	}
}
