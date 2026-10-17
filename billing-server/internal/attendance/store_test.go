// billing-server/internal/attendance/store_test.go

package attendance_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

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

func (c *clock) set(now time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = now
}

// nextDay 는 시계를 하루 뒤로 옮긴다.
func (c *clock) nextDay() { c.set(c.Now().AddDate(0, 0, 1)) }

// fixedRoll 은 늘 n 을 고르는 상자다.
func fixedRoll(n int) attendance.Roll {
	return func() (int, error) { return n, nil }
}

type fixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	clock    *clock
	services app.Services
	service  *attendance.Service
}

// setUp 은 테스트용 스키마에 붙는 서비스들을 만든다. 지금은 2026-10-18 03:00 UTC(한국 12시)다.
// roll 은 상자의 수다. 9999 면 용의 보물이다.
func setUp(t *testing.T, roll int) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	c := &clock{now: time.Date(2026, 10, 18, 3, 0, 0, 0, time.UTC)}
	rules := config.Rules{FreeCreditTTL: 30 * 24 * time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NoProviders(), c.Now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	service, err := attendance.NewService(pool, c.Now, services.Wallet, services.Eligibility,
		attendance.Options{Roll: fixedRoll(roll)})
	if err != nil {
		t.Fatalf("출석을 만들지 못했다: %v", err)
	}
	return fixture{t: t, pool: pool, clock: c, services: services, service: service}
}

// verified 는 본인인증을 한 사용자를 만든다. 미성년자다(출석은 나이를 보지 않는다).
func (f fixture) verified() uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	adultFrom := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	update := eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: &adultFrom}
	if _, err := f.services.Eligibility.Apply(context.Background(), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return user
}

func (f fixture) claim(user uuid.UUID) attendance.Claim {
	f.t.Helper()
	claim, err := f.service.Claim(context.Background(), user)
	if err != nil {
		f.t.Fatalf("출석하지 못했다: %v", err)
	}
	return claim
}

// free 는 그 사용자의 실버다.
func (f fixture) free(user uuid.UUID) credit.Amount {
	f.t.Helper()
	balance, err := f.services.Wallet.Balance(context.Background(), user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	return balance.Free
}

// rows 는 그 사용자의 출석 줄 수다.
func (f fixture) rows(user uuid.UUID) int {
	f.t.Helper()
	var n int
	if err := f.pool.QueryRow(context.Background(),
		"SELECT count(*) FROM attendance_claims WHERE user_id = $1", user).Scan(&n); err != nil {
		f.t.Fatalf("출석 줄을 세지 못했다: %v", err)
	}
	return n
}

func TestAnUnverifiedUserCannotClaim(t *testing.T) {
	f := setUp(t, 0)
	user := uuid.New()
	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrVerificationRequired) {
		t.Fatalf("ErrVerificationRequired 이어야 하는데 %v 다", err)
	}
	if f.rows(user) != 0 || f.free(user) != 0 {
		t.Fatal("아무것도 적히지 않아야 한다")
	}
	status, err := f.service.Status(context.Background(), user)
	if err != nil || status.Verified || status.Claimed || status.CycleDay != 1 {
		t.Fatalf("본인인증 전의 상태가 틀렸다: %+v, %v", status, err)
	}
}

func TestTheFirstClaimGivesDayOne(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	claim := f.claim(user)
	if claim.CycleDay != 1 || claim.Silver != 140 || claim.Chest != nil {
		t.Fatalf("1일째, 140 실버, 상자 없음이어야 한다: %+v", claim)
	}
	if !claim.Day.Equal(time.Date(2026, 10, 18, 0, 0, 0, 0, time.UTC)) {
		t.Fatalf("한국 날짜가 틀렸다: %s", claim.Day)
	}
	if want := f.clock.Now().Add(30 * 24 * time.Hour); !claim.ExpiresAt.Equal(want) {
		t.Fatalf("실버는 30일 뒤에 사라져야 한다: %s", claim.ExpiresAt)
	}
	if f.free(user) != 140 {
		t.Fatalf("실버가 140 이어야 하는데 %s 다", f.free(user))
	}
}

func TestASecondClaimOnTheSameDayChangesNothing(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	f.claim(user)
	// 같은 한국 날짜의 밤 11시 59분
	f.clock.set(time.Date(2026, 10, 18, 14, 59, 59, 0, time.UTC))
	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrAlreadyClaimed) {
		t.Fatalf("ErrAlreadyClaimed 이어야 하는데 %v 다", err)
	}
	if f.free(user) != 140 || f.rows(user) != 1 {
		t.Fatal("두 번째는 아무것도 바꾸지 않아야 한다")
	}
}

