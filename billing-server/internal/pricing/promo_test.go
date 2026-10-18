// billing-server/internal/pricing/promo_test.go

// 가격표의 행사가 표시(Promo)와 베이직 등급을 실제 DB 에서 시험한다.
package pricing_test

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// promoEnd 는 행사가가 끝나는 때다. 이 테스트들은 그때의 정가를 먼저 예약한다.
var promoEnd = startedAt.Add(7 * 24 * time.Hour)

// scheduleRegular 는 행사가 끝나는 때의 정가를 예약한다.
func (f fixture) scheduleRegular(credits int64) {
	f.t.Helper()
	regular := f.change(0)
	regular.Credits, regular.EffectiveAt = credit.Amount(credits), promoEnd
	f.set(regular)
}

// promo 는 지금부터의 행사가 줄을 만든다.
func (f fixture) promo(credits int64) pricing.Change {
	change := f.change(credit.Amount(credits))
	change.Promo = true
	return change
}

func TestAPromoNeedsALaterLine(t *testing.T) {
	f := setUp(t)

	_, err := f.service.Set(ctx(t), f.promo(330))

	if !errors.Is(err, pricing.ErrPromoNeedsEnd) {
		t.Fatalf("오류 = %v. ErrPromoNeedsEnd 이어야 한다", err)
	}
	if n := f.historyOf(f.code); n != 0 {
		t.Errorf("줄이 %d 개 들어갔다", n)
	}
}

func TestALaterLineBeforeThePromoDoesNotCount(t *testing.T) {
	// 행사가보다 이른 줄은 끝이 아니다. 행사가 줄의 적용 시각보다 늦은 줄만 센다
	f := setUp(t)
	f.set(f.change(300))
	late := f.promo(330)
	late.EffectiveAt = startedAt.Add(time.Hour)

	if _, err := f.service.Set(ctx(t), late); !errors.Is(err, pricing.ErrPromoNeedsEnd) {
		t.Fatalf("오류 = %v. ErrPromoNeedsEnd 이어야 한다", err)
	}
}

func TestAPromoEndsAtTheNextLine(t *testing.T) {
	f := setUp(t)
	f.scheduleRegular(440)

	version := f.set(f.promo(330))

	if !version.Promo || version.Credits != 330 {
		t.Fatalf("넣은 줄 = %+v. 330 행사가여야 한다", version)
	}
	price, err := f.priceNow()
	if err != nil || price.Credits != 330 || !price.Promo {
		t.Fatalf("지금 값 = %+v, %v. 330 행사가여야 한다", price, err)
	}
	listing, found := f.listing()
	if !found || listing.Current == nil || !listing.Current.Promo || listing.Next == nil {
		t.Fatalf("목록 = %+v", listing)
	}
	if listing.Next.Credits != 440 || listing.Next.Promo || !listing.Next.EffectiveAt.Equal(promoEnd) {
		t.Errorf("다음 값 = %+v. %s 부터 정가 440 이어야 한다", listing.Next, promoEnd)
	}

	f.clock.Advance(promoEnd.Sub(startedAt))
	price, err = f.priceNow()
	if err != nil || price.Credits != 440 || price.Promo {
		t.Errorf("행사가 끝난 뒤 = %+v, %v. 정가 440 이어야 한다", price, err)
	}
}

func TestAPromoCanFollowAPromo(t *testing.T) {
	// 행사가 다음에 다른 행사가를 이어 붙이면 목록의 다음 값도 행사가로 보인다
	f := setUp(t)
	regular := f.change(440)
	regular.EffectiveAt = promoEnd.Add(7 * 24 * time.Hour)
	f.set(regular)
	second := f.promo(380)
	second.EffectiveAt = promoEnd
	f.set(second)
	f.set(f.promo(330))

	listing, found := f.listing()

	if !found || listing.Current == nil || !listing.Current.Promo || listing.Next == nil {
		t.Fatalf("목록 = %+v", listing)
	}
	if listing.Next.Credits != 380 || !listing.Next.Promo {
		t.Errorf("다음 값 = %+v. 380 행사가여야 한다", listing.Next)
	}
}

func TestAStopEndsAPromoToo(t *testing.T) {
	// 행사가로 팔다가 판매를 멈추는 것도 끝이다
	f := setUp(t)
	f.set(f.change(300))
	stop := f.change(0)
	stop.EffectiveAt = promoEnd
	if _, err := f.service.Stop(ctx(t), stop); err != nil {
		t.Fatalf("판매 중지를 예약하지 못했다: %v", err)
	}
	f.clock.Advance(time.Minute)

	if version := f.set(f.promo(200)); !version.Promo {
		t.Errorf("넣은 줄 = %+v. 행사가여야 한다", version)
	}
}

func TestAStopCannotBeAPromo(t *testing.T) {
	f := setUp(t)
	f.set(f.change(300))
	stop := f.change(0)
	stop.Promo = true

	if _, err := f.service.Stop(ctx(t), stop); !errors.Is(err, pricing.ErrPromoStop) {
		t.Fatalf("오류 = %v. ErrPromoStop 이어야 한다", err)
	}
	if n := f.historyOf(f.code); n != 1 {
		t.Errorf("줄이 %d 개다. 처음 한 줄 그대로여야 한다", n)
	}
}

