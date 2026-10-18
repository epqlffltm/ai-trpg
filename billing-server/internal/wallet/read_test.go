// billing-server/internal/wallet/read_test.go

package wallet_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestBalanceOfAUserWithoutAWalletIsZero(t *testing.T) {
	f := setUp(t, freeFirst)

	balance, err := f.service.Balance(ctx(t), f.user)

	if err != nil || balance != (wallet.Balance{}) {
		t.Errorf("잔액 = %+v, %v. 0 이어야 한다", balance, err)
	}
	// 읽는 것만으로 지갑을 만들지 않는다
	if f.count("wallets") != 0 {
		t.Error("잔액을 읽었더니 지갑이 생겼다")
	}
}

func TestBalanceTotalAddsBothKinds(t *testing.T) {
	if got := (wallet.Balance{Paid: 100, Free: 30}).Total(); got != 130 {
		t.Errorf("합 = %d, 기대 = 130", got)
	}
}

// amounts 는 한 쪽의 줄들에서 양만 뽑는다.
func amounts(page wallet.Page) []credit.Amount {
	list := make([]credit.Amount, 0, len(page.Entries))
	for _, entry := range page.Entries {
		list = append(list, entry.Amount)
	}
	return list
}

// sameAmounts 는 두 목록이 같은 순서의 같은 양인지 본다.
func sameAmounts(got []credit.Amount, want ...credit.Amount) bool {
	if len(got) != len(want) {
		return false
	}
	for index := range want {
		if got[index] != want[index] {
			return false
		}
	}
	return true
}

func TestEntriesComeNewestFirstWithEveryField(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)
	f.spend(50)

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 10)

	if err != nil {
		t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	if !sameAmounts(amounts(page), -20, -30, 30, 100) || page.NextBefore != 0 {
		t.Fatalf("양 = %v, 다음 = %d. 기대 = [-20 -30 30 100], 0", amounts(page), page.NextBefore)
	}
	newest, oldest := page.Entries[0], page.Entries[3]
	if newest.Kind != wallet.KindPaid || newest.Reason != wallet.ReasonSpend {
		t.Errorf("가장 최근 줄 = (%s, %s), 기대 = (paid, spend)", newest.Kind, newest.Reason)
	}
	if oldest.Kind != wallet.KindPaid || oldest.Reason != wallet.ReasonDeposit {
		t.Errorf("가장 오래된 줄 = (%s, %s), 기대 = (paid, deposit)", oldest.Kind, oldest.Reason)
	}
	if newest.ID <= oldest.ID || newest.OperationID == uuid.Nil || !newest.CreatedAt.Equal(f.clock.Now()) {
		t.Errorf("줄의 번호, 작업 번호, 시각이 채워지지 않았다: %+v", newest)
	}
	// 한 번에 쓴 두 줄은 작업 번호가 같다
	if page.Entries[0].OperationID != page.Entries[1].OperationID {
		t.Error("한 번에 쓴 두 줄의 작업 번호가 다르다")
	}
}

func TestEntriesArePagedWithoutGapsOrRepeats(t *testing.T) {
	f := setUp(t, freeFirst)
	for amount := credit.Amount(1); amount <= 5; amount++ {
		f.deposit(amount)
	}

	first, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 2)
	if err != nil || !sameAmounts(amounts(first), 5, 4) || first.NextBefore == 0 {
		t.Fatalf("첫 쪽 = %v, 다음 = %d, %v", amounts(first), first.NextBefore, err)
	}
	second, err := f.service.Entries(ctx(t), f.user, first.NextBefore, 2)
	if err != nil || !sameAmounts(amounts(second), 3, 2) || second.NextBefore == 0 {
		t.Fatalf("둘째 쪽 = %v, 다음 = %d, %v", amounts(second), second.NextBefore, err)
	}
	third, err := f.service.Entries(ctx(t), f.user, second.NextBefore, 2)
	if err != nil || !sameAmounts(amounts(third), 1) || third.NextBefore != 0 {
		t.Fatalf("셋째 쪽 = %v, 다음 = %d, %v", amounts(third), third.NextBefore, err)
	}
}

func TestTheLastPageSaysThereIsNoMoreEvenWhenFull(t *testing.T) {
	f := setUp(t, freeFirst)
	for amount := credit.Amount(1); amount <= 4; amount++ {
		f.deposit(amount)
	}

	first, _ := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 2)
	second, err := f.service.Entries(ctx(t), f.user, first.NextBefore, 2)

	// 줄 수가 쪽의 크기로 딱 나누어떨어져도 빈 쪽을 한 번 더 읽게 하지 않는다
	if err != nil || !sameAmounts(amounts(second), 2, 1) || second.NextBefore != 0 {
		t.Errorf("둘째 쪽 = %v, 다음 = %d, %v. 기대 = [2 1], 0", amounts(second), second.NextBefore, err)
	}
}

