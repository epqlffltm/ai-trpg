// billing-server/internal/eligibility/store_test.go

package eligibility_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// clock 은 테스트가 옮기는 시계다.
type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

// setUp 은 테스트용 스키마에 붙는 서비스와 시계를 만든다. 지금은 한국 시각 2026-10-18 10시다.
func setUp(t *testing.T) (*eligibility.Service, *clock) {
	t.Helper()
	c := &clock{now: time.Date(2026, 10, 18, 1, 0, 0, 0, time.UTC)}
	return eligibility.NewService(testenv.Pool(t), c.Now), c
}

func apply(t *testing.T, service *eligibility.Service, update eligibility.Update) eligibility.Outcome {
	t.Helper()
	outcome, err := service.Apply(context.Background(), update)
	if err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}
	return outcome
}

func TestAnUnknownUserMustVerifyFirst(t *testing.T) {
	service, _ := setUp(t)

	if err := service.Check(context.Background(), uuid.New()); !errors.Is(err, eligibility.ErrVerificationRequired) {
		t.Errorf("%v. 본인인증 전이어야 한다", err)
	}
}

func TestAnAdultMayPay(t *testing.T) {
	service, _ := setUp(t)
	user := uuid.New()

	outcome := apply(t, service, eligibility.Update{UserID: user, Version: 1})

	if outcome != eligibility.Applied {
		t.Errorf("결과 = %s", outcome)
	}
	if err := service.Check(context.Background(), user); err != nil {
		t.Errorf("%v. 성년은 결제할 수 있다", err)
	}
}

func TestAMinorNeedsTheConsentUntilTheDayOfAdulthood(t *testing.T) {
	service, c := setUp(t)
	user := uuid.New()
	// 한국 날짜로 내일이 만 19세 생일이다
	tomorrow := time.Date(2026, 10, 19, 0, 0, 0, 0, time.UTC)
	apply(t, service, eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: &tomorrow})
	ctx := context.Background()

	before := service.Check(ctx, user)
	// UTC 15시가 한국 자정이다
	c.now = time.Date(2026, 10, 18, 15, 0, 0, 0, time.UTC)
	after := service.Check(ctx, user)

	if !errors.Is(before, eligibility.ErrGuardianConsentRequired) || after != nil {
		t.Errorf("전날 = %v, 그날 = %v", before, after)
	}
}

func TestConsentAndRevocationFollowTheVersions(t *testing.T) {
	service, _ := setUp(t)
	user := uuid.New()
	adultDay := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	ctx := context.Background()

	apply(t, service, eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: &adultDay})
	apply(t, service, eligibility.Update{UserID: user, Version: 2, LegalAdultFrom: &adultDay, GuardianConsent: true})
	consented := service.Check(ctx, user)
	apply(t, service, eligibility.Update{UserID: user, Version: 3, LegalAdultFrom: &adultDay})
	revoked := service.Check(ctx, user)

	if consented != nil || !errors.Is(revoked, eligibility.ErrGuardianConsentRequired) {
		t.Errorf("동의 뒤 = %v, 철회 뒤 = %v", consented, revoked)
	}
}

func TestAnOldVersionArrivingLateChangesNothing(t *testing.T) {
	// 철회(버전 3)가 먼저 닿고 동의(버전 2)가 늦게 닿았다. 늦은 동의가 철회를 덮으면 철회한 보호자의 뜻을 거스른다
	service, _ := setUp(t)
	user := uuid.New()
	adultDay := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)

	apply(t, service, eligibility.Update{UserID: user, Version: 3, LegalAdultFrom: &adultDay})
	late := apply(t, service, eligibility.Update{UserID: user, Version: 2, LegalAdultFrom: &adultDay, GuardianConsent: true})
	again := apply(t, service, eligibility.Update{UserID: user, Version: 3, LegalAdultFrom: &adultDay})

	if late != eligibility.Stale || again != eligibility.Stale {
		t.Errorf("늦은 것 = %s, 같은 것을 다시 = %s", late, again)
	}
	if err := service.Check(context.Background(), user); !errors.Is(err, eligibility.ErrGuardianConsentRequired) {
		t.Errorf("%v. 철회가 남아야 한다", err)
	}
}

func TestABadUpdateIsRefused(t *testing.T) {
	service, _ := setUp(t)
	for name, update := range map[string]eligibility.Update{
		"사용자가 없다":  {Version: 1},
		"버전이 0 이다": {UserID: uuid.New()},
	} {
		if _, err := service.Apply(context.Background(), update); !errors.Is(err, eligibility.ErrInvalidUpdate) {
			t.Errorf("%s: %v", name, err)
		}
	}
}
