// billing-server/internal/hold/expire.go

package hold

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/batch"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
)

// ExpireDue 는 만료 시각이 지났는데 아직 held 인 홀드를 오래된 것부터 limit 개까지 돌려준다(정리 작업).
// 돌려준 홀드의 수를 돌려준다. 크레딧은 뺐던 자리로 돌아간다. 돌려준 이유는 expired 로 적힌다.
//
// 홀드 하나가 트랜잭션 하나다. 하나가 실패해도 나머지는 마저 돌려주고, 실패한 수를 오류로 알린다(batch.Each).
// 읽은 뒤에 다른 요청이 확정하거나 연장했으면 그 홀드는 건너뛴다(조건이 붙은 UPDATE). 정리 작업을 둘 띄워도 한 번만 돌려준다.
func (s *Service) ExpireDue(ctx context.Context, limit int) (int, error) {
	now := s.clock()
	ids, err := holddb.New(s.pool).ListExpiredHolds(ctx, holddb.ListExpiredHoldsParams{Now: now, RowLimit: int32(limit)})
	if err != nil {
		return 0, err
	}
	return batch.Each(ctx, ids, s.expireOne)
}

// expireOne 은 홀드 하나를 만료로 돌려준다. 그사이에 끝났거나 연장되었으면 false 다.
func (s *Service) expireOne(ctx context.Context, id uuid.UUID) (bool, error) {
	_, changed, err := s.giveBack(ctx, func(queries *holddb.Queries) (holddb.Hold, error) {
		return queries.ExpireHold(ctx, holddb.ExpireHoldParams{ID: id, Now: s.clock()})
	})
	return changed, err
}
