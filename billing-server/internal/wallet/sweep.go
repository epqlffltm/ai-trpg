// billing-server/internal/wallet/sweep.go

package wallet

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/batch"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// ExpireIdle 는 사라질 시각이 지난 무료 크레딧을 가진 사용자를 limit 명까지 찾아, 원장에 "사라졌다"(expire)를 적는다(정리 작업).
// 정리한 사용자의 수를 돌려준다.
//
// 잔액은 이 일과 상관없이 이미 정확하다. 사라질 시각이 지난 묶음은 읽을 때 세지 않는다.
// 원장의 expire 줄은 원래 그 사용자의 다음 변경 때 적힌다. 변경이 없는 사용자는 그 줄이 끝내 적히지 않아서,
// 원장만 보면 크레딧이 남아 있는 것처럼 보인다. 이 일이 그 줄을 마저 적는다.
//
// 사용자 하나가 트랜잭션 하나다. 다른 변경처럼 지갑의 줄을 잠그고 한다. 그 사용자의 다른 요청과 겹쳐도 한 번만 적힌다.
// 한 사용자에서 실패해도 나머지는 마저 정리하고, 실패한 수를 오류로 알린다(batch.Each).
func (s *Service) ExpireIdle(ctx context.Context, limit int) (int, error) {
	users, err := walletdb.New(s.pool).ListUsersWithDueFreeGrants(ctx, walletdb.ListUsersWithDueFreeGrantsParams{
		Now: s.clock(), RowLimit: int32(limit),
	})
	if err != nil {
		return 0, err
	}
	return batch.Each(ctx, users, s.expireFor)
}

// expireFor 는 한 사용자의 지갑을 잠그고 사라질 시각이 지난 묶음을 정리한다. 다른 일은 하지 않는다.
// 지갑을 잠글 때 늘 하는 정리(lockAndRun)가 곧 이 일이다.
func (s *Service) expireFor(ctx context.Context, userID uuid.UUID) (bool, error) {
	err := s.withLockedWallet(ctx, userID, func(context.Context, change) error { return nil })
	return err == nil, err
}