func TestTheDayChangesAtKoreanMidnight(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	f.clock.set(time.Date(2026, 10, 18, 14, 59, 59, 0, time.UTC)) // 한국 10월 18일 23:59:59
	f.claim(user)
	f.clock.set(time.Date(2026, 10, 18, 15, 0, 0, 0, time.UTC)) // 한국 10월 19일 0시. UTC 로는 아직 18일이다
	claim := f.claim(user)
	if claim.CycleDay != 2 || !claim.Day.Equal(time.Date(2026, 10, 19, 0, 0, 0, 0, time.UTC)) {
		t.Fatalf("한국 자정이 지나면 다음 날, 2일째여야 한다: %+v", claim)
	}
}

func TestSevenDaysInARowOpenTheChest(t *testing.T) {
	f := setUp(t, 9999) // 용의 보물
	user := f.verified()
	var last attendance.Claim
	for range 7 {
		last = f.claim(user)
		f.clock.nextDay()
	}
	if last.CycleDay != 7 || last.Silver != 260 || last.Chest == nil {
		t.Fatalf("7일째에 260 실버와 상자를 받아야 한다: %+v", last)
	}
	if last.Chest.Table != "v1" || last.Chest.Outcome.ID != "dragon_hoard" || last.Chest.Outcome.Silver != 5000 {
		t.Fatalf("v1 의 용의 보물이어야 한다: %+v", last.Chest)
	}
	// 1,400(하루 양의 합) + 5,000(상자)
	if f.free(user) != 6400 {
		t.Fatalf("실버가 6400 이어야 하는데 %s 다", f.free(user))
	}
	var table, outcome string
	var silver int64
	err := f.pool.QueryRow(context.Background(),
		"SELECT chest_table, chest_outcome, chest_silver FROM attendance_claims WHERE user_id = $1 AND cycle_day = 7", user,
	).Scan(&table, &outcome, &silver)
	if err != nil || table != "v1" || outcome != "dragon_hoard" || silver != 5000 {
		t.Fatalf("상자의 결과가 기록에 남아야 한다: %s %s %d, %v", table, outcome, silver, err)
	}
	if next := f.claim(user); next.CycleDay != 1 || next.Chest != nil {
		t.Fatalf("7일째 다음 날은 1일째여야 한다: %+v", next)
	}
}

func TestAMimicBiteGivesNoChestSilver(t *testing.T) {
	f := setUp(t, 0) // 꽝
	user := f.verified()
	var last attendance.Claim
	for range 7 {
		last = f.claim(user)
		f.clock.nextDay()
	}
	if last.Chest == nil || last.Chest.Outcome.ID != "mimic_bite" {
		t.Fatalf("꽝이어야 한다: %+v", last.Chest)
	}
	if f.free(user) != 1400 {
		t.Fatalf("꽝이면 하루 양만 받는다. 1400 이어야 하는데 %s 다", f.free(user))
	}
	var silver int64
	if err := f.pool.QueryRow(context.Background(),
		"SELECT chest_silver FROM attendance_claims WHERE user_id = $1 AND cycle_day = 7", user).Scan(&silver); err != nil || silver != 0 {
		t.Fatalf("꽝도 기록에 0 으로 남아야 한다: %d, %v", silver, err)
	}
}

func TestMissingADayStartsTheCycleOver(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	f.claim(user)
	f.clock.nextDay()
	f.claim(user)
	f.clock.nextDay()
	f.clock.nextDay() // 하루 빠졌다
	if claim := f.claim(user); claim.CycleDay != 1 || claim.Silver != 140 {
		t.Fatalf("하루 빠지면 1일째, 140 실버여야 한다: %+v", claim)
	}
}

func TestAClockMovedBackDoesNotGiveAnotherClaim(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	f.clock.nextDay()
	f.claim(user)
	// 서버의 시계가 하루 뒤로 돌아갔다. 이미 더 늦은 날에 받았으니 받지 않는다
	f.clock.set(time.Date(2026, 10, 18, 3, 0, 0, 0, time.UTC))
	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrAlreadyClaimed) {
		t.Fatalf("ErrAlreadyClaimed 이어야 하는데 %v 다", err)
	}
	if f.rows(user) != 1 || f.free(user) != 140 {
		t.Fatal("아무것도 더 적히지 않아야 한다")
	}
}

func TestStatusShowsTodaysClaim(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	f.claim(user)
	f.clock.nextDay()
	before, err := f.service.Status(context.Background(), user)
	if err != nil || !before.Verified || before.Claimed || before.CycleDay != 2 || before.Silver != 160 || before.Chest {
		t.Fatalf("받기 전에는 2일째, 160 실버를 보여야 한다: %+v, %v", before, err)
	}
	f.claim(user)
	after, err := f.service.Status(context.Background(), user)
	if err != nil || !after.Claimed || after.CycleDay != 2 || after.Silver != 160 {
		t.Fatalf("받은 뒤에는 받은 것을 보여야 한다: %+v, %v", after, err)
	}
}

