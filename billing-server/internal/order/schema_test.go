// billing-server/internal/order/schema_test.go

// DB 가 스스로 막는 것들을 확인한다. 서비스를 거치지 않고 SQL 을 직접 보낸다.
package order_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// PostgreSQL 이 돌려주는 오류의 종류(SQLSTATE).
const (
	checkViolation      = "23514"
	uniqueViolation     = "23505"
	foreignKeyViolation = "23503"
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

func TestTheDatabaseKeepsOrderStatusAndColumnsInStep(t *testing.T) {
	f := setUp(t, approving())
	pending := f.create()
	paid := f.create()
	f.confirm(paid.ID, newPaymentKey())

	cases := map[string]string{
		// 결제 번호를 함께 적는다. 다른 제약에는 걸리지 않고 "모르는 상태"라는 까닭으로만 거절되어야 한다
		"모르는 상태":               "UPDATE orders SET status = 'refunded', payment_key = 'pay_w' WHERE id = $1",
		"결제 번호가 있는 pending":    "UPDATE orders SET payment_key = 'pay_x' WHERE id = $1",
		"결제 번호가 없는 confirming": "UPDATE orders SET status = 'confirming' WHERE id = $1",
		"치른 시각이 없는 paid":       "UPDATE orders SET status = 'paid', payment_key = 'pay_y' WHERE id = $1",
		"치른 시각이 있는 pending":    "UPDATE orders SET paid_at = created_at WHERE id = $1",
		"이유가 없는 failed":        "UPDATE orders SET status = 'failed', payment_key = 'pay_z' WHERE id = $1",
		"이유가 있는 pending":       "UPDATE orders SET failure_code = 'card_declined' WHERE id = $1",
		"값이 0":                 "UPDATE orders SET price = 0 WHERE id = $1",
		"크레딧이 0":               "UPDATE orders SET credits = 0 WHERE id = $1",
	}
	for name, sql := range cases {
		t.Run(name, func(t *testing.T) {
			f.wantRefused(checkViolation, sql, pending.ID)
		})
	}
	// 치른 주문의 결제 번호를 다른 주문에 또 적을 수 없다
	f.wantRefused(uniqueViolation,
		"UPDATE orders SET status = 'confirming', payment_key = (SELECT payment_key FROM orders WHERE id = $2) WHERE id = $1",
		pending.ID, paid.ID)
}

func TestTheLedgerTakesOneDepositPerOrder(t *testing.T) {
	f := setUp(t, approving())
	paid := f.create()
	f.confirm(paid.ID, newPaymentKey())

	const insert = `INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, order_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)`
	// 같은 주문으로 한 줄을 더 넣을 수 없다. 코드가 같은 주문을 두 번 처리해도 여기서 멈춘다
	f.wantRefused(uniqueViolation, insert, f.user, uuid.New(), "paid", "deposit", 1000, paid.ID, startedAt)
	// 없는 주문을 가리킬 수 없다
	f.wantRefused(foreignKeyViolation, insert, f.user, uuid.New(), "paid", "deposit", 1000, uuid.New(), startedAt)
	// 주문은 산 크레딧이 들어온 줄에만 적힌다
	other := f.create()
	f.wantRefused(checkViolation, insert, f.user, uuid.New(), "paid", "spend", -10, other.ID, startedAt)

	f.wantPaidCredits(credits, 1)
}
