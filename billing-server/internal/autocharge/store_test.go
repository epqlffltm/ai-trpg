// billing-server/internal/autocharge/store_test.go
// 카드의 등록과 지우기, 자동 충전의 설정을 테스트용 스키마에서 본다(#980). 결제 대행사는 가짜(payment.Fake)다.
// 테이블을 비우지 않으므로 테스트마다 새 사용자를 쓴다.
package autocharge_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

type fixture struct {
	t           *testing.T
	pool        *pgxpool.Pool
	now         time.Time
	eligibility *eligibility.Service
	service     *autocharge.Service
}

// setUp 은 테스트용 스키마에 붙는 서비스를 만든다. 지금은 2026-11-10 03:00 UTC 다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	now := time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC)
	clock := func() time.Time { return now }
	checker := eligibility.NewService(pool, clock)
	return fixture{t: t, pool: pool, now: now, eligibility: checker,
		service: autocharge.NewService(pool, clock, payment.Fake{}, checker)}
}

// user 는 결제할 수 있는 사용자를 만든다. adultFrom 이 nil 이면 성년이다. 미성년자면 consent 가 보호자의 동의다.
func (f fixture) user(adultFrom *time.Time, consent bool) uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	update := eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: adultFrom, GuardianConsent: consent}
	if _, err := f.eligibility.Apply(context.Background(), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return user
}

func (f fixture) adult() uuid.UUID { return f.user(nil, false) }

// withCard 는 카드를 등록한 성년이다.
func (f fixture) withCard() uuid.UUID {
	f.t.Helper()
	user := f.adult()
	f.register(user)
	return user
}

func (f fixture) register(user uuid.UUID) autocharge.Card {
	f.t.Helper()
	ctx := context.Background()
	key, err := f.service.CustomerKey(ctx, user)
	if err != nil {
		f.t.Fatalf("고객 키를 만들지 못했다: %v", err)
	}
	card, err := f.service.RegisterCard(ctx, user, payment.FakeCardApproved+user.String(), key)
	if err != nil {
		f.t.Fatalf("카드를 등록하지 못했다: %v", err)
	}
	return card
}

func (f fixture) billingKey(user uuid.UUID) string {
	f.t.Helper()
	var key string
	if err := f.pool.QueryRow(context.Background(), "SELECT billing_key FROM payment_cards WHERE user_id = $1", user).Scan(&key); err != nil {
		return ""
	}
	return key
}

func TestTheCustomerKeyIsMadeOnceAndIsNotThePublicID(t *testing.T) {
	f := setUp(t)
	user := f.adult()
	ctx := context.Background()

	keys := make([]uuid.UUID, 8)
	var wg sync.WaitGroup
	for i := range keys {
		wg.Add(1)
		go func() {
			defer wg.Done()
			keys[i], _ = f.service.CustomerKey(ctx, user)
		}()
	}
	wg.Wait()

	for _, key := range keys {
		if key == uuid.Nil || key != keys[0] {
			t.Fatalf("고객 키 = %v. 하나여야 한다", keys)
		}
	}
	if keys[0] == user {
		t.Errorf("공개 ID 를 고객 키로 썼다")
	}
}

func TestACardIsRegisteredAndShownWithoutTheBillingKey(t *testing.T) {
	f := setUp(t)
	user := f.adult()

	card := f.register(user)
	got, err := f.service.Get(context.Background(), user)

	if card.Number != "43301234****123*" || card.IssuerCode != "4V" || !card.RegisteredAt.Equal(f.now) {
		t.Errorf("카드 = %+v", card)
	}
	if err != nil || got.Card == nil || *got.Card != card || got.Settings != nil {
		t.Errorf("읽은 것 = %+v, %v", got, err)
	}
	if f.billingKey(user) != "fake_billing_"+user.String() {
		t.Errorf("빌링키 = %q", f.billingKey(user))
	}
}

func TestRegisteringAgainReplacesTheCard(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	key, _ := f.service.CustomerKey(ctx, user)

	if _, err := f.service.RegisterCard(ctx, user, payment.FakeCardApproved+"second", key); err != nil {
		t.Fatalf("다시 등록하지 못했다: %v", err)
	}

	if f.billingKey(user) != "fake_billing_second" {
		t.Errorf("빌링키 = %q", f.billingKey(user))
	}
}

func TestRegistrationNeedsTheirOwnCustomerKey(t *testing.T) {
	f := setUp(t)
	user, other := f.adult(), f.adult()
	ctx := context.Background()
	otherKey, _ := f.service.CustomerKey(ctx, other)

	// 고객 키를 만든 적이 없다
	_, never := f.service.RegisterCard(ctx, user, payment.FakeCardApproved+"x", uuid.New())
	f.service.CustomerKey(ctx, user)
	// 남의 고객 키다
	_, theirs := f.service.RegisterCard(ctx, user, payment.FakeCardApproved+"x", otherKey)

	if !errors.Is(never, autocharge.ErrCustomerKeyMismatch) || !errors.Is(theirs, autocharge.ErrCustomerKeyMismatch) {
		t.Errorf("오류 = %v, %v", never, theirs)
	}
	if f.billingKey(user) != "" {
		t.Errorf("카드를 적었다")
	}
}

