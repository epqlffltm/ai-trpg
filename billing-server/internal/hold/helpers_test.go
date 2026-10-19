// billing-server/internal/hold/helpers_test.go

// 홀드 테스트들이 함께 쓰는 도구. 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 돈다. 지갑은 진짜를 쓴다.
package hold_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	// source 는 테스트가 쓰는 "부르는 서버"의 이름이다.
	source = "trpg-server"
	// priceCode 와 price 는 테스트가 쓰는 가격표의 줄이다.
	priceCode               = pricing.NarrationStandard
	price     credit.Amount = 50
	week                    = 7 * 24 * time.Hour
	// ttl 은 테스트의 홀드가 만료될 때까지의 시간이다.
	ttl = 24 * time.Hour
)

// clock 은 테스트가 마음대로 돌리는 시계다.
type clock struct {
	mu  sync.Mutex
	now time.Time
}

func (c *clock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *clock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// fixture 는 테스트 하나가 쓰는 것들이다.
type fixture struct {
	t       *testing.T
	pool    *pgxpool.Pool
	clock   *clock
	wallet  *wallet.Service
	service *hold.Service
	// user 는 이 테스트만 쓰는 새 사용자다.
	user uuid.UUID
}

// setUp 은 테스트용 스키마에 붙는 홀드 서비스와 새 사용자를 만든다.
func setUp(t *testing.T) fixture {
	t.Helper()
	return setUpAt(t, testenv.Pool(t), time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC))
}

// setUpSweep 은 정리 작업(ExpireDue)을 돌리는 테스트의 setUp 이다.
// 시계를 정리 작업의 시대에 두고, 정리 작업의 테스트끼리 한 번에 하나만 돌게 잠근다(testenv.ExclusiveSweep).
func setUpSweep(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	testenv.ExclusiveSweep(t, pool)
	f := setUpAt(t, pool, testenv.SweepEnd)
	// 앞서 돈 정리 작업의 테스트가 남긴, 그 시대의 held 홀드를 치운다. 그다음 시계를 시대의 처음으로 돌린다
	if _, err := f.service.ExpireDue(ctx(t), 100_000); err != nil {
		t.Fatalf("남은 홀드를 치우지 못했다: %v", err)
	}
	f.clock.now = testenv.SweepEra
	return f
}

// setUpAt 은 시계를 start 에 둔 setUp 이다.
func setUpAt(t *testing.T, pool *pgxpool.Pool, start time.Time) fixture {
	t.Helper()
	clock := &clock{now: start}
	wallets := wallet.NewService(pool, clock.Now, wallet.Policy{FreeFirst: true, FreeTTL: week})
	return fixture{
		t:       t,
		pool:    pool,
		clock:   clock,
		wallet:  wallets,
		service: newService(t, pool, clock.Now, wallets),
		user:    uuid.New(),
	}
}

// newService 는 홀드 서비스를 만든다. 만들지 못하면 테스트를 멈춘다.
func newService(t *testing.T, pool *pgxpool.Pool, now func() time.Time, wallets hold.Wallet) *hold.Service {
	t.Helper()
	service, err := hold.NewService(pool, now, wallets, pricing.NewService(pool, now), ttl)
	if err != nil {
		t.Fatalf("홀드 서비스를 만들지 못했다: %v", err)
	}
	return service
}

// ctx 는 시간 제한이 걸린 context 를 만든다.
func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// newReference 는 테스트마다 다른 이름표를 만든다. 게임 서버가 지을 법한 모양이다.
func newReference() string {
	return "table:" + uuid.NewString() + ":round:3"
}

// fund 는 이 사용자에게 산 크레딧과 무료 크레딧을 넣는다. 0 이면 넣지 않는다.
func (f fixture) fund(paid credit.Amount, free credit.Amount) {
	f.t.Helper()
	if paid > 0 {
		if err := f.wallet.Deposit(ctx(f.t), f.user, paid); err != nil {
			f.t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
		}
	}
	if free > 0 {
		if err := f.wallet.GrantFree(ctx(f.t), f.user, free); err != nil {
			f.t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
		}
	}
}

// place 는 이 사용자의 홀드를 건다.
func (f fixture) place(reference string) hold.Hold {
	f.t.Helper()
	placed, _, err := f.service.Place(ctx(f.t), source, f.user, reference, priceCode)
	if err != nil {
		f.t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	return placed
}

// wantBalance 는 이 사용자의 잔액이 기대와 같은지 본다.
func (f fixture) wantBalance(paid credit.Amount, free credit.Amount) {
	f.t.Helper()
	got, err := f.wallet.Balance(ctx(f.t), f.user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	if got.Paid != paid || got.Free != free {
		f.t.Errorf("잔액 = 산 것 %d, 무료 %d. 기대 = 산 것 %d, 무료 %d", got.Paid, got.Free, paid, free)
	}
}

// wantStatus 는 DB 에 적힌 홀드의 상태가 기대와 같은지 본다. 서비스를 거치지 않고 직접 읽는다.
func (f fixture) wantStatus(reference string, want hold.Status) {
	f.t.Helper()
	var status hold.Status
	var settled *time.Time
	const query = "SELECT status, settled_at FROM holds WHERE source = $1 AND reference = $2"
	if err := f.pool.QueryRow(ctx(f.t), query, source, reference).Scan(&status, &settled); err != nil {
		f.t.Fatalf("홀드를 읽지 못했다: %v", err)
	}
	if status != want || (want == hold.StatusHeld) != (settled == nil) {
		f.t.Errorf("홀드 = (%s, 끝난 시각 %v), 기대 = %s", status, settled, want)
	}
}

// count 는 이 사용자의 줄이 table 에 몇 개인지 센다. where 는 더할 조건이다(없으면 빈 글자).
func (f fixture) count(table string, where string) int {
	f.t.Helper()
	query := "SELECT COUNT(*) FROM " + table + " WHERE user_id = $1"
	if where != "" {
		query += " AND " + where
	}
	var n int
	if err := f.pool.QueryRow(ctx(f.t), query, f.user).Scan(&n); err != nil {
		f.t.Fatalf("%s 의 줄을 세지 못했다: %v", table, err)
	}
	return n
}

// together 는 run 을 n 개의 흐름에서 한꺼번에 부르고, 돌려받은 오류들을 모은다.
func together(n int, run func(index int) error) []error {
	errs := make([]error, n)
	start := make(chan struct{})
	var done sync.WaitGroup
	for index := range n {
		done.Add(1)
		go func() {
			defer done.Done()
			<-start
			errs[index] = run(index)
		}()
	}
	close(start)
	done.Wait()
	return errs
}
