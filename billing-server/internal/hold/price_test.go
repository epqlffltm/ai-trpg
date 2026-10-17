// billing-server/internal/hold/price_test.go

// 홀드가 DB 의 가격표에서 값을 찾는 것을 시험한다. 테스트마다 새 이름("test.<번호>")을 지어 쓴다.
package hold_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// newPrice 는 이 테스트만 쓰는 이름에 값을 정하고 그 이름을 돌려준다. 적용 시각은 지금이다.
func (f fixture) newPrice(credits credit.Amount) string {
	f.t.Helper()
	code := "test." + uuid.NewString()
	f.setPrice(code, credits, time.Time{})
	return code
}

// setPrice 는 그 이름의 값을 정한다. at 이 비었으면 지금부터다.
func (f fixture) setPrice(code string, credits credit.Amount, at time.Time) {
	f.t.Helper()
	change := pricing.Change{Code: code, Credits: credits, EffectiveAt: at, Reason: "테스트", ChangedBy: "test"}
	if _, err := pricing.NewService(f.pool, f.clock.Now).Set(ctx(f.t), change); err != nil {
		f.t.Fatalf("값을 정하지 못했다: %v", err)
	}
}

func TestPlaceTakesTheValueFromThePriceList(t *testing.T) {
	f := setUp(t)
	f.fund(200, 0)
	code := f.newPrice(120)

	placed, isNew, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if err != nil || !isNew || placed.Amount != 120 || placed.PriceCode != code {
		t.Fatalf("홀드 = %+v, 새것 = %v, %v", placed, isNew, err)
	}
	f.wantBalance(80, 0)
}

func TestAHoldKeepsTheValueItWasPlacedWith(t *testing.T) {
	// 라운드 중에 값이 바뀌었다. 이미 건 홀드와, 같은 이름표로 다시 보낸 요청은 옛 값이다. 새 홀드부터 새 값이다
	f := setUp(t)
	f.fund(500, 0)
	code := f.newPrice(100)
	reference := newReference()
	if _, _, err := f.service.Place(ctx(t), source, f.user, reference, code); err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	f.clock.Advance(time.Minute)
	f.setPrice(code, 150, time.Time{})

	again, isNew, err := f.service.Place(ctx(t), source, f.user, reference, code)
	if err != nil || isNew || again.Amount != 100 {
		t.Errorf("다시 보낸 홀드 = %+v, 새것 = %v, %v", again, isNew, err)
	}
	captured, err := f.service.Capture(ctx(t), source, reference)
	if err != nil || captured.Amount != 100 {
		t.Errorf("확정 = %+v, %v", captured, err)
	}
	next, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code)
	if err != nil || next.Amount != 150 {
		t.Errorf("새 홀드 = %+v, %v", next, err)
	}
	f.wantBalance(250, 0)
}

func TestAStoppedOrScheduledPriceCannotBeHeldYet(t *testing.T) {
	f := setUp(t)
	f.fund(500, 0)
	stopped := f.newPrice(100)
	f.clock.Advance(time.Minute)
	if _, err := pricing.NewService(f.pool, f.clock.Now).Stop(ctx(t), pricing.Change{Code: stopped, Reason: "r", ChangedBy: "b"}); err != nil {
		t.Fatalf("판매를 멈추지 못했다: %v", err)
	}
	scheduled := "test." + uuid.NewString()
	f.setPrice(scheduled, 70, f.clock.Now().Add(time.Hour))

	_, _, stoppedErr := f.service.Place(ctx(t), source, f.user, newReference(), stopped)
	_, _, earlyErr := f.service.Place(ctx(t), source, f.user, newReference(), scheduled)

	// 멈춘 이름과 아직 없는 이름을 가린다. 부르는 서버가 다르게 다룬다
	if !errors.Is(stoppedErr, hold.ErrPriceNotForSale) || !errors.Is(earlyErr, hold.ErrUnknownPrice) {
		t.Errorf("멈춘 이름 = %v, 예약 전 = %v. ErrPriceNotForSale, ErrUnknownPrice 이어야 한다", stoppedErr, earlyErr)
	}
	f.wantBalance(500, 0)
	if got := f.count("holds", ""); got != 0 {
		t.Errorf("홀드가 %d 개 남았다", got)
	}

	// 예약한 때가 되면 걸린다. 값은 홀드의 시계로 찾는다
	f.clock.Advance(time.Hour)
	placed, _, err := f.service.Place(ctx(t), source, f.user, newReference(), scheduled)
	if err != nil || placed.Amount != 70 {
		t.Errorf("예약한 때의 홀드 = %+v, %v", placed, err)
	}
}
