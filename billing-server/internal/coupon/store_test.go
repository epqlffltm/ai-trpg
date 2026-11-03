// billing-server/internal/coupon/store_test.go

// 쿠폰을 받고, 만들고, 멈추는 일을 테스트용 스키마에서 본다(#979).
// 테이블을 비우지 않으므로 테스트마다 새 코드와 새 사용자를 쓴다.
package coupon_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// freeTTL 은 테스트의 무료 크레딧의 기본 기한이다.
const freeTTL = 30 * 24 * time.Hour

// clock 은 테스트가 옮기는 시계다. 여러 고루틴이 함께 읽는다.
type clock struct {
	mu  sync.Mutex
	now time.Time
}

func (c *clock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *clock) advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

type fixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	clock    *clock
	services app.Services
	service  *coupon.Service
}

// setUp 은 테스트용 스키마에 붙는 서비스들을 만든다. 지금은 2026-11-10 03:00 UTC 다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	c := &clock{now: time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC)}
	rules := config.Rules{FreeCreditTTL: freeTTL, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NoProviders(), c.Now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	service := coupon.NewService(pool, c.Now, services.Wallet, services.Eligibility)
	return fixture{t: t, pool: pool, clock: c, services: services, service: service}
}

// verified 는 본인인증을 한 사용자를 만든다.
func (f fixture) verified() uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	update := eligibility.Update{UserID: user, Version: 1}
	if _, err := f.services.Eligibility.Apply(context.Background(), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return user
}

// newCode 는 겹치지 않는 코드다. 소문자로 돌려준다(넣을 때 대문자로 바뀌는지도 본다).
func newCode() string {
	return "t-" + strings.ReplaceAll(uuid.NewString(), "-", "")[:12]
}

// create 는 지금 열려 있는 쿠폰을 만든다. change 로 값을 바꾼다.
func (f fixture) create(change func(*coupon.Spec)) coupon.Coupon {
	f.t.Helper()
	now := f.clock.Now()
	spec := coupon.Spec{
		Code: newCode(), Silver: 300, StartsAt: now.Add(-time.Hour), EndsAt: now.Add(24 * time.Hour),
		CreatedBy: "test", Reason: "시험",
	}
	if change != nil {
		change(&spec)
	}
	made, err := f.service.Create(context.Background(), spec)
	if err != nil {
		f.t.Fatalf("쿠폰을 만들지 못했다: %v", err)
	}
	return made
}

