// billing-server/internal/wallet/helpers_test.go

// 지갑 테스트들이 함께 쓰는 도구. 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 돈다.
// 테스트마다 새 사용자 번호를 쓰므로 테이블을 비우지 않아도 서로 섞이지 않는다.
package wallet_test

import (
	"context"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// week 는 테스트가 쓰는 무료 크레딧의 기한이다.
const week = 7 * 24 * time.Hour

// freeFirst 와 paidFirst 는 테스트가 쓰는 두 가지 규칙이다.
var (
	freeFirst = wallet.Policy{FreeFirst: true, FreeTTL: week}
	paidFirst = wallet.Policy{FreeFirst: false, FreeTTL: week}
)

// clock 은 테스트가 마음대로 돌리는 시계다. 여러 흐름이 함께 읽어도 된다.
type clock struct {
	mu  sync.Mutex
	now time.Time
}

// newClock 은 정해 둔 시각에서 시작하는 시계를 만든다. 실제 시각과 상관없이 테스트가 늘 같게 돈다.
func newClock() *clock {
	return &clock{now: time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)}
}

func (c *clock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

// Advance 는 시계를 d 만큼 앞으로 돌린다.
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
	service *wallet.Service
	// user 는 이 테스트만 쓰는 새 사용자다.
	user uuid.UUID
}

// setUp 은 테스트용 스키마에 붙는 서비스와 새 사용자를 만든다.
func setUp(t *testing.T, policy wallet.Policy) fixture {
	t.Helper()
	return setUpAt(t, testenv.Pool(t), newClock(), policy)
}

// setUpSweep 은 정리 작업(ExpireIdle)을 돌리는 테스트의 setUp 이다.
// 시계를 정리 작업의 시대에 두고, 정리 작업의 테스트끼리 한 번에 하나만 돌게 잠근다(testenv.ExclusiveSweep).
// 앞서 돈 테스트가 남긴, 그 시대의 사라질 묶음을 먼저 정리해 둔다.
func setUpSweep(t *testing.T, policy wallet.Policy) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	testenv.ExclusiveSweep(t, pool)
	f := setUpAt(t, pool, &clock{now: testenv.SweepEnd}, policy)
	if _, err := f.service.ExpireIdle(ctx(t), 100_000); err != nil {
		t.Fatalf("남은 묶음을 정리하지 못했다: %v", err)
	}
	f.clock.now = testenv.SweepEra
	return f
}

// setUpAt 은 시계를 넘겨받는 setUp 이다.
func setUpAt(t *testing.T, pool *pgxpool.Pool, clock *clock, policy wallet.Policy) fixture {
	t.Helper()
	return fixture{
		t:       t,
		pool:    pool,
		clock:   clock,
		service: wallet.NewService(pool, clock.Now, policy),
		user:    uuid.New(),
	}
}

// ctx 는 시간 제한이 걸린 context 를 만든다. DB 가 답하지 않거나 잠금이 풀리지 않아도 테스트가 멈추지 않는다.
func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

func (f fixture) deposit(amount credit.Amount) {
	f.t.Helper()
	if err := f.service.Deposit(ctx(f.t), f.user, amount); err != nil {
		f.t.Fatalf("산 크레딧 %d 을 넣지 못했다: %v", amount, err)
	}
}

func (f fixture) grant(amount credit.Amount) {
	f.t.Helper()
	if err := f.service.GrantFree(ctx(f.t), f.user, amount); err != nil {
		f.t.Fatalf("무료 크레딧 %d 을 주지 못했다: %v", amount, err)
	}
}

func (f fixture) spend(amount credit.Amount) {
	f.t.Helper()
	if err := f.service.Spend(ctx(f.t), f.user, amount); err != nil {
		f.t.Fatalf("크레딧 %d 을 쓰지 못했다: %v", amount, err)
	}
}

