// billing-server/internal/hold/place.go

package hold

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// Place 는 사용자의 크레딧을 가격표의 값만큼 먼저 빼 둔다.
// source 는 부르는 서버의 이름이고, reference 는 그 서버가 이 홀드에 붙인 이름표다.
//
// 같은 서버가 같은 이름표로 다시 부르면 새로 빼지 않고 먼저 건 홀드를 돌려준다(지금의 상태 그대로).
// 두 번째 값은 이번에 새로 걸었으면 true 다. 크레딧이 모자라면 wallet.ErrInsufficient 이고 홀드도 남지 않는다.
func (s *Service) Place(ctx context.Context, source string, userID uuid.UUID, reference string, priceCode string) (Hold, bool, error) {
	if !referencePattern.MatchString(reference) {
		return Hold{}, false, ErrInvalidReference
	}
	price, ok := pricing.Find(priceCode)
	if !ok {
		return Hold{}, false, ErrUnknownPrice
	}

	var placed Hold
	var created bool
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := holddb.New(tx)
		row, err := queries.InsertHold(ctx, holddb.InsertHoldParams{
			ID:        uuid.New(),
			UserID:    userID,
			Source:    source,
			Reference: reference,
			PriceCode: price.Code,
			Amount:    price.Credits,
			Now:       s.clock(),
		})
		// 줄을 돌려받지 못했으면 같은 이름표의 홀드가 이미 있다는 뜻이다
		if errors.Is(err, pgx.ErrNoRows) {
			placed, err = existingHold(ctx, queries, source, userID, reference, price.Code)
			return err
		}
		if err != nil {
			return err
		}
		placed, created = toHold(row), true
		// 크레딧을 빼지 못하면 오류가 올라가고, 방금 만든 홀드의 줄도 함께 되돌려진다
		return s.wallet.TakeForHold(ctx, tx, userID, price.Credits, row.ID)
	})
	if err != nil {
		return Hold{}, false, err
	}
	return placed, created, nil
}

// existingHold 는 같은 이름표로 먼저 건 홀드를 돌려준다. 그 홀드의 사용자나 가격표 이름이 이번 요청과 다르면 ErrReferenceReused 다.
// 이름표는 같은데 내용이 다르면 다시 보낸 요청이 아니라 다른 요청이다. 조용히 먼저 것을 돌려주면 부르는 서버의 버그를 가린다.
func existingHold(ctx context.Context, queries *holddb.Queries, source string, userID uuid.UUID, reference string, priceCode string) (Hold, error) {
	row, err := queries.GetHoldByReference(ctx, holddb.GetHoldByReferenceParams{Source: source, Reference: reference})
	if err != nil {
		return Hold{}, err
	}
	if row.UserID != userID || row.PriceCode != priceCode {
		return Hold{}, ErrReferenceReused
	}
	return toHold(row), nil
}