func (f fixture) balance(user uuid.UUID) wallet.Balance {
	f.t.Helper()
	balance, err := f.services.Wallet.Balance(context.Background(), user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	return balance
}

func TestRedeemingGivesSilverOnceAndShowsAsCoupon(t *testing.T) {
	f := setUp(t)
	made := f.create(nil)
	user := f.verified()

	got, err := f.service.Redeem(context.Background(), user, "  "+strings.ToLower(made.Code)+" ")
	if err != nil {
		t.Fatalf("받지 못했다: %v", err)
	}
	if got.Code != made.Code || got.Silver != 300 || !got.ExpiresAt.Equal(f.clock.Now().Add(freeTTL)) {
		t.Fatalf("받은 것 = %+v", got)
	}
	if balance := f.balance(user); balance.Free != 300 || balance.Paid != 0 {
		t.Fatalf("잔액 = %+v, 실버 300 만 늘어야 한다", balance)
	}
	page, err := f.services.Wallet.Entries(context.Background(), user, 1<<62, 10)
	if err != nil || len(page.Entries) != 1 || page.Entries[0].Source != wallet.SourceCoupon {
		t.Fatalf("원장 = %+v, %v. 받은 줄 하나가 쿠폰이어야 한다", page.Entries, err)
	}

	_, err = f.service.Redeem(context.Background(), user, made.Code)
	if !errors.Is(err, coupon.ErrAlreadyRedeemed) {
		t.Fatalf("두 번째 = %v, ErrAlreadyRedeemed 여야 한다", err)
	}
	if balance := f.balance(user); balance.Free != 300 {
		t.Fatalf("두 번째 뒤 잔액 = %+v", balance)
	}
}

func TestTwoRequestsAtOnceGiveOnce(t *testing.T) {
	f := setUp(t)
	made := f.create(nil)
	user := f.verified()

	errs := redeemTogether(f, made.Code, []uuid.UUID{user, user, user})

	if succeeded(errs) != 1 || countIs(errs, coupon.ErrAlreadyRedeemed) != 2 {
		t.Fatalf("결과 = %v, 하나만 받고 둘은 ErrAlreadyRedeemed 여야 한다", errs)
	}
	if balance := f.balance(user); balance.Free != 300 {
		t.Fatalf("잔액 = %+v", balance)
	}
}

func TestTheLimitIsNeverExceededEvenAtOnce(t *testing.T) {
	f := setUp(t)
	made := f.create(func(spec *coupon.Spec) { spec.MaxRedemptions = 2 })
	users := []uuid.UUID{f.verified(), f.verified(), f.verified(), f.verified()}

	errs := redeemTogether(f, made.Code, users)

	if succeeded(errs) != 2 || countIs(errs, coupon.ErrExhausted) != 2 {
		t.Fatalf("결과 = %v, 둘만 받고 둘은 ErrExhausted 여야 한다", errs)
	}
	listed, err := f.service.List(context.Background(), 50)
	if err != nil {
		t.Fatal(err)
	}
	for _, one := range listed {
		if one.ID == made.ID && one.Redemptions != 2 {
			t.Fatalf("받은 사람의 수 = %d, 2 여야 한다", one.Redemptions)
		}
	}
}

func TestOutsideThePeriodOrStoppedCannotBeRedeemed(t *testing.T) {
	f := setUp(t)
	user := f.verified()
	now := f.clock.Now()
	later := f.create(func(spec *coupon.Spec) { spec.StartsAt, spec.EndsAt = now.Add(time.Hour), now.Add(2*time.Hour) })
	past := f.create(func(spec *coupon.Spec) { spec.StartsAt, spec.EndsAt = now.Add(-2*time.Hour), now })
	stopped := f.create(nil)
	if err := f.service.Stop(context.Background(), stopped.Code); err != nil {
		t.Fatal(err)
	}

	cases := []struct {
		code string
		want error
	}{{later.Code, coupon.ErrNotStarted}, {past.Code, coupon.ErrEnded}, {stopped.Code, coupon.ErrStopped}}
	for _, tc := range cases {
		if _, err := f.service.Redeem(context.Background(), user, tc.code); !errors.Is(err, tc.want) {
			t.Fatalf("%s = %v, %v 여야 한다", tc.code, err, tc.want)
		}
	}
	if balance := f.balance(user); balance.Free != 0 {
		t.Fatalf("잔액 = %+v, 받은 것이 없어야 한다", balance)
	}
}

func TestOnlyVerifiedPeopleRedeem(t *testing.T) {
	f := setUp(t)
	made := f.create(nil)

	_, err := f.service.Redeem(context.Background(), uuid.New(), made.Code)

	if !errors.Is(err, coupon.ErrVerificationRequired) {
		t.Fatalf("본인인증 전 = %v", err)
	}
}

func TestTooManyWrongCodesBlockUntilTheWindowEnds(t *testing.T) {
	f := setUp(t)
	made := f.create(nil)
	user := f.verified()
	for i := range coupon.MaxFailures {
		code := "NOPE-" + strings.ToUpper(uuid.NewString()[:8])
		if i%2 == 1 {
			code = "?" // 모양이 틀린 것도 센다
		}
		if _, err := f.service.Redeem(context.Background(), user, code); !errors.Is(err, coupon.ErrNotFound) {
			t.Fatalf("%d 번째 = %v, ErrNotFound 여야 한다", i+1, err)
		}
	}

	_, err := f.service.Redeem(context.Background(), user, made.Code)
	var blocked *coupon.TooManyAttemptsError
	if !errors.As(err, &blocked) || blocked.RetryAfter != coupon.FailureWindow {
		t.Fatalf("한도 뒤 = %v, 한 시간 기다리라는 TooManyAttemptsError 여야 한다", err)
	}
	if _, err := f.service.Redeem(context.Background(), f.verified(), made.Code); err != nil {
		t.Fatalf("다른 사람은 막히지 않아야 한다: %v", err)
	}

	f.clock.advance(coupon.FailureWindow)
	if _, err := f.service.Redeem(context.Background(), user, made.Code); err != nil {
		t.Fatalf("창이 끝난 뒤 = %v, 받아야 한다", err)
	}
}

func TestExistingCodesDoNotCountAsWrong(t *testing.T) {
	f := setUp(t)
	user := f.verified()
	stopped := f.create(nil)
	if err := f.service.Stop(context.Background(), stopped.Code); err != nil {
		t.Fatal(err)
	}
	for range coupon.MaxFailures + 1 {
		if _, err := f.service.Redeem(context.Background(), user, stopped.Code); !errors.Is(err, coupon.ErrStopped) {
			t.Fatalf("멈춘 쿠폰 = %v", err)
		}
	}

	if _, err := f.service.Redeem(context.Background(), user, f.create(nil).Code); err != nil {
		t.Fatalf("있는 코드를 여러 번 넣은 것은 틀린 시도가 아니다: %v", err)
	}
}

func TestACouponCanSetHowLongItsSilverLasts(t *testing.T) {
	f := setUp(t)
	made := f.create(func(spec *coupon.Spec) { spec.SilverDays = 7 })

	got, err := f.service.Redeem(context.Background(), f.verified(), made.Code)

	if err != nil || !got.ExpiresAt.Equal(f.clock.Now().Add(7*24*time.Hour)) {
		t.Fatalf("받은 것 = %+v, %v. 7일 뒤에 사라져야 한다", got, err)
	}
}

func TestCreatingAndStopping(t *testing.T) {
	f := setUp(t)
	made := f.create(nil)

	_, err := f.service.Create(context.Background(), coupon.Spec{
		Code: strings.ToLower(made.Code), Silver: 1, StartsAt: made.StartsAt, EndsAt: made.EndsAt, CreatedBy: "test", Reason: "같은 코드",
	})
	if !errors.Is(err, coupon.ErrCodeTaken) {
		t.Fatalf("같은 코드 = %v", err)
	}
	if _, err := f.service.Create(context.Background(), coupon.Spec{Code: newCode(), Silver: 0}); !errors.Is(err, coupon.ErrInvalidSpec) {
		t.Fatalf("틀린 값 = %v", err)
	}
	if err := f.service.Stop(context.Background(), made.Code); err != nil {
		t.Fatal(err)
	}
	if err := f.service.Stop(context.Background(), made.Code); err != nil {
		t.Fatalf("두 번 멈춰도 오류가 아니다: %v", err)
	}
	if err := f.service.Stop(context.Background(), newCode()); !errors.Is(err, coupon.ErrNotFound) {
		t.Fatalf("없는 코드 = %v", err)
	}
}

// redeemTogether 는 users 가 같은 코드를 한꺼번에 넣는다. 결과는 users 의 차례다.
func redeemTogether(f fixture, code string, users []uuid.UUID) []error {
	errs := make([]error, len(users))
	var start, done sync.WaitGroup
	start.Add(1)
	for i, user := range users {
		done.Add(1)
		go func() {
			defer done.Done()
			start.Wait()
			_, errs[i] = f.service.Redeem(context.Background(), user, code)
		}()
	}
	start.Done()
	done.Wait()
	return errs
}

func succeeded(errs []error) int {
	n := 0
	for _, err := range errs {
		if err == nil {
			n++
		}
	}
	return n
}

func countIs(errs []error, target error) int {
	n := 0
	for _, err := range errs {
		if errors.Is(err, target) {
			n++
		}
	}
	return n
}
