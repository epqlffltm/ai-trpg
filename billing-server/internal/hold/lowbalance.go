// billing-server/internal/hold/lowbalance.go

package hold

import (
	"context"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// 골드가 떨어진 것을 자동 충전에 알린다(#980). 홀드가 골드를 뺀 트랜잭션 안에서, 지갑이 잠긴 채로 부른다.
// 그래서 한 사람의 홀드들이 차례로 지나가고, 받는 쪽은 그 순간의 잔액을 본다.
//
// 받는 쪽의 오류는 홀드를 막지 않는다. 서술의 값을 받는 것이 먼저다. 받는 쪽의 일은 세이브포인트 안에서 하고,
// 실패하면 그것만 되돌리고 warning 한 줄을 남긴다. 받는 쪽은 결제 대행사를 부르지 않는다(적기만 한다).

// LowBalance 는 골드를 뺀 뒤의 잔액을 받는 것이다. *autocharge.Service 가 이 모양이다.
type LowBalance interface {
	NoteBalanceInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (bool, error)
}

// WithLowBalance 는 홀드를 걸 때마다 잔액을 lowBalance 에 알리게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) WithLowBalance(lowBalance LowBalance) {
	s.lowBalance = lowBalance
}

// noteBalance 는 잔액을 알린다. 붙여 둔 것이 없으면 아무것도 하지 않는다. 실패하면 그 일만 되돌린다.
func (s *Service) noteBalance(ctx context.Context, tx pgx.Tx, userID uuid.UUID) {
	if s.lowBalance == nil {
		return
	}
	savepoint, err := tx.Begin(ctx)
	if err == nil {
		_, err = s.lowBalance.NoteBalanceInTx(ctx, savepoint, userID)
		err = finishSavepoint(ctx, savepoint, err)
	}
	if err != nil {
		slog.WarnContext(ctx, "자동 충전할 일을 보지 못했다. 홀드는 걸었다",
			slog.String("operation", "hold.place"),
			slog.String("error_code", "autocharge.note_failed"),
			slog.String("error_message", err.Error()),
		)
	}
}

// finishSavepoint 는 일이 되었으면 세이브포인트를 놓고, 안 되었으면 되돌린다. 일의 오류나 놓지 못한 오류를 돌려준다.
func finishSavepoint(ctx context.Context, savepoint pgx.Tx, workErr error) error {
	if workErr != nil {
		_ = savepoint.Rollback(ctx)
		return workErr
	}
	return savepoint.Commit(ctx)
}
