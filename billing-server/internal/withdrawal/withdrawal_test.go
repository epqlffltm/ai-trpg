// billing-server/internal/withdrawal/withdrawal_test.go

// 탈퇴를 반영하는 일을 시험한다. 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 진짜 지갑, 홀드, 결제 자격, 알림으로 돈다.
package withdrawal_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/withdrawal"
)

const (
	// source 와 priceCode 는 테스트의 홀드를 건 서버와 가격표의 이름이다. price 는 그 값이다.
	source                  = "trpg-server"
	priceCode               = pricing.NarrationStandard
	price     credit.Amount = 50
)

// fixture 는 테스트 하나가 쓰는 것들이다.
type fixture struct {
	t           *testing.T
	pool        *pgxpool.Pool
	wallet      *wallet.Service
	holds       *hold.Service
	eligibility *eligibility.Service
	notices     *usernotice.Service
	service     *withdrawal.Service
	// user 는 이 테스트만 쓰는 새 사용자다.
	user uuid.UUID
}

// setUp 은 진짜 서비스들로 탈퇴를 반영하는 것을 만든다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	now := func() time.Time { return time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC) }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: 7 * 24 * time.Hour})
	holds, err := hold.NewService(pool, now, wallets, pricing.NewService(pool, now), 24*time.Hour)
	if err != nil {
		t.Fatalf("홀드 서비스를 만들지 못했다: %v", err)
	}
	f := fixture{
		t: t, pool: pool, wallet: wallets, holds: holds,
		eligibility: eligibility.NewService(pool, now), notices: usernotice.NewService(pool, now, nil),
		user: uuid.New(),
	}
	f.service = withdrawal.NewService(pool, wallets, holds, f.eligibility, f.notices)
	return f
}