func TestThePromoMarkIsNotInherited(t *testing.T) {
	// 등급과 달리 행사가 표시는 이어받지 않는다. 표시 없이 값을 바꾸면 정가다
	f := setUp(t)
	f.scheduleRegular(440)
	f.set(f.promo(330))
	f.clock.Advance(time.Minute)

	if version := f.set(f.change(300)); version.Promo {
		t.Errorf("넣은 줄 = %+v. 정가여야 한다", version)
	}
}

func TestImportMarksTheCurrentValueAsAPromo(t *testing.T) {
	// 이미 파는 값에 행사가 표시만 붙인다. 값과 등급은 같다
	f := setUp(t)
	f.set(f.change(330))
	f.scheduleRegular(440)
	f.clock.Advance(time.Minute)

	planned, err := f.service.Import(ctx(t), []pricing.Entry{{Code: f.code, Credits: 330, Promo: true}}, "행사가로 표시", "test")

	if err != nil || len(planned) != 1 || planned[0].Effect != pricing.EffectPromo {
		t.Fatalf("계산 = %+v, %v. 행사 표시여야 한다", planned, err)
	}
	if price, err := f.priceNow(); err != nil || !price.Promo || price.Credits != 330 {
		t.Errorf("지금 값 = %+v, %v. 330 행사가여야 한다", price, err)
	}
	// 다시 정가로 적으면 표시를 뗀다. 이것도 행사 표시의 바뀜이다
	f.clock.Advance(time.Minute)
	planned, err = f.service.Plan(ctx(t), []pricing.Entry{{Code: f.code, Credits: 330}}, "표시를 뗀다", "test")
	if err != nil || planned[0].Effect != pricing.EffectPromo {
		t.Errorf("계산 = %+v, %v. 행사 표시여야 한다", planned, err)
	}
}

func TestImportCallsTheRaiseAfterAPromoItsEnd(t *testing.T) {
	// 행사가 다음의 정가는 올림이 아니라 행사 끝이다. 공급사 인상과 나눠 보인다
	f := setUp(t)
	f.scheduleRegular(500)
	f.set(f.promo(330))
	earlier := startedAt.Add(3 * 24 * time.Hour)

	planned, err := f.service.Plan(ctx(t), []pricing.Entry{{Code: f.code, Credits: 440, EffectiveAt: earlier}}, "정가", "test")

	if err != nil || planned[0].Effect != pricing.EffectPromoEnd {
		t.Fatalf("계산 = %+v, %v. 행사 끝이어야 한다", planned, err)
	}
	if planned[0].Before == nil || !planned[0].Before.Promo {
		t.Errorf("전 값 = %+v. 행사가여야 한다", planned[0].Before)
	}
	// 행사가에서 행사가로 오르는 것은 그냥 올림이다
	planned, err = f.service.Plan(ctx(t), []pricing.Entry{{Code: f.code, Credits: 400, EffectiveAt: earlier, Promo: true}}, "더 오른 행사가", "test")
	if err != nil || planned[0].Effect != pricing.EffectRaise {
		t.Errorf("계산 = %+v, %v. 올림이어야 한다", planned, err)
	}
}

func TestImportRefusesAPromoWithoutAnEndAndWritesNothing(t *testing.T) {
	f := setUp(t)
	other := newCode()
	entries := []pricing.Entry{
		{Code: other, Credits: 100, Tier: pricing.TierStandard},
		{Code: f.code, Credits: 330, Tier: pricing.TierStandard, Promo: true},
	}

	_, err := f.service.Import(ctx(t), entries, "행사가", "test")

	if !errors.Is(err, pricing.ErrPromoNeedsEnd) {
		t.Fatalf("오류 = %v. ErrPromoNeedsEnd 이어야 한다", err)
	}
	if n := f.historyOf(other); n != 0 {
		t.Errorf("다른 줄이 %d 개 들어갔다. 하나도 넣지 않아야 한다", n)
	}
}

func TestImportRefusesAStoppingPromo(t *testing.T) {
	f := setUp(t)
	f.set(f.change(300))

	_, err := f.service.Plan(ctx(t), []pricing.Entry{{Code: f.code, Stop: true, Promo: true}}, "멈춤", "test")

	if !errors.Is(err, pricing.ErrPromoStop) {
		t.Fatalf("오류 = %v. ErrPromoStop 이어야 한다", err)
	}
}

func TestABasicNameIsSoldAsBasic(t *testing.T) {
	f := setUp(t)
	change := f.change(10)
	change.Tier = pricing.TierBasic

	version := f.set(change)

	if version.Tier != pricing.TierBasic {
		t.Fatalf("넣은 줄 = %+v. basic 이어야 한다", version)
	}
	if tier := f.tierNow(); tier != pricing.TierBasic || tier.PaidOnly() {
		t.Errorf("지금 등급 = %q. 골드만이 아닌 basic 이어야 한다", tier)
	}
}
