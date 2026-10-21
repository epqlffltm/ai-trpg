// billing-server/internal/hold/withdraw.go

package hold

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
)

// ReleaseHeldInTx 는 그 사람의 held 홀드를 모두 돌려준다(탈퇴, #603). 돌려준 이유는 withdrawn 이다. 돌려준 수를 돌려준다.
// 부르는 쪽이 연 트랜잭션(tx) 안에서 한다. 부르는 쪽은 먼저 그 사람의 지갑을 잠근다(wallet.LockExisting).
// 그래야 이 사이에 새 홀드가 걸리지 않는다. 홀드를 거는 일도 지갑을 잠근다.
//
// 크레딧은 뺐던 자리로 돌아간다. 부르는 쪽이 이어서 그것까지 없앤다(wallet.ForfeitInTx).
// 상태를 바꾸는 문장 하나가 held 인 것만 바꾼다. 홀드를 건 서버가 그사이에 확정하거나 돌려준 홀드는 건드리지 않고,
// 이 문장이 바꾼 홀드는 그 서버의 확정을 기다리게 한 뒤 이미 돌려준 홀드로 답하게 한다(ErrAlreadyReleased). 몇 번을 불러도 같다.
func (s *Service) ReleaseHeldInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (int, error) {
	rows, err := holddb.New(tx).WithdrawHeldHolds(ctx, holddb.WithdrawHeldHoldsParams{UserID: userID, Now: s.clock()})
	if err != nil {
		return 0, err
	}
	for _, row := range rows {
		if err := s.wallet.ReturnForHold(ctx, tx, row.UserID, row.ID); err != nil {
			return 0, err
		}
	}
	return len(rows), nil
}