func TestARefusedOrLostRegistrationLeavesNoCard(t *testing.T) {
	f := setUp(t)
	user := f.adult()
	ctx := context.Background()
	key, _ := f.service.CustomerKey(ctx, user)

	_, refused := f.service.RegisterCard(ctx, user, payment.FakeCardRefused+"x", key)
	_, lost := f.service.RegisterCard(ctx, user, payment.FakeCardLost+"x", key)
	_, empty := f.service.RegisterCard(ctx, user, "", key)

	var refusal *payment.RefusedError
	if !errors.As(refused, &refusal) || !errors.Is(lost, autocharge.ErrIssuerUnavailable) || !errors.Is(empty, autocharge.ErrInvalidAuthKey) {
		t.Errorf("오류 = %v, %v, %v", refused, lost, empty)
	}
	if f.billingKey(user) != "" {
		t.Errorf("카드를 적었다")
	}
}

func TestTurningOnNeedsACard(t *testing.T) {
	f := setUp(t)
	user := f.adult()

	_, err := f.service.Update(context.Background(), user, validSettings())

	if !errors.Is(err, autocharge.ErrNoCard) {
		t.Errorf("오류 = %v", err)
	}
	if got, _ := f.service.Get(context.Background(), user); got.Settings != nil {
		t.Errorf("설정을 적었다: %+v", got.Settings)
	}
}

func TestSettingsAreSavedAndCanBeTurnedOff(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()

	on, onErr := f.service.Update(ctx, user, validSettings())
	off := validSettings()
	off.Enabled = false
	off.Threshold = 0
	turnedOff, offErr := f.service.Update(ctx, user, off)

	if onErr != nil || on.Settings == nil || *on.Settings != validSettings() || on.Card == nil {
		t.Errorf("켠 것 = %+v, %v", on, onErr)
	}
	if offErr != nil || turnedOff.Settings == nil || *turnedOff.Settings != off {
		t.Errorf("끈 것 = %+v, %v", turnedOff, offErr)
	}
}

func TestTurningOffNeedsNothing(t *testing.T) {
	// 카드도 결제 자격도 없어도 끈 설정은 적을 수 있다
	f := setUp(t)
	off := validSettings()
	off.Enabled = false

	if _, err := f.service.Update(context.Background(), uuid.New(), off); err != nil {
		t.Errorf("끄지 못했다: %v", err)
	}
}

func TestAMinorNeedsTheGuardian(t *testing.T) {
	f := setUp(t)
	adultFrom := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	without, with := f.user(&adultFrom, false), f.user(&adultFrom, true)
	f.register(without)
	f.register(with)
	ctx := context.Background()

	_, refused := f.service.Update(ctx, without, validSettings())
	_, allowed := f.service.Update(ctx, with, validSettings())

	if !errors.Is(refused, eligibility.ErrGuardianConsentRequired) {
		t.Errorf("보호자 동의 없이 = %v", refused)
	}
	if allowed != nil {
		t.Errorf("보호자 동의가 있는데 = %v", allowed)
	}
}

func TestWithoutIdentityItCannotBeTurnedOn(t *testing.T) {
	f := setUp(t)

	_, err := f.service.Update(context.Background(), uuid.New(), validSettings())

	if !errors.Is(err, eligibility.ErrVerificationRequired) {
		t.Errorf("오류 = %v", err)
	}
}

func TestRemovingTheCardTurnsItOff(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	if _, err := f.service.Update(ctx, user, validSettings()); err != nil {
		t.Fatalf("켜지 못했다: %v", err)
	}

	removeErr := f.service.RemoveCard(ctx, user)
	again := f.service.RemoveCard(ctx, user)
	got, _ := f.service.Get(ctx, user)

	if removeErr != nil || again != nil {
		t.Errorf("오류 = %v, %v", removeErr, again)
	}
	if got.Card != nil || got.Settings == nil || got.Settings.Enabled {
		t.Errorf("지운 뒤 = %+v", got)
	}
}

func TestTurningOnAgainClearsTheFailures(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	f.service.Update(ctx, user, validSettings())
	if _, err := f.pool.Exec(ctx, "UPDATE auto_charge_settings SET consecutive_failures = 3, enabled = false WHERE user_id = $1", user); err != nil {
		t.Fatalf("실패를 적지 못했다: %v", err)
	}
	off := validSettings()
	off.Enabled = false

	stillOff, _ := f.service.Update(ctx, user, off)
	on, _ := f.service.Update(ctx, user, validSettings())

	if stillOff.ConsecutiveFailures != 3 || on.ConsecutiveFailures != 0 {
		t.Errorf("끈 채로 = %d, 켠 뒤 = %d", stillOff.ConsecutiveFailures, on.ConsecutiveFailures)
	}
}

func TestEraseRemovesEverything(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	f.service.Update(ctx, user, validSettings())

	erased, err := f.service.Erase(ctx, user)
	again, againErr := f.service.Erase(ctx, user)
	got, _ := f.service.Get(ctx, user)
	var customers int
	f.pool.QueryRow(ctx, "SELECT count(*) FROM billing_customers WHERE user_id = $1", user).Scan(&customers)

	if err != nil || !erased || againErr != nil || again {
		t.Errorf("지우기 = %v %v, 다시 = %v %v", erased, err, again, againErr)
	}
	if got.Card != nil || got.Settings != nil || customers != 0 {
		t.Errorf("남은 것 = %+v, 고객 %d", got, customers)
	}
}