func TestStatusShowsTheChestDay(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	for range 6 {
		f.claim(user)
		f.clock.nextDay()
	}
	status, err := f.service.Status(context.Background(), user)
	if err != nil || status.CycleDay != 7 || !status.Chest || status.Silver != 260 {
		t.Fatalf("7일째에는 상자를 연다고 보여야 한다: %+v, %v", status, err)
	}
	f.claim(user)
	after, err := f.service.Status(context.Background(), user)
	if err != nil || !after.Claimed || !after.Chest {
		t.Fatalf("상자를 연 날에는 받은 뒤에도 상자를 보여야 한다: %+v, %v", after, err)
	}
}

func TestConcurrentClaimsGiveOnce(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	const callers = 8
	errs := make(chan error, callers)
	var wg sync.WaitGroup
	for range callers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := f.service.Claim(context.Background(), user)
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	succeeded := 0
	for err := range errs {
		switch {
		case err == nil:
			succeeded++
		case !errors.Is(err, attendance.ErrAlreadyClaimed):
			t.Fatalf("이미 받았다는 오류만 나야 하는데 %v 다", err)
		}
	}
	if succeeded != 1 || f.free(user) != 140 || f.rows(user) != 1 {
		t.Fatalf("한 번만 받아야 한다: 성공 %d, 실버 %s, 줄 %d", succeeded, f.free(user), f.rows(user))
	}
}

func TestAnExistingGrantRollsTheClaimBack(t *testing.T) {
	f := setUp(t, 0)
	user := f.verified()
	// 오늘의 이름으로 이미 지급이 있다(기록이 지워졌거나 손으로 줬다)
	key := attendance.GrantKey(time.Date(2026, 10, 18, 0, 0, 0, 0, time.UTC))
	if _, err := f.services.Wallet.GrantFreeOnce(context.Background(), user, 10, key); err != nil {
		t.Fatalf("지급을 만들지 못했다: %v", err)
	}
	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrAlreadyClaimed) {
		t.Fatalf("ErrAlreadyClaimed 이어야 하는데 %v 다", err)
	}
	if f.rows(user) != 0 || f.free(user) != 10 {
		t.Fatalf("출석의 줄도 되돌려야 한다: 줄 %d, 실버 %s", f.rows(user), f.free(user))
	}
}

func TestAChestGrantFailureRollsEverythingBack(t *testing.T) {
	f := setUp(t, 9999)
	user := f.verified()
	for range 6 {
		f.claim(user)
		f.clock.nextDay()
	}
	key := attendance.ChestGrantKey(eligibility.KoreanDate(f.clock.Now()))
	if _, err := f.services.Wallet.GrantFreeOnce(context.Background(), user, 1, key); err != nil {
		t.Fatalf("지급을 만들지 못했다: %v", err)
	}
	before := f.free(user)
	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrAlreadyClaimed) {
		t.Fatalf("ErrAlreadyClaimed 이어야 하는데 %v 다", err)
	}
	if f.rows(user) != 6 || f.free(user) != before {
		t.Fatalf("7일째의 하루 양과 줄도 되돌려야 한다: 줄 %d, 실버 %s(전 %s)", f.rows(user), f.free(user), before)
	}
}

func TestARollFailureRollsTheClaimBack(t *testing.T) {
	pool := testenv.Pool(t)
	c := &clock{now: time.Date(2026, 10, 18, 3, 0, 0, 0, time.UTC)}
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NoProviders(), c.Now)
	if err != nil {
		t.Fatal(err)
	}
	broken := errors.New("난수를 고르지 못했다")
	service, err := attendance.NewService(pool, c.Now, services.Wallet, services.Eligibility,
		attendance.Options{Schedule: attendance.Schedule{50}, Roll: func() (int, error) { return 0, broken }})
	if err != nil {
		t.Fatal(err)
	}
	f := fixture{t: t, pool: pool, clock: c, services: services, service: service}
	user := f.verified()
	// 주기가 하루라 첫날이 곧 상자를 여는 날이다
	if _, err := service.Claim(context.Background(), user); !errors.Is(err, broken) {
		t.Fatalf("난수의 오류가 나와야 하는데 %v 다", err)
	}
	if f.rows(user) != 0 || f.free(user) != 0 {
		t.Fatal("아무것도 적히지 않아야 한다")
	}
}

func TestABadScheduleStopsTheService(t *testing.T) {
	_, err := attendance.NewService(nil, time.Now, nil, nil, attendance.Options{Schedule: attendance.Schedule{0}})
	if !errors.Is(err, attendance.ErrInvalidSchedule) {
		t.Fatalf("ErrInvalidSchedule 이어야 하는데 %v 다", err)
	}
	bad := attendance.ChestTable{Version: "v9", Outcomes: []attendance.Outcome{{ID: "a", Chance: 1}}}
	_, err = attendance.NewService(nil, time.Now, nil, nil, attendance.Options{Chest: &bad})
	if !errors.Is(err, attendance.ErrInvalidChest) {
		t.Fatalf("ErrInvalidChest 이어야 하는데 %v 다", err)
	}
}
