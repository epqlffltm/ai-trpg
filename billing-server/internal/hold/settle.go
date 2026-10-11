// billing-server/internal/hold/settle.go

package hold

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
)

// Capture 는 홀드를 확정한다. 빼 둔 크레딧은 돌아오지 않는다. 크레딧은 홀드를 걸 때 이미 빠졌으므로 잔액은 바뀌지 않는다.
// 이미 확정한 홀드면 그대로 돌려준다. 몇 번을 불러도 같다. 이미 돌려준 홀드면 ErrAlreadyReleased 다.
func (s *Service) Capture(ctx context.Context, source string, reference string) (Hold, error) {
	row, err := holddb.New(s.pool).SettleHold(ctx, holddb.SettleHoldParams{
		Source: source, Reference: reference, Status: string(StatusCaptured), Now: s.clock(),
	})
	if errors.Is(err, pgx.ErrNoRows) {
		// held 가 아니다. 이미 끝난 홀드이거나, 없는 홀드다
		return s.alreadySettled(ctx, source, reference, StatusCaptured)
	}
	if err != nil {
		return Hold{}, err
	}
	return toHold(row), nil
}

// Release 는 홀드를 풀고 빼 둔 크레딧을 돌려준다. 둘은 한 트랜잭션이다.
// 이미 돌려준 홀드면 그대로 돌려준다. 몇 번을 불러도 크레딧은 한 번만 돌아간다. 이미 확정한 홀드면 ErrAlreadyCaptured 다.
func (s *Service) Release(ctx context.Context, source string, reference string) (Hold, error) {
	var released Hold
	var changed bool
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		row, err := holddb.New(tx).SettleHold(ctx, holddb.SettleHoldParams{
			Source: source, Reference: reference, Status: string(StatusReleased), Now: s.clock(),
		})
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		released, changed = toHold(row), true
		return s.wallet.ReturnForHold(ctx, tx, row.UserID, row.ID)
	})
	if err != nil {
		return Hold{}, err
	}
	if !changed {
		return s.alreadySettled(ctx, source, reference, StatusReleased)
	}
	return released, nil
}

// alreadySettled 는 held 가 아닌 홀드에 확정이나 반환이 왔을 때의 처리다.
// 바라던 상태(wanted)로 이미 끝났으면 그 홀드를 돌려주고, 반대로 끝났으면 오류다. 없는 홀드면 ErrNotFound 다.
func (s *Service) alreadySettled(ctx context.Context, source string, reference string, wanted Status) (Hold, error) {
	row, err := holddb.New(s.pool).GetHoldByReference(ctx, holddb.GetHoldByReferenceParams{Source: source, Reference: reference})
	if errors.Is(err, pgx.ErrNoRows) {
		return Hold{}, ErrNotFound
	}
	if err != nil {
		return Hold{}, err
	}
	current := toHold(row)
	switch {
	case current.Status == wanted:
		return current, nil
	case current.Status == StatusCaptured:
		return Hold{}, ErrAlreadyCaptured
	case current.Status == StatusReleased:
		return Hold{}, ErrAlreadyReleased
	default:
		// 바꾸려 할 때는 없던 홀드가 다시 읽는 사이에 걸렸다. 아주 드물다. 없다고 답하고, 부르는 쪽이 다시 보내면 된다
		return Hold{}, ErrNotFound
	}
}
