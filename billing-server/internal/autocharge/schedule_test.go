// billing-server/internal/autocharge/schedule_test.go
// 날짜 기준의 자동 충전(#1167)을 테스트용 스키마에서 본다. 그날(한국 날짜) 한 번만 사는지, 다른 날에는 사지 않는지,
// 그날이 지나면 보내지 않는지, 방식을 바꾸면 적어 둔 일을 보내지 않는지, 동의에 방식과 날이 적히는지 본다.
// 시계는 2026-11-10 03:00 UTC(한국 12:00, 10일)에서 시작한다(setUpCharging). 테스트마다 새 사용자를 쓰고,
// 끝나면 끈다. 켜 둔 채 두면 다른 테스트의 바퀴가 그 사람의 일을 적는다(테이블을 비우지 않는다).
package autocharge_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// today 는 시계가 시작하는 날(한국 날짜의 10일)이다.
const today = 10

// enableDate 는 marks 를 넣은 카드를 등록하고 매달 day 에 1,000 골드를 사도록 켠다(한 달 30,000 원). 끝나면 끈다.
func (f chargeFixture) enableDate(day int, marks string) {
	f.t.Helper()
	ctx := context.Background()
	key, err := f.service.CustomerKey(ctx, f.user)
	if err != nil {
		f.t.Fatalf("고객 키를 만들지 못했다: %v", err)
	}
	if _, err := f.service.RegisterCard(ctx, f.user, payment.FakeCardApproved+uuid.NewString()+marks, key); err != nil {
		f.t.Fatalf("카드를 등록하지 못했다: %v", err)
	}
	f.dateSettings(true, day)
	f.t.Cleanup(func() { f.dateSettings(false, day) })
}

// dateSettings 는 날짜 기준의 설정을 적는다.
func (f chargeFixture) dateSettings(enabled bool, day int) {
	f.t.Helper()
	if _, err := f.service.Update(context.Background(), f.user, autocharge.Settings{
		Enabled: enabled, Mode: autocharge.ModeDate, Threshold: threshold, ChargeDay: day,
		ProductID: "credits-1000", MonthlyLimit: 30_000,
	}, autocharge.TermsVersion); err != nil {
		f.t.Fatalf("설정을 적지 못했다: %v", err)
	}
}

func TestKoreaDateIsTheDayInKorea(t *testing.T) {
	for name, tc := range map[string]struct {
		at   time.Time
		want time.Time
	}{
		"한국의 자정":      {time.Date(2026, 11, 9, 15, 0, 0, 0, time.UTC), time.Date(2026, 11, 10, 0, 0, 0, 0, time.UTC)},
		"한국의 자정 1초 전": {time.Date(2026, 11, 9, 14, 59, 59, 0, time.UTC), time.Date(2026, 11, 9, 0, 0, 0, 0, time.UTC)},
		"한국의 낮":       {time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC), time.Date(2026, 11, 10, 0, 0, 0, 0, time.UTC)},
	} {
		if got := autocharge.KoreaDate(tc.at); !got.Equal(tc.want) {
			t.Errorf("%s: %v", name, got)
		}
	}
	day := time.Date(2026, 11, 10, 0, 0, 0, 0, time.UTC)
	if autocharge.PastChargeDate(day, time.Date(2026, 11, 10, 14, 59, 59, 0, time.UTC)) {
		t.Errorf("그날의 마지막 1초를 지난 것으로 봤다")
	}
	if !autocharge.PastChargeDate(day, time.Date(2026, 11, 10, 15, 0, 0, 0, time.UTC)) {
		t.Errorf("다음 날을 그날로 봤다")
	}
}

func TestTheDayMustBeAnEveryMonthDay(t *testing.T) {
	date := func(day int) autocharge.Settings {
		settings := validSettings()
		settings.Mode, settings.ChargeDay = autocharge.ModeDate, day
		return settings
	}
	for _, day := range []int{1, autocharge.MaxChargeDay} {
		if err := date(day).Validate(); err != nil {
			t.Errorf("%d 일을 거절했다: %v", day, err)
		}
	}
	for name, settings := range map[string]autocharge.Settings{
		"날을 고르지 않았다": date(0),
		"29일":        date(29),
		"31일":        date(31),
		"음수":         date(-1),
		"모르는 방식":     func() autocharge.Settings { s := validSettings(); s.Mode = "weekly"; return s }(),
		"방식이 없다":     func() autocharge.Settings { s := validSettings(); s.Mode = ""; return s }(),
	} {
		if err := settings.Validate(); !errors.Is(err, autocharge.ErrInvalidSettings) {
			t.Errorf("%s: 오류 = %v", name, err)
		}
	}
	balance := validSettings()
	balance.ChargeDay = 5
	if err := balance.Validate(); err != nil {
		t.Errorf("잔액 기준이 남겨 둔 날을 거절했다: %v", err)
	}
}

func TestOnTheDayItBuysOnceEvenIfTheWorkerRunsAgain(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today, "")

	first := f.round()
	f.clock.advance(time.Hour)
	f.round()
	f.clock.advance(10 * time.Hour) // 한국 23:00. 아직 그날이다
	f.round()

	if first.Queued < 1 || !equal(f.requests(), "paid::") || f.gold() != 1_000 {
		t.Errorf("결과 = %+v, 일 = %v, 골드 = %s", first, f.requests(), f.gold())
	}
	var chargeDate time.Time
	f.pool.QueryRow(context.Background(), "SELECT charge_date FROM auto_charge_requests WHERE user_id = $1", f.user).Scan(&chargeDate)
	if !chargeDate.Equal(time.Date(2026, 11, 10, 0, 0, 0, 0, time.UTC)) {
		t.Errorf("그날 = %v", chargeDate)
	}
}

