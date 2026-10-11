// billing-server/internal/wallet/schema_test.go

// DB 가 스스로 막는 것들을 확인한다. 서비스를 거치지 않고 SQL 을 직접 보낸다.
// 코드에 실수가 있어도 잔액이 음수가 되거나 지난 기록이 바뀌는 일은 DB 에서 멈춘다.
package wallet_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// PostgreSQL 이 돌려주는 오류의 종류(SQLSTATE).
const (
	checkViolation      = "23514"
	foreignKeyViolation = "23503"
	restrictViolation   = "23001"
)

// wantRefused 는 SQL 을 보내고, DB 가 기대한 종류의 오류로 거절하는지 본다.
func (f fixture) wantRefused(code string, sql string, args ...any) {
	f.t.Helper()
	_, err := f.pool.Exec(ctx(f.t), sql, args...)
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) || pgErr.Code != code {
		f.t.Errorf("오류 = %v. SQLSTATE %s 로 거절해야 한다", err, code)
	}
}

func TestTheDatabaseKeepsBalancesFromGoingNegative(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(10)
	f.grant(10)

	f.wantRefused(checkViolation, "UPDATE wallets SET paid_balance = paid_balance - 11 WHERE user_id = $1", f.user)
	f.wantRefused(checkViolation, "UPDATE free_grants SET remaining = remaining - 11 WHERE user_id = $1", f.user)
	// 준 것보다 많이 남을 수도 없다
	f.wantRefused(checkViolation, "UPDATE free_grants SET remaining = remaining + 1 WHERE user_id = $1", f.user)

	f.wantBalance(10, 10)
}

func TestTheDatabaseRefusesGrantsThatAreAlreadyExpired(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(1)

	const insert = `INSERT INTO free_grants (user_id, amount, remaining, expires_at, created_at)
		VALUES ($1, $2, $2, $3, $4)`
	now := f.clock.Now()
	f.wantRefused(checkViolation, insert, f.user, 10, now, now)
	f.wantRefused(checkViolation, insert, f.user, 0, now.Add(week), now)
	f.wantRefused(checkViolation, insert, f.user, -5, now.Add(week), now)
}

func TestTheLedgerOnlyGrows(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)

	f.wantRefused(restrictViolation, "UPDATE ledger_entries SET amount = 1000000 WHERE user_id = $1", f.user)
	f.wantRefused(restrictViolation, "DELETE FROM ledger_entries WHERE user_id = $1", f.user)
	f.wantRefused(restrictViolation, "TRUNCATE ledger_entries")

	f.wantLedger(line{"paid", "deposit", 100})
}

func TestTheLedgerRefusesLinesThatDoNotMakeSense(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)
	grantID := *f.ledger()[0].GrantID

	const insert = `INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, grant_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)`
	cases := []struct {
		name    string
		kind    string
		reason  string
		amount  int64
		grantID *int64
	}{
		{"모르는 종류", "bonus", "deposit", 10, nil},
		{"모르는 이유", "paid", "gift", 10, nil},
		{"양이 0", "paid", "deposit", 0, nil},
		{"충전인데 줄었다", "paid", "deposit", -10, nil},
		{"썼는데 늘었다", "paid", "spend", 10, nil},
		{"사라졌는데 늘었다", "free", "expire", 10, &grantID},
		{"산 크레딧이 지급되었다", "paid", "grant", 10, nil},
		{"산 크레딧이 사라졌다", "paid", "expire", -10, nil},
		{"무료 크레딧이 충전되었다", "free", "deposit", 10, &grantID},
		{"무료 크레딧인데 지급 묶음이 없다", "free", "spend", -10, nil},
		{"산 크레딧인데 지급 묶음이 있다", "paid", "spend", -10, &grantID},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f.wantRefused(checkViolation, insert, f.user, uuid.New(), tc.kind, tc.reason, tc.amount, tc.grantID, f.clock.Now())
		})
	}
	// 거절된 줄은 하나도 남지 않았다
	f.wantLedger(line{"free", "grant", 10})
}

func TestLinesNeedAWallet(t *testing.T) {
	f := setUp(t, freeFirst)

	// 지갑이 없는 사용자의 줄은 적을 수 없다. 지갑의 줄이 그 사용자의 잠금 지점이라 반드시 있어야 한다
	f.wantRefused(foreignKeyViolation,
		`INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, created_at)
		VALUES ($1, $2, 'paid', 'deposit', 10, $3)`, f.user, uuid.New(), f.clock.Now())
	f.wantRefused(foreignKeyViolation,
		`INSERT INTO free_grants (user_id, amount, remaining, expires_at, created_at)
		VALUES ($1, 10, 10, $2, $3)`, f.user, f.clock.Now().Add(week), f.clock.Now())
}
