// billing-server/internal/hold/settle.go

package hold

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
)

// Capture 는 홀드를 확정한다. 빼 둔 크레딧은 돌아오지 않는다. 크레딧은 홀드를 걸 때 이미 빠졌으므로 잔액은 바뀌지 않는다.
// 이미 확정한 홀드면 그대로 돌려준다. 몇 번을 불러도 같다. 이미 돌려준 홀드면(만료되어 돌려준 것도) ErrAlreadyReleased 다.
func (s *Service) Capture(ctx context.Context, source string, reference string) (Hold, error) {
	row, err := holddb.New(s.pool).CaptureHold(ctx, holddb.CaptureHoldParams{
		Source: source, Reference: reference, Now: s.clock(),
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
	released, changed, err := s.giveBack(ctx, func(queries *holddb.Queries) (holddb.Hold, error) {
		return queries.ReleaseHold(ctx, holddb.ReleaseHoldParams{Source: source, Reference: reference, Now: s.clock()})
	})
	if err != nil {
		return Hold{}, err
	}
	if !changed {
		return s.alreadySettled(ctx, source, reference, StatusReleased)
	}
	return released, nil
}

// Extend 는 held 인 홀드의 만료 시각을 지금부터 ttl 뒤로 민다. 연장한 홀드를 돌려준다.
// 만료 시각이 지났어도 정리 작업이 아직 돌려주지 않았으면 연장된다. 앞으로 당기지는 않는다.
// 이미 확정했으면 ErrAlreadyCaptured, 이미 돌려줬으면(만료되어 돌려준 것도) ErrAlreadyReleased, 없으면 ErrNotFound 다.
func (s *Service) Extend(ctx context.Context, source string, reference string) (Hold, error) {
	now := s.clock()
	row, err := holddb.New(s.pool).ExtendHold(ctx, holddb.ExtendHoldParams{
		Source: source, Reference: reference, ExpiresAt: now.Add(s.ttl), Now: now,
	})
	if errors.Is(err, pgx.ErrNoRows) {
		// 바라던 상태가 없다. 끝난 홀드는 어느 쪽이든 오류다
		return s.alreadySettled(ctx, source, reference, StatusHeld)
	}
	if err != nil {
		return Hold{}, err
	}
	return toHold(row), nil
}

// giveBack 은 change 로 홀드를 released 로 바꾸고, 바꿨으면 빼 둔 크레딧을 돌려놓는다. 둘은 한 트랜잭션이다.
// change 가 바꿀 줄을 찾지 못했으면(held 가 아니거나 조건이 맞지 않으면) 아무것도 하지 않고 두 번째 값이 false 다.
func (s *Service) giveBack(ctx context.Context, change func(*holddb.Queries) (holddb.Hold, error)) (Hold, bool, error) {
	var released Hold
	var changed bool
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		row, err := change(holddb.New(tx))
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
		return Hold{}, false, err
	}
	return released, changed, nil
}

// alreadySettled 는 held 가 아닌 홀드에 확정, 반환, 연장이 왔을 때의 처리다.
// 바라던 상태(wanted)로 이미 끝났으면 그 홀드를 돌려주고, 다르게 끝났으면 오류다. 없는 홀드면 ErrNotFound 다.
// 연장은 바라는 상태가 held 라서 끝난 홀드는 모두 오류다.
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