func TestOnOtherDaysItDoesNotBuy(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today+1, "")

	f.round()

	if len(f.requests()) != 0 {
		t.Errorf("다른 날에 적었다: %v", f.requests())
	}
	f.clock.advance(13 * time.Hour) // 한국 01:00, 11일
	f.round()
	if !equal(f.requests(), "paid::") {
		t.Errorf("그날이 되었는데 = %v", f.requests())
	}
}

func TestDateModeIgnoresDrops(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today+1, "")
	f.deposit(120)

	f.spend() // 70: 잔액 기준이었으면 떨어진 것이다
	f.spend()

	if len(f.requests()) != 0 {
		t.Errorf("떨어진 것으로 적었다: %v", f.requests())
	}
}

func TestTurningItOnAgainOnTheDayDoesNotBuyAgain(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today, payment.FakeChargeDeclined)
	f.round()

	f.dateSettings(false, today)
	f.dateSettings(true, today)
	f.round()

	if !equal(f.requests(), "declined::"+payment.FakeCodeChargeDeclined) {
		t.Errorf("일 = %v. 그날은 한 번이어야 한다", f.requests())
	}
}

func TestQueueingTwiceOnTheSameDayWritesOne(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today, "")
	ctx := context.Background()

	if _, err := f.service.QueueScheduled(ctx, f.clock.Now(), 1_000); err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}
	again, err := f.service.QueueScheduled(ctx, f.clock.Now().Add(time.Minute), 1_000)

	if err != nil || len(f.requests()) != 1 {
		t.Errorf("두 번째 = %d %v, 일 = %v", again, err, f.requests())
	}
}

func TestAQueuedDateChargeIsNotSentAfterTheDay(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today, "")
	if _, err := f.service.QueueScheduled(context.Background(), f.clock.Now(), 1_000); err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}

	f.clock.advance(12 * time.Hour) // 한국 00:00, 11일. 결제 작업이 그날 내내 멈춰 있었다
	f.round()

	if !equal(f.requests(), "skipped:stale:") || f.gold() != 0 {
		t.Errorf("일 = %v, 골드 = %s", f.requests(), f.gold())
	}
	f.clock.advance(24 * time.Hour) // 12일. 다음 날에 대신 사지 않는다
	f.round()
	if len(f.requests()) != 1 {
		t.Errorf("다른 날에 대신 샀다: %v", f.requests())
	}
}

func TestSwitchingTheModeSkipsWhatWasQueued(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(today, "")
	if _, err := f.service.QueueScheduled(context.Background(), f.clock.Now(), 1_000); err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}

	f.settings(true, 30_000) // 잔액 기준으로 바꿨다
	f.deposit(5_000)         // 기준 위라 잔액 기준으로는 아직 사지 않는다
	f.round()

	if !equal(f.requests(), "skipped:disabled:") || f.gold() != 5_000 {
		t.Errorf("일 = %v, 골드 = %s", f.requests(), f.gold())
	}
}

func TestTheMonthlyLimitAlsoStopsADateCharge(t *testing.T) {
	f := setUpCharging(t)
	f.enable("")
	f.deposit(120)
	f.spend()
	f.round() // 잔액 기준으로 이번 달에 1,000 원을 썼다
	if _, err := f.service.Update(context.Background(), f.user, autocharge.Settings{
		Enabled: true, Mode: autocharge.ModeDate, Threshold: threshold, ChargeDay: today,
		ProductID: "credits-1000", MonthlyLimit: 1_000,
	}, autocharge.TermsVersion); err != nil {
		t.Fatalf("설정을 적지 못했다: %v", err)
	}
	t.Cleanup(func() { f.dateSettings(false, today) })

	f.clock.advance(time.Second) // 적는 일의 차례가 시각으로 갈린다
	f.round()

	if !equal(f.requests(), "paid::", "skipped:monthly_limit:") {
		t.Errorf("일 = %v", f.requests())
	}
}

func TestADateConsentRecordsTheModeAndTheDay(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(7, "")

	var mode string
	var day *int16
	f.pool.QueryRow(context.Background(),
		"SELECT mode, charge_day FROM auto_charge_consents WHERE user_id = $1 ORDER BY id DESC LIMIT 1", f.user).Scan(&mode, &day)
	if mode != "date" || day == nil || *day != 7 {
		t.Errorf("동의 = %s %v", mode, day)
	}
	got := f.view()
	if got.Settings == nil || got.Settings.Mode != autocharge.ModeDate || got.Settings.ChargeDay != 7 {
		t.Errorf("설정 = %+v", got.Settings)
	}
}

func TestABalanceConsentDoesNotRecordAKeptDay(t *testing.T) {
	f := setUpCharging(t)
	f.enableDate(7, "")
	if _, err := f.service.Update(context.Background(), f.user, autocharge.Settings{
		Enabled: true, Mode: autocharge.ModeBalance, Threshold: threshold, ChargeDay: 7,
		ProductID: "credits-1000", MonthlyLimit: 30_000,
	}, autocharge.TermsVersion); err != nil {
		t.Fatalf("설정을 적지 못했다: %v", err)
	}

	var mode string
	var day *int16
	f.pool.QueryRow(context.Background(),
		"SELECT mode, charge_day FROM auto_charge_consents WHERE user_id = $1 ORDER BY id DESC LIMIT 1", f.user).Scan(&mode, &day)
	if mode != "balance" || day != nil {
		t.Errorf("동의 = %s %v", mode, day)
	}
	if got := f.view(); got.Settings == nil || got.Settings.ChargeDay != 7 {
		t.Errorf("남겨 둔 날이 사라졌다: %+v", got.Settings)
	}
}