// wantBalance 는 잔액이 기대와 같은지 보고, 지금의 값과 원장이 맞는지도 함께 본다.
func (f fixture) wantBalance(paid credit.Amount, free credit.Amount) {
	f.t.Helper()
	got, err := f.service.Balance(ctx(f.t), f.user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	// 가장 먼저 사라지는 것(NextExpiry)은 read_test.go 가 본다
	if got.Paid != paid || got.Free != free {
		f.t.Errorf("잔액 = 산 것 %d, 무료 %d. 기대 = 산 것 %d, 무료 %d", got.Paid, got.Free, paid, free)
	}
	f.wantBooksToMatch()
}

// line 은 원장의 한 줄에서 테스트가 견주는 칸들이다.
type line struct {
	Kind   wallet.Kind
	Reason wallet.Reason
	Amount credit.Amount
}

// row 는 원장의 한 줄을 DB 에서 그대로 읽은 것이다.
type row struct {
	line
	OperationID uuid.UUID
	GrantID     *int64
	// LotID 는 산 크레딧의 묶음이다. 산 크레딧의 줄이 아니면 nil 이다.
	LotID     *int64
	CreatedAt time.Time
}

// ledger 는 이 사용자의 원장을 적힌 순서대로 DB 에서 직접 읽는다. 서비스를 거치지 않는다.
func (f fixture) ledger() []row {
	f.t.Helper()
	const query = `SELECT kind, reason, amount, operation_id, grant_id, lot_id, created_at
		FROM ledger_entries WHERE user_id = $1 ORDER BY id`
	rows, err := f.pool.Query(ctx(f.t), query, f.user)
	if err != nil {
		f.t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	defer rows.Close()

	var list []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.Kind, &r.Reason, &r.Amount, &r.OperationID, &r.GrantID, &r.LotID, &r.CreatedAt); err != nil {
			f.t.Fatalf("원장의 줄을 읽지 못했다: %v", err)
		}
		list = append(list, r)
	}
	if err := rows.Err(); err != nil {
		f.t.Fatalf("원장을 읽다가 끊겼다: %v", err)
	}
	return list
}

// wantLedger 는 원장의 줄들이 기대한 순서와 내용인지 본다.
func (f fixture) wantLedger(want ...line) []row {
	f.t.Helper()
	got := f.ledger()
	if len(got) != len(want) {
		f.t.Fatalf("원장이 %d 줄이다. 기대 = %d 줄: %+v", len(got), len(want), lines(got))
	}
	for index := range want {
		if got[index].line != want[index] {
			f.t.Errorf("원장의 %d 번째 줄 = %+v, 기대 = %+v", index+1, got[index].line, want[index])
		}
	}
	return got
}

// lines 는 읽어 온 줄들에서 견주는 칸만 뽑는다. 실패했을 때 읽기 쉽게 찍으려고 쓴다.
func lines(rows []row) []line {
	list := make([]line, 0, len(rows))
	for _, r := range rows {
		list = append(list, r.line)
	}
	return list
}

