// billing-server/internal/hold/lowbalance_test.go

// 홀드가 골드를 뺀 뒤의 잔액을 붙여 둔 것(WithLowBalance)에 알리는지 시험한다(자동 충전, #980).
package hold_test

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// lowBalances 는 알린 것을 적는 가짜다. 받은 트랜잭션에서 그 순간의 골드를 읽는다. fail 이 있으면 그 오류를 돌려준다.
// write 가 true 면 실패하기 전에 줄 하나를 바꾼다(실패하면 그것만 되돌려지는지 본다).
type lowBalances struct {
	paid  []int64
	fail  error
	write bool
}

func (l *lowBalances) NoteBalanceInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (bool, error) {
	var paid int64
	if err := tx.QueryRow(ctx, "SELECT paid_balance FROM wallets WHERE user_id = $1", userID).Scan(&paid); err != nil {
		return false, err
	}
	l.paid = append(l.paid, paid)
	if l.write {
		if _, err := tx.Exec(ctx, "UPDATE wallets SET paid_balance = 0 WHERE user_id = $1", userID); err != nil {
			return false, err
		}
	}
	return false, l.fail
}

func TestTheGoldAfterTheHoldIsNoted(t *testing.T) {
	f := setUp(t)
	f.fund(500, 0)
	noted := &lowBalances{}
	f.service.WithLowBalance(noted)
	reference := newReference()

	f.place(reference)
	f.place(reference) // 같은 이름표로 다시 부른 것은 빼지 않았다

	if len(noted.paid) != 1 || noted.paid[0] != int64(500-price) {
		t.Errorf("알린 골드 = %v. 뺀 뒤의 %d 한 번이어야 한다", noted.paid, 500-price)
	}
}

func TestAFailureToNoteDoesNotStopTheHold(t *testing.T) {
	// 자동 충전을 보지 못해도 서술의 값은 받는다. 알린 쪽이 바꾼 것만 되돌린다
	f := setUp(t)
	f.fund(500, 0)
	f.service.WithLowBalance(&lowBalances{fail: errors.New("DB 가 이상하다"), write: true})
	reference := newReference()

	f.place(reference)

	f.wantStatus(reference, "held")
	f.wantBalance(500-price, 0)
}
