// billing-server/internal/pricing/read.go

package pricing

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing/pricingdb"
)

// At 은 그 이름의 at 시각의 값을 돌려준다. 홀드를 걸 때 그 홀드의 시계로 부른다.
// 그런 이름이 없으면(그 시각에 적용된 줄이 없는 것도) ErrUnknownCode, 판매를 멈췄으면 ErrNotForSale 이다.
func (s *Service) At(ctx context.Context, code string, at time.Time) (Price, error) {
	row, err := pricingdb.New(s.pool).CurrentPrice(ctx, pricingdb.CurrentPriceParams{Code: code, Now: at.UTC()})
	if errors.Is(err, pgx.ErrNoRows) {
		return Price{}, ErrUnknownCode
	}
	if err != nil {
		return Price{}, err
	}
	if row.Amount == nil {
		return Price{}, ErrNotForSale
	}
	return toPrice(row), nil
}

// toPrice 는 값이 있는 줄을 Price 로 바꾼다. 부르는 쪽이 row.Amount 가 nil 이 아닌지 확인했다.
func toPrice(row pricingdb.PriceVersion) Price {
	return Price{Code: row.Code, Credits: *row.Amount, Tier: Tier(row.Tier), Promo: row.Promo, Since: row.EffectiveAt}
}

// Current 는 이름마다 지금 적용된 줄을 이름 순서로 돌려준다. 판매를 멈춘 이름도 함께 돌려준다(OnSale 이 false).
func (s *Service) Current(ctx context.Context) ([]Version, error) {
	rows, err := pricingdb.New(s.pool).CurrentPrices(ctx, s.clock())
	if err != nil {
		return nil, err
	}
	return toVersions(rows), nil
}

// History 는 그 이름의 모든 줄을 적용 시각 순서로 돌려준다. 아직 적용되지 않은 예약도 함께 돌려준다.
// 그런 이름이 없으면 빈 목록이다.
func (s *Service) History(ctx context.Context, code string) ([]Version, error) {
	rows, err := pricingdb.New(s.pool).PriceHistory(ctx, code)
	if err != nil {
		return nil, err
	}
	return toVersions(rows), nil
}

// toVersions 는 DB 의 줄들을 이 패키지의 모양으로 바꾼다.
func toVersions(rows []pricingdb.PriceVersion) []Version {
	versions := make([]Version, len(rows))
	for i, row := range rows {
		versions[i] = toVersion(row)
	}
	return versions
}

// toVersion 은 DB 의 줄 하나를 이 패키지의 모양으로 바꾼다.
func toVersion(row pricingdb.PriceVersion) Version {
	version := Version{
		ID:          row.ID,
		Code:        row.Code,
		Tier:        Tier(row.Tier),
		Promo:       row.Promo,
		EffectiveAt: row.EffectiveAt,
		Reason:      row.Reason,
		ChangedBy:   row.ChangedBy,
		CreatedAt:   row.CreatedAt,
	}
	if row.Amount != nil {
		version.Credits, version.OnSale = *row.Amount, true
	}
	return version
}
