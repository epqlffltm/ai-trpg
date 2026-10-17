// billing-server/internal/pricing/list.go

package pricing

import (
	"context"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing/pricingdb"
)

// 가격 목록. 게임 서버가 받아 캐싱하고, 자기 모델 목록과 이름으로 맞춰 붙여 로그인한 사용자에게 보여 준다.
//
// 이름마다 지금 값과 다음에 바뀔 값(예약)을 함께 준다. 예약까지 받아 두면 부르는 쪽이 그 시각에 스스로 갈아 끼울 수 있고,
// 사용자에게 "12월 1일부터 240" 처럼 미리 알릴 수 있다.
// 목록은 보여 주는 값일 뿐이다. 실제로 받는 값은 홀드를 걸 때 그 시각의 가격표(At)로 정한다.

// Listing 은 가격 목록의 이름 하나다.
type Listing struct {
	Code string
	// Current 는 지금 받는 값이다. 지금 팔지 않으면(판 적이 없거나 판매를 멈췄으면) nil 이다.
	Current *Price
	// Next 는 다음에 바뀔 값이다. 예약이 없으면 nil 이다.
	Next *Scheduled
}

// Scheduled 는 아직 적용되지 않은 다음 값이다.
type Scheduled struct {
	// Credits 는 바뀔 값이다. OnSale 이 false 면(판매를 멈추는 예약) 0 이다.
	Credits     credit.Amount
	OnSale      bool
	Tier        Tier
	EffectiveAt time.Time
}

// List 는 지금 팔고 있거나 바뀔 예약이 있는 이름들을 이름 순서로 돌려준다. 판매를 멈췄고 예약도 없는 이름은 뺀다.
// 지금 값과 예약을 한 스냅샷(읽기만 하는 트랜잭션)에서 읽는다. 그사이에 더해진 줄 때문에 둘이 어긋나지 않는다.
func (s *Service) List(ctx context.Context) ([]Listing, error) {
	now := s.clock()
	var current, upcoming []pricingdb.PriceVersion
	err := pgx.BeginTxFunc(ctx, s.pool, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly}, func(tx pgx.Tx) error {
		queries := pricingdb.New(tx)
		var err error
		if current, err = queries.CurrentPrices(ctx, now); err != nil {
			return err
		}
		upcoming, err = queries.UpcomingPrices(ctx, now)
		return err
	})
	if err != nil {
		return nil, err
	}
	return mergeListings(toVersions(current), toVersions(upcoming)), nil
}

// mergeListings 는 이름마다의 지금 줄과 다음 줄을 합쳐 이름 순서의 목록으로 만든다.
// 지금 팔지 않고 예약도 없는 이름은 뺀다.
func mergeListings(current []Version, upcoming []Version) []Listing {
	byCode := map[string]*Listing{}
	for _, version := range current {
		if version.OnSale {
			listingFor(byCode, version.Code).Current = &Price{Code: version.Code, Credits: version.Credits, Tier: version.Tier, Since: version.EffectiveAt}
		}
	}
	for _, version := range upcoming {
		listingFor(byCode, version.Code).Next = &Scheduled{Credits: version.Credits, OnSale: version.OnSale, Tier: version.Tier, EffectiveAt: version.EffectiveAt}
	}
	return sortedListings(byCode)
}

// listingFor 는 그 이름의 목록 줄을 찾고, 없으면 만들어 넣는다.
func listingFor(byCode map[string]*Listing, code string) *Listing {
	listing, ok := byCode[code]
	if !ok {
		listing = &Listing{Code: code}
		byCode[code] = listing
	}
	return listing
}

// sortedListings 는 목록 줄들을 이름 순서로 늘어놓는다. 부르는 쪽이 같은 목록을 늘 같은 순서로 받는다(버전 비교).
func sortedListings(byCode map[string]*Listing) []Listing {
	listings := make([]Listing, 0, len(byCode))
	for _, listing := range byCode {
		listings = append(listings, *listing)
	}
	sort.Slice(listings, func(i, j int) bool { return listings[i].Code < listings[j].Code })
	return listings
}