// ctx 는 시간 제한이 걸린 context 를 만든다.
func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// seed 는 탈퇴하기 전의 사람을 만든다. 골드 300, 실버 50, 걸린 홀드 하나(실버에서 50), 결제 자격, 보내지 않은 알림 하나.
func (f fixture) seed() {
	f.t.Helper()
	if err := f.wallet.Deposit(ctx(f.t), f.user, 300); err != nil {
		f.t.Fatalf("골드를 넣지 못했다: %v", err)
	}
	if err := f.wallet.GrantFree(ctx(f.t), f.user, 50); err != nil {
		f.t.Fatalf("실버를 주지 못했다: %v", err)
	}
	if _, _, err := f.holds.Place(ctx(f.t), source, f.user, "table:"+uuid.NewString()+":round:1", priceCode); err != nil {
		f.t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	update := eligibility.Update{UserID: f.user, Version: 1, GuardianConsent: false}
	if _, err := f.eligibility.Apply(ctx(f.t), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	if err := f.notices.RecordShort(ctx(f.t), f.user, priceCode, price, false); err != nil {
		f.t.Fatalf("알림을 적지 못했다: %v", err)
	}
}

// process 는 탈퇴를 반영한다. 실패하면 테스트를 멈춘다.
func (f fixture) process() withdrawal.Outcome {
	f.t.Helper()
	outcome, err := f.service.Process(ctx(f.t), f.user)
	if err != nil {
		f.t.Fatalf("탈퇴를 반영하지 못했다: %v", err)
	}
	return outcome
}

// scalar 는 이 사용자에 대한 쿼리 하나의 값을 읽는다.
func (f fixture) scalar(query string, target any) {
	f.t.Helper()
	if err := f.pool.QueryRow(ctx(f.t), query, f.user).Scan(target); err != nil {
		f.t.Fatalf("읽지 못했다(%s): %v", query, err)
	}
}

func TestWithdrawalClosesTheWalletAndErasesTheRest(t *testing.T) {
	f := setUp(t)
	f.seed()

	got := f.process()

	want := withdrawal.Outcome{
		ReleasedHolds: 1, Forfeited: wallet.Forfeited{Paid: 300, Free: 50}, ErasedEligibility: true, CancelledNotices: 1,
	}
	if got != want {
		t.Errorf("결과 = %+v, 기대 = %+v", got, want)
	}
	balance, err := f.wallet.Balance(ctx(t), f.user)
	if err != nil || balance.Total() != 0 {
		t.Errorf("잔액 = %+v (%v). 모두 사라져야 한다", balance, err)
	}
	var reason string
	f.scalar("SELECT release_reason FROM holds WHERE user_id = $1", &reason)
	if reason != string(hold.ReleaseWithdrawn) {
		t.Errorf("홀드를 돌려준 이유 = %s", reason)
	}
	if verified, err := f.eligibility.Verified(ctx(t), f.user); err != nil || verified {
		t.Errorf("결제 자격이 남았다(%v, %v)", verified, err)
	}
	var status, lastError string
	f.scalar("SELECT status FROM user_notices WHERE user_id = $1", &status)
	f.scalar("SELECT last_error FROM user_notices WHERE user_id = $1", &lastError)
	if status != "expired" || lastError != "withdrawn" {
		t.Errorf("알림 = (%s, %s). 보내지 않기로 하고 줄은 남긴다", status, lastError)
	}
}

func TestTheLedgerKeepsWhatHappened(t *testing.T) {
	f := setUp(t)
	f.seed()

	f.process()

	var forfeited, total int64
	f.scalar("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE user_id = $1 AND reason = 'forfeit'", &forfeited)
	f.scalar("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE user_id = $1", &total)
	if forfeited != -350 || total != 0 {
		t.Errorf("소멸의 합 = %d, 원장의 합 = %d. -350 과 0 이어야 한다", forfeited, total)
	}
}

func TestWithdrawalTwiceChangesNothing(t *testing.T) {
	f := setUp(t)
	f.seed()
	f.process()
	var before int
	f.scalar("SELECT COUNT(*) FROM ledger_entries WHERE user_id = $1", &before)

	got := f.process()

	var after int
	f.scalar("SELECT COUNT(*) FROM ledger_entries WHERE user_id = $1", &after)
	if got != (withdrawal.Outcome{}) || after != before {
		t.Errorf("두 번째 = %+v, 원장 %d 줄 -> %d 줄. 같은 알림이 다시 와도 결과가 같다", got, before, after)
	}
}

func TestAnUnknownUserIsNothingToDo(t *testing.T) {
	f := setUp(t)

	got := f.process()

	var wallets int
	f.scalar("SELECT COUNT(*) FROM wallets WHERE user_id = $1", &wallets)
	if got != (withdrawal.Outcome{}) || wallets != 0 {
		t.Errorf("결과 = %+v, 지갑 %d 개. 모르는 사용자는 할 일이 없고 지갑을 만들지 않는다", got, wallets)
	}
}

func TestNoHoldCanBePlacedAfterwards(t *testing.T) {
	f := setUp(t)
	f.seed()
	f.process()

	_, _, err := f.holds.Place(ctx(t), source, f.user, "table:"+uuid.NewString()+":round:2", priceCode)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Errorf("탈퇴한 뒤의 홀드 = %v. 남은 크레딧이 없다", err)
	}
}

// failingEligibility 는 결제 자격을 지우다 실패하는 가짜다.
type failingEligibility struct{}

func (failingEligibility) Erase(context.Context, uuid.UUID) (bool, error) {
	return false, errors.New("DB 가 답하지 않는다")
}

func TestAFailureIsFinishedWhenSentAgain(t *testing.T) {
	f := setUp(t)
	f.seed()
	broken := withdrawal.NewService(f.pool, f.wallet, f.holds, failingEligibility{}, f.notices)

	if _, err := broken.Process(ctx(t), f.user); err == nil {
		t.Fatal("결제 자격을 지우지 못했는데 오류가 아니다. 인증 서버가 다시 보내지 않는다")
	}
	got := f.process()

	if got.ErasedEligibility != true || got.CancelledNotices != 1 || got.Forfeited != (wallet.Forfeited{}) {
		t.Errorf("다시 보낸 결과 = %+v. 돈은 이미 정리했고 나머지를 마친다", got)
	}
}

// TestAHoldRacingTheWithdrawalLeavesNothingBehind 는 홀드를 거는 요청과 탈퇴가 함께 와도 틈이 없는지 본다.
// 홀드가 먼저면 탈퇴가 돌려주고 없앤다. 탈퇴가 먼저면 홀드는 크레딧이 모자라 걸리지 않는다.
// 어느 쪽이든 끝나면 걸린 홀드도, 남은 크레딧도 없다.
func TestAHoldRacingTheWithdrawalLeavesNothingBehind(t *testing.T) {
	for round := range 10 {
		f := setUp(t)
		f.seed()
		start := make(chan struct{})
		placed := make(chan error, 1)
		go func() {
			<-start
			_, _, err := f.holds.Place(ctx(t), source, f.user, "table:"+uuid.NewString()+":round:2", priceCode)
			placed <- err
		}()
		close(start)
		f.process()
		if err := <-placed; err != nil && !errors.Is(err, wallet.ErrInsufficient) {
			t.Fatalf("%d 번째: 홀드 = %v", round, err)
		}

		var held int
		f.scalar("SELECT COUNT(*) FROM holds WHERE user_id = $1 AND status = 'held'", &held)
		balance, err := f.wallet.Balance(ctx(t), f.user)
		if err != nil || held != 0 || balance.Total() != 0 {
			t.Fatalf("%d 번째: 걸린 홀드 %d, 잔액 %+v (%v). 남은 것이 없어야 한다", round, held, balance, err)
		}
	}
}
