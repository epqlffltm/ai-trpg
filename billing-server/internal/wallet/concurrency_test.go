// billing-server/internal/wallet/concurrency_test.go

// 같은 사용자의 요청이 한꺼번에 들어와도 잔액이 틀어지지 않는지 본다.
// 요청마다 DB 연결을 따로 쓰므로 실제로 겹쳐서 돈다.
package wallet_test

import (
	"errors"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// together 는 run 을 n 개의 흐름에서 한꺼번에 부르고, 돌려받은 오류들을 모은다.
// 모두가 출발선에 선 뒤에 함께 출발한다. 먼저 뜬 흐름이 먼저 끝나 버리면 겹치지 않는다.
func together(n int, run func() error) []error {
	errs := make([]error, n)
	start := make(chan struct{})
	var done sync.WaitGroup
	for index := range n {
		done.Add(1)
		go func() {
			defer done.Done()
			<-start
			errs[index] = run()
		}()
	}
	close(start)
	done.Wait()
	return errs
}

// tally 는 오류들을 성공한 수와 모자라서 거절된 수로 센다. 그 밖의 오류가 있으면 테스트를 실패시킨다.
func tally(t *testing.T, errs []error) (succeeded int, refused int) {
	t.Helper()
	for _, err := range errs {
		switch {
		case err == nil:
			succeeded++
		case errors.Is(err, wallet.ErrInsufficient):
			refused++
		default:
			t.Errorf("뜻밖의 오류: %v", err)
		}
	}
	return succeeded, refused
}

func TestConcurrentSpendsNeverTakeMoreThanHeld(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)

	// 10 씩 스무 번을 한꺼번에 쓴다. 가진 것은 열 번어치다
	errs := together(20, func() error { return f.service.Spend(ctx(t), f.user, 10) })

	succeeded, refused := tally(t, errs)
	if succeeded != 10 || refused != 10 {
		t.Errorf("성공 %d, 거절 %d. 기대 = 성공 10, 거절 10", succeeded, refused)
	}
	f.wantBalance(0, 0)
}

func TestConcurrentSpendsAcrossBothKinds(t *testing.T) {
	for name, policy := range map[string]wallet.Policy{"무료부터": freeFirst, "산 것부터": paidFirst} {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, policy)
			f.deposit(45)
			f.grant(25)
			f.grant(30)

			// 가진 것은 100 이다. 7 씩 서른 번을 쓰면 열네 번만 되고 2 가 남는다
			errs := together(30, func() error { return f.service.Spend(ctx(t), f.user, 7) })

			succeeded, refused := tally(t, errs)
			if succeeded != 14 || refused != 16 {
				t.Errorf("성공 %d, 거절 %d. 기대 = 성공 14, 거절 16", succeeded, refused)
			}
			balance, err := f.service.Balance(ctx(t), f.user)
			if err != nil || balance.Total() != 2 {
				t.Errorf("남은 것 = %+v, %v. 합이 2 여야 한다", balance, err)
			}
			f.wantBooksToMatch()
		})
	}
}

func TestConcurrentFirstDepositsCreateOneWallet(t *testing.T) {
	f := setUp(t, freeFirst)

	// 지갑이 없는 사용자에게 한꺼번에 넣는다. 지갑을 서로 만들려다 부딪치지 않는다
	errs := together(20, func() error { return f.service.Deposit(ctx(t), f.user, 5) })

	if succeeded, _ := tally(t, errs); succeeded != 20 {
		t.Errorf("성공 %d. 모두 성공해야 한다", succeeded)
	}
	if f.count("wallets") != 1 {
		t.Errorf("지갑이 %d 개다", f.count("wallets"))
	}
	f.wantBalance(100, 0)
}

func TestConcurrentDepositsGrantsAndSpendsKeepTheBooksStraight(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(50)

	// 넣기, 주기, 쓰기를 열 번씩 섞어서 한꺼번에 돌린다
	var turn, spends atomic.Int64
	errs := together(30, func() error {
		switch turn.Add(1) % 3 {
		case 0:
			return f.service.Deposit(ctx(t), f.user, 3)
		case 1:
			return f.service.GrantFree(ctx(t), f.user, 2)
		default:
			err := f.service.Spend(ctx(t), f.user, 4)
			if err == nil {
				spends.Add(1)
			}
			return err
		}
	})
	tally(t, errs)

	// 어떤 순서로 끝나든, 50 + 넣은 30 + 준 20 에서 성공한 만큼 4 씩 빠진 것이 남는다
	want := credit.Amount(100 - 4*spends.Load())
	balance, err := f.service.Balance(ctx(t), f.user)
	if err != nil || balance.Total() != want {
		t.Errorf("남은 것 = %+v, %v. 합이 %d 여야 한다", balance, err, want)
	}
	f.wantBooksToMatch()
}