func TestEntriesOfAUserWithoutAWalletAreEmpty(t *testing.T) {
	f := setUp(t, freeFirst)

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 10)

	// 빈 목록은 nil 이 아니다. JSON 으로 바꾸면 null 이 아니라 [] 가 된다
	if err != nil || page.Entries == nil || len(page.Entries) != 0 || page.NextBefore != 0 {
		t.Errorf("쪽 = %+v, %v. 빈 목록이어야 한다", page, err)
	}
}

func TestEntriesShowOnlyTheUsersOwnLines(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	other := setUp(t, freeFirst)
	other.deposit(7)

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, wallet.MaxPageSize)

	if err != nil || !sameAmounts(amounts(page), 100) {
		t.Errorf("양 = %v, %v. 기대 = [100]", amounts(page), err)
	}
}

func TestEntriesRejectABadRange(t *testing.T) {
	f := setUp(t, freeFirst)
	cases := []struct {
		name   string
		before int64
		limit  int
	}{
		{"한 줄도 읽지 않는다", wallet.FirstPage, 0},
		{"줄 수가 음수다", wallet.FirstPage, -1},
		{"너무 많이 읽는다", wallet.FirstPage, wallet.MaxPageSize + 1},
		{"before 가 0 이다", 0, 10},
		{"before 가 음수다", -5, 10},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := f.service.Entries(ctx(t), f.user, tc.before, tc.limit)
			if !errors.Is(err, wallet.ErrInvalidPage) {
				t.Errorf("오류 = %v. ErrInvalidPage 이어야 한다", err)
			}
		})
	}
}

func TestEntriesAcceptTheLargestPage(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(1)

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, wallet.MaxPageSize)

	if err != nil || len(page.Entries) != 1 {
		t.Errorf("쪽 = %+v, %v", page, err)
	}
}

// wantNextExpiry 는 가장 먼저 사라지는 무료 크레딧이 기대와 같은지 본다. 양이 0 이면 없어야 한다.
func (f fixture) wantNextExpiry(amount credit.Amount, at time.Time) {
	f.t.Helper()
	balance, err := f.service.Balance(ctx(f.t), f.user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	next := balance.NextExpiry
	if amount == 0 {
		if next != nil {
			f.t.Errorf("가장 먼저 사라지는 것 = %+v. 없어야 한다", *next)
		}
		return
	}
	if next == nil || next.Amount != amount || !next.At.Equal(at) {
		f.t.Errorf("가장 먼저 사라지는 것 = %+v, 기대 = %d 이 %v 에", next, amount, at)
	}
}

func TestNoFreeCreditsMeansNothingExpires(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)

	// 산 크레딧은 사라지지 않는다
	f.wantNextExpiry(0, time.Time{})
}

func TestTheEarliestGrantIsTheNextToExpire(t *testing.T) {
	f := setUp(t, freeFirst)
	start := f.clock.Now()
	f.grant(10)
	f.clock.Advance(24 * time.Hour)
	f.grant(20)

	f.wantNextExpiry(10, start.Add(week))
	f.wantBalance(0, 30)
}

func TestGrantsThatExpireAtTheSameMomentAreAddedUp(t *testing.T) {
	f := setUp(t, freeFirst)
	start := f.clock.Now()
	f.grant(10)
	f.grant(5)
	f.clock.Advance(time.Hour)
	f.grant(20)

	f.wantNextExpiry(15, start.Add(week))
}

func TestSpendingTakesFromTheGrantThatExpiresFirst(t *testing.T) {
	f := setUp(t, freeFirst)
	start := f.clock.Now()
	f.grant(10)
	f.clock.Advance(time.Hour)
	f.grant(20)

	f.spend(4)
	f.wantNextExpiry(6, start.Add(week))

	// 첫 묶음을 다 쓰면 다음 묶음이 가장 먼저 사라지는 것이다
	f.spend(6)
	f.wantNextExpiry(20, start.Add(time.Hour+week))
}

func TestAGrantPastItsExpiryIsNotTheNextToExpire(t *testing.T) {
	f := setUp(t, freeFirst)
	start := f.clock.Now()
	f.grant(10)
	f.clock.Advance(time.Hour)
	f.grant(20)

	// 첫 묶음이 사라지는 바로 그 시각이다. 그 시각부터는 쓸 수 없다
	f.clock.Advance(week - time.Hour)
	f.wantNextExpiry(20, start.Add(time.Hour+week))

	f.clock.Advance(time.Hour)
	f.wantNextExpiry(0, time.Time{})
}

func TestAnotherUsersGrantsAreNotTheNextToExpire(t *testing.T) {
	f := setUp(t, freeFirst)
	other := setUpAt(t, f.pool, f.clock, freeFirst)
	other.grant(50)

	f.wantNextExpiry(0, time.Time{})
}
