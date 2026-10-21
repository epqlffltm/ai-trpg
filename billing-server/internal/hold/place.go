// billing-server/internal/hold/place.go

package hold

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// Place 는 사용자의 크레딧을 가격표의 값만큼 먼저 빼 둔다. 프리미엄 이름이면 산 크레딧(골드)에서만 뺀다.
// source 는 부르는 서버의 이름이고, reference 는 그 서버가 이 홀드에 붙인 이름표다.
//
// 같은 서버가 같은 이름표로 다시 부르면 새로 빼지 않고 먼저 건 홀드를 돌려준다(지금의 상태 그대로. 연장하지 않는다).
// 새 홀드의 만료 시각은 지금부터 ttl 뒤다.
// 두 번째 값은 이번에 새로 걸었으면 true 다. 크레딧이 모자라면 wallet.ErrInsufficient 이고 홀드도 남지 않는다.
// 프리미엄인데 골드가 모자라면 wallet.ErrPaidInsufficient 다(ErrInsufficient 도 참이다).
// 모자라 걸지 못했으면 붙여 둔 것(WithShortfalls)에 알린다. 알리지 못해도 답은 같다.
// 이름표의 결과(처음, 다시 보냄, 다른 내용)를 센다(metrics.go). 돌아오면 트랜잭션은 이미 끝났다.
func (s *Service) Place(ctx context.Context, source string, userID uuid.UUID, reference string, priceCode string) (Hold, bool, error) {
	placed, created, err := s.place(ctx, source, userID, reference, priceCode)
	s.keys.Count(ctx, idempotencyKind, created, err, ErrReferenceReused)
	return placed, created, err
}

// place 는 Place 의 본문이다. 이름표를 보고, 가격표에서 값을 찾고, 건다. 크레딧이 모자라 걸지 못했으면 그 일을 알린다.
func (s *Service) place(ctx context.Context, source string, userID uuid.UUID, reference string, priceCode string) (Hold, bool, error) {
	if !referencePattern.MatchString(reference) {
		return Hold{}, false, ErrInvalidReference
	}
	now := s.clock()
	price, err := s.priceAt(ctx, priceCode, now)
	if err != nil {
		return Hold{}, false, err
	}
	placed, created, err := s.take(ctx, source, userID, reference, price, now)
	if errors.Is(err, wallet.ErrInsufficient) {
		s.noteShort(ctx, userID, price, err)
	}
	return placed, created, err
}

// take 는 한 트랜잭션 안에서 홀드의 줄을 만들고 지갑에서 price 만큼 뺀다. 같은 이름표의 홀드가 이미 있으면 그것을 돌려준다.
// 두 번째 값은 이번에 새로 걸었으면 true 다. 크레딧이 모자라면 홀드의 줄도 함께 되돌려진다.
func (s *Service) take(ctx context.Context, source string, userID uuid.UUID, reference string, price pricing.Price, now time.Time) (Hold, bool, error) {
	var placed Hold
	var created bool
	// 지갑이 원장에 적은 일은 커밋한 뒤에 세어진다(txn.Run)
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := holddb.New(tx)
		row, err := queries.InsertHold(ctx, holddb.InsertHoldParams{
			ID:        uuid.New(),
			UserID:    userID,
			Source:    source,
			Reference: reference,
			PriceCode: price.Code,
			Amount:    price.Credits,
			Now:       now,
			ExpiresAt: now.Add(s.ttlFor(source)),
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
		return s.wallet.TakeForHold(ctx, tx, userID, price.Credits, row.ID, fundsFor(price.Tier))
	})
	if err != nil {
		return Hold{}, false, err
	}
	return placed, created, nil
}

// priceAt 은 가격표에서 그 이름의 at 시각의 값을 찾는다. 없으면 ErrUnknownPrice, 판매를 멈췄으면 ErrPriceNotForSale 이다.
// 둘을 나눈다. 없는 이름은 부르는 서버의 버그이고, 멈춘 이름은 그 서버의 모델 목록이 아직 옛것이라는 뜻이다.
// 가격표를 읽지 못한 것(DB 오류)은 그대로 올린다. 부르는 쪽의 잘못(400)이 아니다.
func (s *Service) priceAt(ctx context.Context, code string, at time.Time) (pricing.Price, error) {
	price, err := s.prices.At(ctx, code, at)
	switch {
	case errors.Is(err, pricing.ErrUnknownCode):
		return pricing.Price{}, ErrUnknownPrice
	case errors.Is(err, pricing.ErrNotForSale):
		return pricing.Price{}, ErrPriceNotForSale
	}
	return price, err
}

// fundsFor 는 가격표의 등급으로 무엇으로 낼지 정한다. 프리미엄은 산 크레딧(골드)으로만 낸다.
func fundsFor(tier pricing.Tier) wallet.Funds {
	if tier.PaidOnly() {
		return wallet.PaidOnly
	}
	return wallet.AnyCredits
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
