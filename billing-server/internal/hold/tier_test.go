// billing-server/internal/hold/tier_test.go

// 가격표의 등급이 홀드가 무엇으로 낼지를 정하는지 시험한다. 프리미엄은 골드(산 크레딧)로만 낸다(#338).
package hold_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// newPremium 은 이 테스트만 쓰는 프리미엄 이름을 만들고 값을 정한다.
func (f fixture) newPremium(credits credit.Amount) string {
	f.t.Helper()
	code := "test." + uuid.NewString()
	change := pricing.Change{Code: code, Credits: credits, Tier: pricing.TierPremium, Reason: "테스트", ChangedBy: "test"}
	if _, err := pricing.NewService(f.pool, f.clock.Now).Set(ctx(f.t), change); err != nil {
		f.t.Fatalf("값을 정하지 못했다: %v", err)
	}
	return code
}

// newBasic 은 이 테스트만 쓰는 베이직 이름을 만들고 값을 정한다.
func (f fixture) newBasic(credits credit.Amount) string {
	f.t.Helper()
	code := "test." + uuid.NewString()
	change := pricing.Change{Code: code, Credits: credits, Tier: pricing.TierBasic, Reason: "테스트", ChangedBy: "test"}
	if _, err := pricing.NewService(f.pool, f.clock.Now).Set(ctx(f.t), change); err != nil {
		f.t.Fatalf("값을 정하지 못했다: %v", err)
	}
	return code
}

func TestABasicHoldCanBePaidWithSilver(t *testing.T) {
	// 베이직은 스탠다드처럼 실버로 낸다. 골드가 없어도 걸린다
	f := setUp(t)
	f.fund(0, 300)
	code := f.newBasic(10)

	placed, created, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if err != nil || !created || placed.Amount != 10 {
		t.Fatalf("홀드 = %+v, 새로 = %v, 오류 = %v", placed, created, err)
	}
	f.wantBalance(0, 290)
}

func TestAPremiumHoldTakesOnlyGold(t *testing.T) {
	f := setUp(t)
	f.fund(500, 300)
	code := f.newPremium(200)

	placed, created, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if err != nil || !created || placed.Amount != 200 {
		t.Fatalf("홀드 = %+v, 새로 = %v, 오류 = %v", placed, created, err)
	}
	// 무료 크레딧부터 쓰는 설정(FreeFirst)이어도 실버는 그대로다
	f.wantBalance(300, 300)
}

func TestAPremiumHoldWithOnlySilverIsRefused(t *testing.T) {
	f := setUp(t)
	f.fund(100, 1_000)
	code := f.newPremium(200)

	_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if !errors.Is(err, wallet.ErrPaidInsufficient) {
		t.Fatalf("오류 = %v. ErrPaidInsufficient 이어야 한다", err)
	}
	// 크레딧이 모자란 다른 경우와 같이 다루는 코드도 그대로 돈다
	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Errorf("오류 = %v. ErrInsufficient 도 참이어야 한다", err)
	}
	f.wantBalance(100, 1_000)
	if n := f.count("holds", ""); n != 0 {
		t.Errorf("홀드가 %d 개 남았다", n)
	}
}

func TestAStandardHoldShortOfEverythingIsPlainInsufficient(t *testing.T) {
	f := setUp(t)
	f.fund(10, 10)
	code := f.newPrice(200)

	_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if !errors.Is(err, wallet.ErrInsufficient) || errors.Is(err, wallet.ErrPaidInsufficient) {
		t.Errorf("오류 = %v. 골드만의 부족이 아니라 그냥 부족이어야 한다", err)
	}
}

func TestAStandardHoldStillSpendsSilverFirst(t *testing.T) {
	f := setUp(t)
	f.fund(500, 300)
	code := f.newPrice(200)

	if _, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code); err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	f.wantBalance(500, 100)
}

func TestAReleasedPremiumHoldGoesBackToGold(t *testing.T) {
	f := setUp(t)
	f.fund(500, 300)
	code := f.newPremium(200)
	reference := newReference()
	if _, _, err := f.service.Place(ctx(t), source, f.user, reference, code); err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}

	released, err := f.service.Release(ctx(t), source, reference)

	if err != nil || released.Status != hold.StatusReleased {
		t.Fatalf("반환 = %+v, %v", released, err)
	}
	f.wantBalance(500, 300)
}

func TestTheTierAtPlacingTimeDecides(t *testing.T) {
	// 등급이 바뀌기 전에 건 홀드는 그때의 등급으로 냈다. 등급이 바뀐 뒤의 홀드만 새 등급을 따른다
	f := setUp(t)
	f.fund(500, 300)
	code := f.newPrice(100)
	prices := pricing.NewService(f.pool, f.clock.Now)
	later := f.clock.Now().Add(time.Hour)
	if _, err := prices.Set(ctx(t), pricing.Change{Code: code, Credits: 100, Tier: pricing.TierPremium, EffectiveAt: later, Reason: "r", ChangedBy: "b"}); err != nil {
		t.Fatalf("등급을 예약하지 못했다: %v", err)
	}

	if _, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code); err != nil {
		t.Fatalf("첫 홀드: %v", err)
	}
	f.wantBalance(500, 200)
	f.clock.Advance(time.Hour)
	if _, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code); err != nil {
		t.Fatalf("둘째 홀드: %v", err)
	}
	f.wantBalance(400, 200)
}
