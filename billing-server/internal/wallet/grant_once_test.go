// billing-server/internal/wallet/grant_once_test.go

package wallet_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// grantOnce 는 이 사용자에게 한 번만 주는 무료 크레딧을 준다.
func (f fixture) grantOnce(amount credit.Amount, key string) (wallet.Grant, error) {
	f.t.Helper()
	return f.service.GrantFreeOnce(ctx(f.t), f.user, amount, key)
}

func TestGrantFreeOnceGivesCreditsThatExpire(t *testing.T) {
	f := setUp(t, freeFirst)

	grant, err := f.grantOnce(1000, "welcome")

	if err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}
	// 얼마를 줬고 언제 사라지는지 돌려준다
	if grant.Amount != 1000 || !grant.ExpiresAt.Equal(f.clock.Now().Add(week)) {
		t.Errorf("준 것 = %+v, 기대 = 1000, %v", grant, f.clock.Now().Add(week))
	}
	f.wantBalance(0, 1000)
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 1000})

	// 다른 무료 크레딧과 똑같이 기한이 지나면 사라진다
	f.clock.Advance(week)
	f.wantBalance(0, 0)
}

func TestGrantFreeOnceRefusesTheSecondTime(t *testing.T) {
	f := setUp(t, freeFirst)
	if _, err := f.grantOnce(1000, "welcome"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}

	again, err := f.grantOnce(1000, "welcome")

	if !errors.Is(err, wallet.ErrAlreadyGranted) || again != (wallet.Grant{}) {
		t.Errorf("둘째 = %+v, %v. ErrAlreadyGranted 이어야 한다", again, err)
	}
	// 한 줄도 더 생기지 않았다
	f.wantBalance(0, 1000)
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 1000})
}

func TestGrantFreeOnceStaysRefusedAfterTheCreditsAreGone(t *testing.T) {
	cases := map[string]func(f fixture){
		"다 썼다":       func(f fixture) { f.spend(1000) },
		"기한이 지났다":    func(f fixture) { f.clock.Advance(week) },
		"사라진 것이 적혔다": func(f fixture) { f.clock.Advance(week); f.deposit(1); f.spend(1) },
	}
	for name, useUp := range cases {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, freeFirst)
			if _, err := f.grantOnce(1000, "welcome"); err != nil {
				t.Fatalf("주지 못했다: %v", err)
			}
			useUp(f)

			_, err := f.grantOnce(1000, "welcome")

			// 받은 것이 남아 있지 않아도 받은 적이 있으면 다시 받지 못한다
			if !errors.Is(err, wallet.ErrAlreadyGranted) {
				t.Errorf("오류 = %v. ErrAlreadyGranted 이어야 한다", err)
			}
			f.wantBalance(0, 0)
		})
	}
}

func TestGrantFreeOnceIsPerKeyAndPerUser(t *testing.T) {
	f := setUp(t, freeFirst)
	other := setUp(t, freeFirst)

	// 이름이 다르면 다른 지급이다. 사용자가 다르면 같은 이름도 따로 받는다
	if _, err := f.grantOnce(1000, "welcome"); err != nil {
		t.Errorf("welcome: %v", err)
	}
	if _, err := f.grantOnce(300, "launch-event"); err != nil {
		t.Errorf("launch-event: %v", err)
	}
	if _, err := other.grantOnce(1000, "welcome"); err != nil {
		t.Errorf("다른 사용자의 welcome: %v", err)
	}

	f.wantBalance(0, 1300)
	other.wantBalance(0, 1000)
}

func TestPlainGrantsAreNotLimited(t *testing.T) {
	// 이름이 없는 지급은 몇 번이고 줄 수 있다. 한 번만 받은 것과도 상관없다
	f := setUp(t, freeFirst)
	if _, err := f.grantOnce(1000, "welcome"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}

	f.grant(10)
	f.grant(10)

	f.wantBalance(0, 1020)
}

func TestGrantFreeOnceRejectsBadInput(t *testing.T) {
	f := setUp(t, freeFirst)
	keys := map[string]string{
		"비었다":   "",
		"대문자":   "Welcome",
		"빈칸":    "welcome bonus",
		"한글":    "환영",
		"너무 길다": strings.Repeat("k", 65),
		"따옴표":   `welcome"`,
	}
	for name, key := range keys {
		t.Run(name, func(t *testing.T) {
			if _, err := f.grantOnce(1000, key); !errors.Is(err, wallet.ErrInvalidGrantKey) {
				t.Errorf("오류 = %v. ErrInvalidGrantKey 이어야 한다", err)
			}
		})
	}
	for _, amount := range []credit.Amount{0, -1, wallet.MaxAmount + 1} {
		if _, err := f.grantOnce(amount, "welcome"); !errors.Is(err, wallet.ErrInvalidAmount) {
			t.Errorf("양 %d: 오류 = %v. ErrInvalidAmount 이어야 한다", amount, err)
		}
	}
	// 거절된 요청은 지갑조차 만들지 않는다. 받은 것으로 치지도 않는다
	if f.count("wallets") != 0 {
		t.Error("거절했는데 지갑이 생겼다")
	}
	if _, err := f.grantOnce(1000, "welcome"); err != nil {
		t.Errorf("거절된 뒤의 첫 지급을 못 받았다: %v", err)
	}
}

