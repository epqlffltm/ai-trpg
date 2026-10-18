// billing-server/internal/pricing/tier_test.go

// 가격표의 등급(standard, premium)을 실제 DB 에서 시험한다(#338).
package pricing_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// tierNow 는 이 테스트의 이름의 지금 등급이다.
func (f fixture) tierNow() pricing.Tier {
	f.t.Helper()
	price, err := f.priceNow()
	if err != nil {
		f.t.Fatalf("지금의 값을 읽지 못했다: %v", err)
	}
	return price.Tier
}

func TestANewNameNeedsATier(t *testing.T) {
	f := setUp(t)
	change := f.change(120)
	change.Tier = ""

	_, err := f.service.Set(ctx(t), change)

	if !errors.Is(err, pricing.ErrMissingTier) {
		t.Fatalf("오류 = %v. ErrMissingTier 이어야 한다", err)
	}
	if n := f.historyOf(f.code); n != 0 {
		t.Errorf("줄이 %d 개 들어갔다", n)
	}
}

func TestAnUnknownTierIsRefused(t *testing.T) {
	f := setUp(t)
	change := f.change(120)
	change.Tier = "gold"

	if _, err := f.service.Set(ctx(t), change); !errors.Is(err, pricing.ErrInvalidTier) {
		t.Errorf("오류 = %v. ErrInvalidTier 이어야 한다", err)
	}
}

func TestTheTierIsKeptUnlessChanged(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	f.clock.Advance(time.Minute)
	same := f.change(150)
	same.Tier = ""
	if version := f.set(same); version.Tier != pricing.TierStandard {
		t.Errorf("적지 않은 등급 = %q. 그때의 등급(standard)이어야 한다", version.Tier)
	}

	f.clock.Advance(time.Minute)
	premium := f.change(150)
	premium.Tier = pricing.TierPremium
	f.set(premium)
	if got := f.tierNow(); got != pricing.TierPremium {
		t.Errorf("바꾼 등급 = %q", got)
	}

	f.clock.Advance(time.Minute)
	raise := f.change(200)
	raise.Tier = ""
	if version := f.set(raise); version.Tier != pricing.TierPremium {
		t.Errorf("값만 올린 줄의 등급 = %q. premium 이 그대로여야 한다", version.Tier)
	}
	if n := f.historyOf(f.code); n != 4 {
		t.Errorf("줄 %d 개. 등급을 바꾸는 것도 줄을 더해야 한다", n)
	}
}

func TestStoppingKeepsTheTierForTheNextSale(t *testing.T) {
	f := setUp(t)
	premium := f.change(600)
	premium.Tier = pricing.TierPremium
	f.set(premium)
	f.clock.Advance(time.Minute)
	stopped, err := f.service.Stop(ctx(t), pricing.Change{Code: f.code, Reason: "r", ChangedBy: "b"})
	if err != nil || stopped.Tier != pricing.TierPremium {
		t.Fatalf("멈춘 줄 = %+v, %v. 그때의 등급이 적혀야 한다", stopped, err)
	}

	f.clock.Advance(time.Minute)
	resume := f.change(600)
	resume.Tier = ""
	if version := f.set(resume); version.Tier != pricing.TierPremium {
		t.Errorf("다시 판 줄의 등급 = %q. 멈추기 전의 등급이어야 한다", version.Tier)
	}
}

func TestATierChangeCanBeScheduled(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	later := startedAt.Add(time.Hour)
	premium := f.change(120)
	premium.Tier, premium.EffectiveAt = pricing.TierPremium, later
	f.set(premium)

	if got := f.tierNow(); got != pricing.TierStandard {
		t.Errorf("예약 전의 등급 = %q", got)
	}
	listing, _ := f.listing()
	if listing.Current == nil || listing.Current.Tier != pricing.TierStandard || listing.Next == nil || listing.Next.Tier != pricing.TierPremium {
		t.Errorf("목록 = 지금 %+v, 다음 %+v", listing.Current, listing.Next)
	}
	f.clock.Advance(time.Hour)
	if got := f.tierNow(); got != pricing.TierPremium {
		t.Errorf("예약 뒤의 등급 = %q", got)
	}
}

func TestImportRetiersAndKeepsTiers(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	kept, fresh := newCode(), newCode()
	keptChange := f.change(300)
	keptChange.Code, keptChange.Tier = kept, pricing.TierPremium
	f.set(keptChange)
	f.clock.Advance(time.Minute)
	entries := []pricing.Entry{
		{Code: f.code, Credits: 120, Tier: pricing.TierPremium},
		{Code: kept, Credits: 320},
		{Code: fresh, Credits: 70, Tier: pricing.TierStandard},
	}

	planned, err := f.service.Import(ctx(t), entries, "등급", "test")

	if err != nil || len(planned) != 3 {
		t.Fatalf("넣기 = %+v, %v", planned, err)
	}
	if planned[0].Effect != pricing.EffectRetier || planned[0].Tier != pricing.TierPremium || planned[0].Before.Tier != pricing.TierStandard {
		t.Errorf("등급만 바꾼 줄 = %+v", planned[0])
	}
	if planned[1].Effect != pricing.EffectRaise || planned[1].Tier != pricing.TierPremium {
		t.Errorf("등급을 적지 않은 줄 = %+v. 그때의 등급(premium)이어야 한다", planned[1])
	}
	if got := f.tierNow(); got != pricing.TierPremium {
		t.Errorf("넣은 뒤의 등급 = %q", got)
	}
}

func TestImportNeedsATierForNewNames(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	entries := []pricing.Entry{{Code: f.code, Credits: 130}, {Code: newCode(), Credits: 70}}

	_, err := f.service.Import(ctx(t), entries, "r", "test")

	if !errors.Is(err, pricing.ErrMissingTier) || !strings.Contains(err.Error(), "2번째 줄") {
		t.Errorf("오류 = %v. 2번째 줄의 ErrMissingTier 이어야 한다", err)
	}
	if n := f.historyOf(f.code); n != 1 {
		t.Errorf("첫 줄이 들어갔다(줄 %d 개)", n)
	}
}

func TestASameValueWithTheSameTierIsSkipped(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))

	planned, err := f.service.Plan(ctx(t), []pricing.Entry{{Code: f.code, Credits: 120, Tier: pricing.TierStandard}}, "r", "test")

	if err != nil || planned[0].Effect != pricing.EffectSame {
		t.Errorf("계산 = %+v, %v. 값과 등급이 같으면 같음이어야 한다", planned, err)
	}
}