// wantBooksToMatch 는 지금의 값이 원장과 맞는지 본다.
//   - 산 크레딧의 잔액 = 원장의 paid 줄의 합
//   - 지급 묶음마다, 남은 양 = 그 묶음의 원장 줄의 합
//   - 무료 크레딧의 줄에만 지급 묶음이 적혀 있다
//   - 산 크레딧의 묶음마다, 남은 양 = 그 묶음의 원장 줄의 합. 묶음들의 합 = 산 크레딧의 잔액
func (f fixture) wantBooksToMatch() {
	f.t.Helper()
	const paidQuery = `SELECT
		COALESCE((SELECT paid_balance FROM wallets WHERE user_id = $1), 0)::BIGINT,
		COALESCE((SELECT SUM(amount) FROM ledger_entries WHERE user_id = $1 AND kind = 'paid'), 0)::BIGINT`
	var balance, sum int64
	if err := f.pool.QueryRow(ctx(f.t), paidQuery, f.user).Scan(&balance, &sum); err != nil {
		f.t.Fatalf("산 크레딧을 맞춰 보지 못했다: %v", err)
	}
	if balance != sum {
		f.t.Errorf("산 크레딧의 잔액은 %d 인데 원장의 합은 %d 다", balance, sum)
	}

	const grantQuery = `SELECT COUNT(*) FROM free_grants g
		WHERE g.user_id = $1 AND g.remaining <> COALESCE(
			(SELECT SUM(e.amount) FROM ledger_entries e WHERE e.grant_id = g.id AND e.kind = 'free'), 0)`
	var mismatched int
	if err := f.pool.QueryRow(ctx(f.t), grantQuery, f.user).Scan(&mismatched); err != nil {
		f.t.Fatalf("무료 크레딧을 맞춰 보지 못했다: %v", err)
	}
	if mismatched != 0 {
		f.t.Errorf("남은 양이 원장의 합과 다른 지급 묶음이 %d 개다", mismatched)
	}

	// 산 크레딧의 묶음도 같다. 그리고 묶음들의 남은 양을 더하면 잔액이다
	const lotQuery = `SELECT
		(SELECT COUNT(*) FROM paid_lots l WHERE l.user_id = $1 AND l.remaining <> COALESCE(
			(SELECT SUM(e.amount) FROM ledger_entries e WHERE e.lot_id = l.id), 0)),
		COALESCE((SELECT SUM(remaining) FROM paid_lots WHERE user_id = $1), 0)::BIGINT`
	var lotTotal int64
	if err := f.pool.QueryRow(ctx(f.t), lotQuery, f.user).Scan(&mismatched, &lotTotal); err != nil {
		f.t.Fatalf("산 크레딧의 묶음을 맞춰 보지 못했다: %v", err)
	}
	if mismatched != 0 {
		f.t.Errorf("남은 양이 원장의 합과 다른 산 크레딧 묶음이 %d 개다", mismatched)
	}
	if lotTotal != balance {
		f.t.Errorf("산 크레딧의 잔액은 %d 인데 묶음들의 합은 %d 다", balance, lotTotal)
	}
}

// lot 은 산 크레딧의 묶음 하나를 DB 에서 그대로 읽은 것이다.
type lot struct {
	ID        int64
	OrderID   *uuid.UUID
	Amount    credit.Amount
	Remaining credit.Amount
}

// lots 는 이 사용자의 산 크레딧 묶음을 만든 순서대로 DB 에서 직접 읽는다.
func (f fixture) lots() []lot {
	f.t.Helper()
	rows, err := f.pool.Query(ctx(f.t),
		"SELECT id, order_id, amount, remaining FROM paid_lots WHERE user_id = $1 ORDER BY created_at, id", f.user)
	if err != nil {
		f.t.Fatalf("묶음을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	var list []lot
	for rows.Next() {
		var l lot
		if err := rows.Scan(&l.ID, &l.OrderID, &l.Amount, &l.Remaining); err != nil {
			f.t.Fatalf("묶음을 읽지 못했다: %v", err)
		}
		list = append(list, l)
	}
	if err := rows.Err(); err != nil {
		f.t.Fatalf("묶음을 읽다가 끊겼다: %v", err)
	}
	return list
}

// wantRemaining 은 산 크레딧 묶음들의 남은 양이 만든 순서대로 기대와 같은지 본다.
func (f fixture) wantRemaining(want ...credit.Amount) {
	f.t.Helper()
	got := f.lots()
	remaining := make([]credit.Amount, 0, len(got))
	for _, l := range got {
		remaining = append(remaining, l.Remaining)
	}
	if !slices.Equal(remaining, want) {
		f.t.Errorf("묶음들의 남은 양 = %v, 기대 = %v", remaining, want)
	}
}

// count 는 이 사용자의 줄이 table 에 몇 개인지 센다. table 은 테스트가 적은 이름만 넣는다.
func (f fixture) count(table string) int {
	f.t.Helper()
	var n int
	if err := f.pool.QueryRow(ctx(f.t), "SELECT COUNT(*) FROM "+table+" WHERE user_id = $1", f.user).Scan(&n); err != nil {
		f.t.Fatalf("%s 의 줄을 세지 못했다: %v", table, err)
	}
	return n
}