func TestGrantFreeOnceAcceptsTheLongestKey(t *testing.T) {
	f := setUp(t, freeFirst)

	if _, err := f.grantOnce(1, strings.Repeat("k", 64)); err != nil {
		t.Errorf("64자의 이름을 받지 않았다: %v", err)
	}
}

func TestConcurrentGrantFreeOnceGivesOnce(t *testing.T) {
	f := setUp(t, freeFirst)

	// 받기 단추를 스무 번 한꺼번에 누른다
	errs := together(20, func() error {
		_, err := f.grantOnce(1000, "welcome")
		return err
	})

	given, refused := 0, 0
	for _, err := range errs {
		switch {
		case err == nil:
			given++
		case errors.Is(err, wallet.ErrAlreadyGranted):
			refused++
		default:
			t.Errorf("뜻밖의 오류: %v", err)
		}
	}
	if given != 1 || refused != 19 {
		t.Errorf("받은 것 %d 번, 거절 %d 번. 기대 = 1 번, 19 번", given, refused)
	}
	f.wantBalance(0, 1000)
}

func TestTheDatabaseRefusesTheSameGrantKeyTwice(t *testing.T) {
	f := setUp(t, freeFirst)
	if _, err := f.grantOnce(1000, "welcome"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}

	const insert = `INSERT INTO free_grants (user_id, amount, remaining, expires_at, grant_key, created_at)
		VALUES ($1, 10, 10, $2, $3, $4)`
	now := f.clock.Now()
	// 코드가 확인을 빠뜨려도 같은 이름의 둘째 줄은 DB 가 거절한다
	f.wantRefused("23505", insert, f.user, now.Add(week), "welcome", now)
	// 빈 이름은 이름이 없는 것(NULL)과 섞이지 않게 거절한다
	f.wantRefused(checkViolation, insert, f.user, now.Add(week), "", now)

	f.wantBalance(0, 1000)
}

// grantOnceInTx 는 트랜잭션을 열어 GrantFreeOnceInTx 를 부른다. commit 이 false 면 되돌린다.
func (f fixture) grantOnceInTx(amount credit.Amount, key string, commit bool) (wallet.Grant, error) {
	f.t.Helper()
	tx, err := f.pool.Begin(ctx(f.t))
	if err != nil {
		f.t.Fatalf("트랜잭션을 열지 못했다: %v", err)
	}
	grant, grantErr := f.service.GrantFreeOnceInTx(ctx(f.t), tx, f.user, amount, key)
	if grantErr != nil || !commit {
		if err := tx.Rollback(ctx(f.t)); err != nil {
			f.t.Fatalf("되돌리지 못했다: %v", err)
		}
		return grant, grantErr
	}
	if err := tx.Commit(ctx(f.t)); err != nil {
		f.t.Fatalf("적지 못했다: %v", err)
	}
	return grant, nil
}

func TestGrantFreeOnceInTxGivesWhenTheCallerCommits(t *testing.T) {
	f := setUp(t, freeFirst)

	grant, err := f.grantOnceInTx(140, "attendance-20261018", true)

	if err != nil || grant.Amount != 140 || !grant.ExpiresAt.Equal(f.clock.Now().Add(week)) {
		t.Fatalf("준 것 = %+v, %v", grant, err)
	}
	f.wantBalance(0, 140)
	f.wantLedger(line{wallet.KindFree, wallet.ReasonGrant, 140})
}

func TestGrantFreeOnceInTxIsUndoneWhenTheCallerRollsBack(t *testing.T) {
	f := setUp(t, freeFirst)

	if _, err := f.grantOnceInTx(140, "attendance-20261018", false); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}

	// 지급도 원장도 남지 않는다. 같은 이름으로 다시 받을 수 있다
	f.wantBalance(0, 0)
	f.wantLedger()
	if _, err := f.grantOnce(140, "attendance-20261018"); err != nil {
		t.Fatalf("되돌린 뒤에는 다시 받아야 한다: %v", err)
	}
}

func TestGrantFreeOnceInTxRefusesAKeyAlreadyGiven(t *testing.T) {
	f := setUp(t, freeFirst)
	if _, err := f.grantOnce(140, "attendance-20261018"); err != nil {
		t.Fatalf("주지 못했다: %v", err)
	}

	_, err := f.grantOnceInTx(140, "attendance-20261018", true)

	if !errors.Is(err, wallet.ErrAlreadyGranted) {
		t.Fatalf("ErrAlreadyGranted 이어야 하는데 %v 다", err)
	}
	f.wantBalance(0, 140)
}

func TestGrantFreeOnceInTxChecksTheAmountAndKey(t *testing.T) {
	f := setUp(t, freeFirst)
	if _, err := f.grantOnceInTx(0, "attendance-20261018", true); !errors.Is(err, wallet.ErrInvalidAmount) {
		t.Errorf("0 은 ErrInvalidAmount 이어야 하는데 %v 다", err)
	}
	if _, err := f.grantOnceInTx(1, "Bad Key", true); !errors.Is(err, wallet.ErrInvalidGrantKey) {
		t.Errorf("틀린 이름은 ErrInvalidGrantKey 이어야 하는데 %v 다", err)
	}
	f.wantBalance(0, 0)
}
