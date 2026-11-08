// billing-server/internal/autocharge/store_test.go
// 카드의 등록과 지우기, 자동 충전의 설정을 테스트용 스키마에서 본다(#980). 결제 대행사는 가짜(payment.Fake)다.
// 테이블을 비우지 않으므로 테스트마다 새 사용자를 쓴다.
package autocharge_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
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

	_, err := f.service.Update(context.Background(), user, validSettings(), autocharge.TermsVersion)

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

	on, onErr := f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion)
	off := validSettings()
	off.Enabled = false
	off.Threshold = 0
	turnedOff, offErr := f.service.Update(ctx, user, off, 0)

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

	if _, err := f.service.Update(context.Background(), uuid.New(), off, 0); err != nil {
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

	_, refused := f.service.Update(ctx, without, validSettings(), autocharge.TermsVersion)
	_, allowed := f.service.Update(ctx, with, validSettings(), autocharge.TermsVersion)

	if !errors.Is(refused, eligibility.ErrGuardianConsentRequired) {
		t.Errorf("보호자 동의 없이 = %v", refused)
	}
	if allowed != nil {
		t.Errorf("보호자 동의가 있는데 = %v", allowed)
	}
}

func TestWithoutIdentityItCannotBeTurnedOn(t *testing.T) {
	f := setUp(t)

	_, err := f.service.Update(context.Background(), uuid.New(), validSettings(), autocharge.TermsVersion)

	if !errors.Is(err, eligibility.ErrVerificationRequired) {
		t.Errorf("오류 = %v", err)
	}
}

func TestRemovingTheCardTurnsItOff(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	if _, err := f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion); err != nil {
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
	f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion)
	if _, err := f.pool.Exec(ctx, "UPDATE auto_charge_settings SET consecutive_failures = 3, enabled = false WHERE user_id = $1", user); err != nil {
		t.Fatalf("실패를 적지 못했다: %v", err)
	}
	off := validSettings()
	off.Enabled = false

	stillOff, _ := f.service.Update(ctx, user, off, 0)
	on, _ := f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion)

	if stillOff.ConsecutiveFailures != 3 || on.ConsecutiveFailures != 0 {
		t.Errorf("끈 채로 = %d, 켠 뒤 = %d", stillOff.ConsecutiveFailures, on.ConsecutiveFailures)
	}
}

func TestEraseRemovesEverything(t *testing.T) {
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion)

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

func TestTurningOnNeedsTheCurrentTerms(t *testing.T) {
	// 켜려면 자동 결제 동의의 지금의 판에 동의해야 한다. 끄는 것은 동의가 필요 없다
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()

	_, missing := f.service.Update(ctx, user, validSettings(), 0)
	_, outdated := f.service.Update(ctx, user, validSettings(), autocharge.TermsVersion+1)
	after, _ := f.service.Get(ctx, user)
	off := validSettings()
	off.Enabled = false
	_, offErr := f.service.Update(ctx, user, off, 0)

	if !errors.Is(missing, autocharge.ErrTermsRequired) || !errors.Is(outdated, autocharge.ErrTermsOutdated) {
		t.Errorf("동의 없음 = %v, 옛 판 = %v", missing, outdated)
	}
	if after.Settings != nil || after.AgreedTermsVersion != 0 || f.consents(user) != 0 {
		t.Errorf("거절했는데 적었다: %+v, 동의 %d 줄", after, f.consents(user))
	}
	if offErr != nil || f.consents(user) != 0 {
		t.Errorf("끄기 = %v, 동의 %d 줄. 끄기는 동의를 적지 않는다", offErr, f.consents(user))
	}
}

func TestTurningOnRecordsTheConsentWithItsConditions(t *testing.T) {
	// 켜는 설정을 적을 때마다 판과 조건을 한 줄씩 쌓는다. 탈퇴해도 남는다
	f := setUp(t)
	user := f.withCard()
	ctx := context.Background()
	first := validSettings()
	second := validSettings()
	second.Threshold, second.ProductID, second.MonthlyLimit = 300, "credits-1000", 10_000

	on, err := f.service.Update(ctx, user, first, autocharge.TermsVersion)
	if err != nil {
		t.Fatalf("켜지 못했다: %v", err)
	}
	if _, err := f.service.Update(ctx, user, second, autocharge.TermsVersion); err != nil {
		t.Fatalf("다시 적지 못했다: %v", err)
	}
	if _, err := f.service.Erase(ctx, user); err != nil {
		t.Fatalf("지우지 못했다: %v", err)
	}

	if on.AgreedTermsVersion != autocharge.TermsVersion {
		t.Errorf("동의한 판 = %d", on.AgreedTermsVersion)
	}
	rows, err := f.pool.Query(ctx, `SELECT terms_version, threshold, product_id, price, monthly_limit, agreed_at
		FROM auto_charge_consents WHERE user_id = $1 ORDER BY id`, user)
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	defer rows.Close()
	var got []string
	for rows.Next() {
		var version int
		var threshold, price, limit int64
		var product string
		var at time.Time
		if err := rows.Scan(&version, &threshold, &product, &price, &limit, &at); err != nil {
			t.Fatalf("읽지 못했다: %v", err)
		}
		if !at.Equal(f.now) {
			t.Errorf("동의한 때 = %v, 기대 = %v", at, f.now)
		}
		got = append(got, fmt.Sprintf("%d:%d:%s:%d:%d", version, threshold, product, price, limit))
	}
	want := []string{
		fmt.Sprintf("%d:%d:%s:5000:%d", autocharge.TermsVersion, first.Threshold, first.ProductID, first.MonthlyLimit),
		fmt.Sprintf("%d:300:credits-1000:1000:10000", autocharge.TermsVersion),
	}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("동의의 줄 = %v, 기대 = %v", got, want)
	}
}

// consents 는 그 사람의 자동 결제 동의의 줄 수다.
func (f fixture) consents(user uuid.UUID) int {
	f.t.Helper()
	var count int
	if err := f.pool.QueryRow(context.Background(), "SELECT count(*) FROM auto_charge_consents WHERE user_id = $1", user).Scan(&count); err != nil {
		f.t.Fatalf("읽지 못했다: %v", err)
	}
	return count
}
