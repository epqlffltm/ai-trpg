// billing-server/internal/pricing/list_test.go

// 가격 목록(List)을 실제 DB 에서 시험한다. 목록에는 다른 테스트의 이름도 함께 나오므로 이 테스트의 이름만 찾아 본다.
package pricing_test

import (
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// listing 은 가격 목록에서 이 테스트의 이름을 찾는다. 없으면 두 번째 값이 false 다.
func (f fixture) listing() (pricing.Listing, bool) {
	f.t.Helper()
	listings, err := f.service.List(ctx(f.t))
	if err != nil {
		f.t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	for _, listing := range listings {
		if listing.Code == f.code {
			return listing, true
		}
	}
	return pricing.Listing{}, false
}

func TestListShowsTheCurrentValueAndTheNextScheduledOne(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	raise := f.change(240)
	raise.EffectiveAt = startedAt.Add(48 * time.Hour)
	f.set(raise)
	later := f.change(300)
	later.EffectiveAt = startedAt.Add(96 * time.Hour)
	f.set(later)

	got, found := f.listing()

	if !found || got.Current == nil || got.Current.Credits != 120 || !got.Current.Since.Equal(startedAt) {
		t.Fatalf("지금 값 = %+v", got.Current)
	}
	// 예약이 둘이면 가장 이른 것 하나만 다음 값이다
	if got.Next == nil || !got.Next.OnSale || got.Next.Credits != 240 || !got.Next.EffectiveAt.Equal(raise.EffectiveAt) {
		t.Errorf("다음 값 = %+v", got.Next)
	}
}

func TestListMovesOnWhenTheScheduledTimePasses(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	raise := f.change(240)
	raise.EffectiveAt = startedAt.Add(time.Hour)
	f.set(raise)

	f.clock.Advance(time.Hour)
	got, _ := f.listing()

	if got.Current == nil || got.Current.Credits != 240 || got.Next != nil {
		t.Errorf("지금 = %+v, 다음 = %+v. 예약이 지금 값이 되고 다음 값은 없어야 한다", got.Current, got.Next)
	}
}

func TestListShowsAScheduledStopAndAScheduledFirstSale(t *testing.T) {
	stopping := setUp(t)
	stopping.set(stopping.change(120))
	stop := stopping.change(0)
	stop.EffectiveAt = startedAt.Add(time.Hour)
	if _, err := stopping.service.Stop(ctx(t), stop); err != nil {
		t.Fatalf("판매 중지를 예약하지 못했다: %v", err)
	}
	got, _ := stopping.listing()
	if got.Current == nil || got.Next == nil || got.Next.OnSale || !got.Next.EffectiveAt.Equal(stop.EffectiveAt) {
		t.Errorf("지금 = %+v, 다음 = %+v. 판매 중지 예약이 다음 값이어야 한다", got.Current, got.Next)
	}

	upcoming := setUp(t)
	first := upcoming.change(80)
	first.EffectiveAt = startedAt.Add(time.Hour)
	upcoming.set(first)
	got, found := upcoming.listing()
	if !found || got.Current != nil || got.Next == nil || got.Next.Credits != 80 {
		t.Errorf("지금 = %+v, 다음 = %+v. 아직 팔지 않지만 예약이 있으면 목록에 나와야 한다", got.Current, got.Next)
	}
}

func TestListLeavesOutStoppedNamesWithoutAPlan(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	f.clock.Advance(time.Minute)
	if _, err := f.service.Stop(ctx(t), f.change(0)); err != nil {
		t.Fatalf("판매를 멈추지 못했다: %v", err)
	}

	if got, found := f.listing(); found {
		t.Errorf("목록 = %+v. 판매를 멈췄고 예약도 없으면 빠져야 한다", got)
	}
}

func TestListIsInNameOrder(t *testing.T) {
	f := setUp(t)
	f.set(f.change(10))
	other := f.change(20)
	other.Code = f.code + ".b"
	f.set(other)

	listings, err := f.service.List(ctx(t))

	// 부르는 쪽은 본문의 해시로 바뀌었는지 본다. 같은 목록은 늘 같은 순서여야 한다
	if err != nil || len(listings) < 2 {
		t.Fatalf("목록 = %v, %v", listings, err)
	}
	for i := 1; i < len(listings); i++ {
		if listings[i-1].Code >= listings[i].Code {
			t.Fatalf("%d: %s 다음에 %s. 이름 순서여야 한다", i, listings[i-1].Code, listings[i].Code)
		}
	}
}
