// billing-server/internal/autocharge/charge_test.go
// 떨어진 것 적기와 결제하기(#980 의 둘째 단계)를 테스트용 스키마에서 본다. 홀드는 진짜 홀드 서비스로 건다(app.NewServices).
// 결제 대행사는 가짜다. 빌링키에 넣은 표시가 결과를 정한다(payment.FakeChargeDeclined, FakeChargeLost).
// 테이블을 비우지 않으므로 테스트마다 새 사용자를 쓴다.
package autocharge_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// threshold 와 holdPrice 는 테스트의 기준 골드와 홀드 하나의 값(가격표의 서술 값)이다.
const (
	threshold credit.Amount = 100
	holdPrice credit.Amount = 50
	source                  = "trpg-server"
)

// movingClock 은 테스트가 옮기는 시계다. 여러 고루틴이 함께 읽는다.
type movingClock struct {
	mu  sync.Mutex
	now time.Time
}

func (c *movingClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *movingClock) advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// countingCharger 는 보낸 결제와 조회를 세고, 앞의 lost 번은 답을 주지 않은 뒤 가짜에게 넘긴다. 조회는 늘 가짜에게 넘긴다.
type countingCharger struct {
	mu      sync.Mutex
	lost    int
	calls   []payment.CardCharge
	lookups []payment.CardCharge
}

func (c *countingCharger) LookupCharge(ctx context.Context, charge payment.CardCharge) (payment.ChargeResult, error) {
	c.mu.Lock()
	c.lookups = append(c.lookups, charge)
	c.mu.Unlock()
	return payment.Fake{}.LookupCharge(ctx, charge)
}

func (c *countingCharger) lookupCount() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.lookups)
}

func (c *countingCharger) ChargeCard(ctx context.Context, charge payment.CardCharge) (payment.ChargeResult, error) {
	c.mu.Lock()
	c.calls = append(c.calls, charge)
	lose := len(c.calls) <= c.lost
	c.mu.Unlock()
	if lose {
		return payment.ChargeResult{}, payment.ErrUnknownOutcome
	}
	return payment.Fake{}.ChargeCard(ctx, charge)
}

func (c *countingCharger) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.calls)
}

type chargeFixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	clock    *movingClock
	services app.Services
	charger  *countingCharger
	service  *autocharge.Service
	user     uuid.UUID
}

// setUpCharging 는 홀드, 지갑, 주문, 결제 작업을 만들고 결제할 수 있는 새 사용자를 하나 둔다. 지금은 2026-11-10 03:00 UTC 다.
func setUpCharging(t *testing.T) chargeFixture {
	t.Helper()
	pool := testenv.Pool(t)
	clock := &movingClock{now: time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC)}
	rules := config.Rules{SpendFreeFirst: true, FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NewProviders(config.Payment{Provider: config.ProviderFake}), clock.Now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	charger := &countingCharger{}
	f := chargeFixture{
		t: t, pool: pool, clock: clock, services: services, charger: charger, user: uuid.New(),
		service: autocharge.NewService(pool, clock.Now, payment.Fake{}, services.Eligibility).WithCharging(charger, services.Orders),
	}
	if _, err := services.Eligibility.Apply(context.Background(), eligibility.Update{UserID: f.user, Version: 1}); err != nil {
		t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return f
}

// enable 은 marks 를 넣은 카드를 등록하고 자동 충전을 켠다(기준 100, 1,000 골드, 한 달 30,000 원).
func (f chargeFixture) enable(marks string) {
	f.t.Helper()
	ctx := context.Background()
	key, err := f.service.CustomerKey(ctx, f.user)
	if err != nil {
		f.t.Fatalf("고객 키를 만들지 못했다: %v", err)
	}
	if _, err := f.service.RegisterCard(ctx, f.user, payment.FakeCardApproved+uuid.NewString()+marks, key); err != nil {
		f.t.Fatalf("카드를 등록하지 못했다: %v", err)
	}
	f.settings(true, 30_000)
}

func (f chargeFixture) settings(enabled bool, monthlyLimit int64) {
	f.t.Helper()
	if _, err := f.service.Update(context.Background(), f.user, autocharge.Settings{
		Enabled: enabled, Threshold: threshold, ProductID: "credits-1000", MonthlyLimit: monthlyLimit,
	}, autocharge.TermsVersion); err != nil {
		f.t.Fatalf("설정을 적지 못했다: %v", err)
	}
}

func (f chargeFixture) deposit(amount credit.Amount) {
	f.t.Helper()
	if err := f.services.Wallet.Deposit(context.Background(), f.user, amount); err != nil {
		f.t.Fatalf("골드를 넣지 못했다: %v", err)
	}
}

// spend 는 서술의 값으로 홀드를 하나 건다(골드 50). 시계를 1초 옮긴다(적는 일의 차례가 시각으로 갈린다).
func (f chargeFixture) spend() {
	f.t.Helper()
	f.clock.advance(time.Second)
	if _, _, err := f.services.Holds.Place(context.Background(), source, f.user, "table:"+uuid.NewString()+":round:1", pricing.NarrationStandard); err != nil {
		f.t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
}

func (f chargeFixture) round() autocharge.ChargeResult {
	f.t.Helper()
	result, err := f.service.ChargeRound(context.Background(), 100)
	if err != nil {
		f.t.Fatalf("한 바퀴를 돌지 못했다: %v", err)
	}
	return result
}

// requests 는 그 사람의 충전할 일의 상태들이다. 만든 차례다.
func (f chargeFixture) requests() []string {
	f.t.Helper()
	rows, err := f.pool.Query(context.Background(),
		"SELECT status || ':' || skip_reason || ':' || failure_code FROM auto_charge_requests WHERE user_id = $1 ORDER BY created_at, id", f.user)
	if err != nil {
		f.t.Fatalf("읽지 못했다: %v", err)
	}
	defer rows.Close()
	var got []string
	for rows.Next() {
		var line string
		if err := rows.Scan(&line); err != nil {
			f.t.Fatalf("읽지 못했다: %v", err)
		}
		got = append(got, line)
	}
	return got
}

func (f chargeFixture) gold() credit.Amount {
	f.t.Helper()
	balance, err := f.services.Wallet.Balance(context.Background(), f.user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	return balance.Paid
}

func (f chargeFixture) view() autocharge.View {
	f.t.Helper()
	got, err := f.service.Get(context.Background(), f.user)
	if err != nil {
		f.t.Fatalf("읽지 못했다: %v", err)
	}
	return got
}

func equal(a []string, b ...string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestDecide(t *testing.T) {
	for name, tc := range map[string]struct {
		enabled, armed bool
		paid           credit.Amount
		want           autocharge.Decision
	}{
		"꺼짐":           {false, true, 0, autocharge.DecideNothing},
		"떨어졌다":         {true, true, 99, autocharge.DecideCharge},
		"이미 한 번 샀다":    {true, false, 99, autocharge.DecideNothing},
		"기준에 딱 닿았다":    {true, false, 100, autocharge.DecideArm},
		"기준 위, 이미 켜졌다": {true, true, 500, autocharge.DecideNothing},
	} {
		if got := autocharge.Decide(tc.enabled, tc.armed, threshold, tc.paid); got != tc.want {
			t.Errorf("%s: %v", name, got)
		}
	}
}

func TestADropBelowTheThresholdBuysOnce(t *testing.T) {
	f := setUpCharging(t)
	f.enable("")
	f.deposit(170)

	f.spend() // 120: 아직 기준 위
	before := f.requests()
	f.spend() // 70: 떨어졌다
	f.spend() // 20: 이미 적었다
	queued := f.requests()
	result := f.round()

	if len(before) != 0 || !equal(queued, "pending::") {
		t.Fatalf("적은 일 = %v 다음 %v. 떨어진 때 한 번이어야 한다", before, queued)
	}
	if result.Paid != 1 || !equal(f.requests(), "paid::") || f.gold() != 20+1_000 {
		t.Errorf("결과 = %+v, 일 = %v, 골드 = %s", result, f.requests(), f.gold())
	}
	var channel, status, key string
	f.pool.QueryRow(context.Background(), "SELECT channel, status, idempotency_key FROM orders WHERE user_id = $1", f.user).Scan(&channel, &status, &key)
	if channel != "auto" || status != "paid" {
		t.Errorf("주문 = %s %s %s", channel, status, key)
	}
	var billingKeys int
	f.pool.QueryRow(context.Background(), "SELECT count(*) FROM auto_charge_requests WHERE user_id = $1 AND billing_key IS NOT NULL", f.user).Scan(&billingKeys)
	if billingKeys != 0 {
		t.Errorf("끝난 일에 빌링키가 남았다")
	}
}

func TestEnablingBelowTheThresholdBuysOnTheNextSpend(t *testing.T) {
	f := setUpCharging(t)
	f.deposit(60)
	f.enable("")

	f.spend()

	if !equal(f.requests(), "pending::") {
		t.Errorf("일 = %v", f.requests())
	}
}

func TestADeclineIsNotRetriedUntilTheGoldComesBack(t *testing.T) {
	f := setUpCharging(t)
	f.enable(payment.FakeChargeDeclined)
	f.deposit(120)
	f.spend()
	result := f.round()

	f.spend() // 아직 기준 아래. 다시 사지 않는다
	stillOne := f.requests()
	f.deposit(1_000) // 손으로 샀다
	f.spend()        // 기준 위를 봤다(다시 켜진다)
	if err := f.services.Wallet.Spend(context.Background(), f.user, f.gold()-60); err != nil {
		t.Fatalf("쓰지 못했다: %v", err)
	}
	f.spend() // 다시 떨어졌다

	if result.Declined != 1 || !equal(stillOne, "declined::"+payment.FakeCodeChargeDeclined) {
		t.Fatalf("결과 = %+v, 일 = %v", result, stillOne)
	}
	if got := f.requests(); len(got) != 2 || got[1] != "pending::" {
		t.Errorf("다시 떨어진 뒤 = %v", got)
	}
	if f.view().ConsecutiveFailures != 1 {
		t.Errorf("이어서 실패한 수 = %d", f.view().ConsecutiveFailures)
	}
}

func TestThreeDeclinesTurnItOff(t *testing.T) {
	f := setUpCharging(t)
	f.enable(payment.FakeChargeDeclined)
	ctx := context.Background()
	for i := range autocharge.MaxFailures {
		if i > 0 {
			// 사용자가 다시 켜지 않고 골드만 오르내린다: 기준 위를 본 뒤 떨어진다
			f.deposit(1_000)
			f.spend()
			if err := f.services.Wallet.Spend(ctx, f.user, f.gold()-60); err != nil {
				t.Fatalf("쓰지 못했다: %v", err)
			}
		} else {
			f.deposit(60)
		}
		f.spend()
		f.round()
	}

	got := f.view()
	if got.Settings == nil || got.Settings.Enabled || got.ConsecutiveFailures != autocharge.MaxFailures {
		t.Errorf("세 번 뒤 = %+v, 실패 %d", got.Settings, got.ConsecutiveFailures)
	}
	// 끈 거절에만 껐다고 적는다. 알림에 함께 싣는다
	rows, err := f.pool.Query(ctx, "SELECT turned_off FROM auto_charge_requests WHERE user_id = $1 ORDER BY created_at", f.user)
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	defer rows.Close()
	var turnedOff []bool
	for rows.Next() {
		var value bool
		if err := rows.Scan(&value); err != nil {
			t.Fatalf("읽지 못했다: %v", err)
		}
		turnedOff = append(turnedOff, value)
	}
	if len(turnedOff) != 3 || turnedOff[0] || turnedOff[1] || !turnedOff[2] {
		t.Errorf("껐다고 적은 것 = %v", turnedOff)
	}
}

func TestAnUnknownAnswerIsSentAgainWithTheSameOrderAndPaidOnce(t *testing.T) {
	f := setUpCharging(t)
	f.charger.lost = 2
	f.enable("")
	f.deposit(60)
	f.spend()

	first := f.round()
	f.round() // 아직 때가 아니다
	f.clock.advance(15 * time.Second)
	second := f.round()
	f.clock.advance(time.Minute)
	third := f.round()

	if first.Retried != 1 || second.Retried != 1 || third.Paid != 1 || f.charger.count() != 3 {
		t.Fatalf("바퀴 = %+v %+v %+v, 보낸 수 = %d", first, second, third, f.charger.count())
	}
	for _, call := range f.charger.calls {
		if call.OrderID != f.charger.calls[0].OrderID || call.BillingKey != f.charger.calls[0].BillingKey {
			t.Errorf("다시 보낸 것이 다르다: %+v", f.charger.calls)
		}
	}
	if f.gold() != 10+1_000 {
		t.Errorf("골드 = %s", f.gold())
	}
}

func TestOnceSentItFinishesEvenIfTheCardIsRemoved(t *testing.T) {
	// 보낸 뒤에는 돈이 나갔을 수 있다. 끄거나 카드를 지워도 옮겨 적은 카드로 답을 받는다
	f := setUpCharging(t)
	f.charger.lost = 1
	f.enable("")
	f.deposit(60)
	f.spend()
	f.round()

	if err := f.service.RemoveCard(context.Background(), f.user); err != nil {
		t.Fatalf("지우지 못했다: %v", err)
	}
	f.clock.advance(time.Minute)
	result := f.round()

	if result.Paid != 1 || !equal(f.requests(), "paid::") {
		t.Errorf("결과 = %+v, 일 = %v", result, f.requests())
	}
}

func TestBeforeSendingItIsSkippedForGoodReasons(t *testing.T) {
	ctx := context.Background()
	for name, tc := range map[string]struct {
		before func(f chargeFixture)
		reason string
	}{
		"그새 껐다":      {func(f chargeFixture) { f.settings(false, 30_000) }, autocharge.SkipDisabled},
		"그새 카드를 지웠다": {func(f chargeFixture) { f.service.RemoveCard(ctx, f.user) }, autocharge.SkipDisabled},
		"보호자 동의를 잃었다": {func(f chargeFixture) {
			adultFrom := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
			f.services.Eligibility.Apply(ctx, eligibility.Update{UserID: f.user, Version: 2, LegalAdultFrom: &adultFrom})
		}, autocharge.SkipNotEligible},
	} {
		f := setUpCharging(t)
		f.enable("")
		f.deposit(60)
		f.spend()
		tc.before(f)

		result := f.round()

		if result.Skipped != 1 || !equal(f.requests(), "skipped:"+tc.reason+":") || f.charger.count() != 0 {
			t.Errorf("%s: 결과 = %+v, 일 = %v, 보낸 수 = %d", name, result, f.requests(), f.charger.count())
		}
	}
}

func TestTheMonthlyLimitStopsIt(t *testing.T) {
	// 한 달 상한 1,500 원: 1,000 원을 한 번 산 뒤의 두 번째는 넘는다
	f := setUpCharging(t)
	f.enable("")
	f.settings(true, 1_500)
	f.deposit(60)
	f.spend()
	f.round()
	if err := f.services.Wallet.Spend(context.Background(), f.user, f.gold()-60); err != nil {
		t.Fatalf("쓰지 못했다: %v", err)
	}
	f.deposit(200)
	f.spend()
	if err := f.services.Wallet.Spend(context.Background(), f.user, f.gold()-60); err != nil {
		t.Fatalf("쓰지 못했다: %v", err)
	}
	f.spend()
	result := f.round()

	if got := f.requests(); len(got) != 2 || got[1] != "skipped:"+autocharge.SkipMonthlyCap+":" || result.Skipped != 1 {
		t.Errorf("일 = %v, 결과 = %+v", got, result)
	}
}

func TestNextMonthTheLimitStartsOver(t *testing.T) {
	// 한국 날짜로 달이 바뀌면 다시 센다. 2026-11-30 15:00 UTC 는 한국 12-01 00:00 이다
	if got := autocharge.MonthStart(time.Date(2026, 11, 30, 15, 0, 0, 0, time.UTC)); !got.Equal(time.Date(2026, 11, 30, 15, 0, 0, 0, time.UTC)) {
		t.Errorf("12월의 시작 = %v", got)
	}
	if got := autocharge.MonthStart(time.Date(2026, 11, 30, 14, 59, 0, 0, time.UTC)); !got.Equal(time.Date(2026, 10, 31, 15, 0, 0, 0, time.UTC)) {
		t.Errorf("11월의 시작 = %v", got)
	}
}

func TestTwoWorkersSendItOnce(t *testing.T) {
	f := setUpCharging(t)
	f.enable("")
	f.deposit(60)
	f.spend()

	var wg sync.WaitGroup
	for range 4 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, _ = f.service.ChargeRound(context.Background(), 10)
		}()
	}
	wg.Wait()

	if f.charger.count() != 1 || !equal(f.requests(), "paid::") || f.gold() != 10+1_000 {
		t.Errorf("보낸 수 = %d, 일 = %v, 골드 = %s", f.charger.count(), f.requests(), f.gold())
	}
}

func TestWithdrawalSkipsWhatWasNotSent(t *testing.T) {
	f := setUpCharging(t)
	f.enable("")
	f.deposit(60)
	f.spend()

	if _, err := f.service.Erase(context.Background(), f.user); err != nil {
		t.Fatalf("지우지 못했다: %v", err)
	}
	result := f.round()

	if !equal(f.requests(), "skipped:withdrawn:") || f.charger.count() != 0 || result.Any() {
		t.Errorf("일 = %v, 보낸 수 = %d", f.requests(), f.charger.count())
	}
}

func TestAPurchaseThatLeavesItBelowTheThresholdIsNotRepeated(t *testing.T) {
	// 기준(5,000)이 상품(1,000)보다 크다. 산 뒤에도 기준 아래지만 다시 사지 않는다. 기준 이상을 봐야 다시 산다
	f := setUpCharging(t)
	f.enable("")
	if _, err := f.service.Update(context.Background(), f.user, autocharge.Settings{
		Enabled: true, Threshold: 5_000, ProductID: "credits-1000", MonthlyLimit: 30_000,
	}, autocharge.TermsVersion); err != nil {
		t.Fatalf("설정을 적지 못했다: %v", err)
	}
	f.deposit(60)
	f.spend()
	f.round()

	f.spend()
	f.spend()

	if got := f.requests(); !equal(got, "paid::") {
		t.Errorf("일 = %v. 한 번만 사야 한다", got)
	}
}

func TestASuccessClearsTheFailures(t *testing.T) {
	f := setUpCharging(t)
	f.enable(payment.FakeChargeDeclined)
	f.deposit(60)
	f.spend()
	f.round()
	// 카드를 바꾸고 다시 켠다(켜면 0 이 되므로, 실패를 다시 하나 적어 둔다)
	f.enable("")
	if _, err := f.pool.Exec(context.Background(), "UPDATE auto_charge_settings SET consecutive_failures = 2 WHERE user_id = $1", f.user); err != nil {
		t.Fatalf("실패를 적지 못했다: %v", err)
	}
	f.deposit(50)
	f.spend()
	result := f.round()

	if result.Paid != 1 || f.view().ConsecutiveFailures != 0 {
		t.Errorf("결과 = %+v, 이어서 실패한 수 = %d", result, f.view().ConsecutiveFailures)
	}
}

func TestAQueuedChargeIsSentUntilADayHasPassed(t *testing.T) {
	// 결제 작업이 하루 가까이 멈췄다 돌아와도 하루가 되기 전이면 보낸다
	f := setUpCharging(t)
	f.enable("")
	f.deposit(60)
	f.spend()
	f.clock.advance(autocharge.PendingFor - time.Second)

	result := f.round()

	if result.Paid != 1 || !equal(f.requests(), "paid::") {
		t.Errorf("결과 = %+v, 일 = %v", result, f.requests())
	}
}

func TestAChargeQueuedADayAgoIsNotSentAndBuysOnTheNextDrop(t *testing.T) {
	// 결제 작업이 하루 넘게 멈춰 있었다. 며칠 전의 잔액으로 사지 않는다. 실패로 세지 않는다(알리지 않는 것은 usernotice 의 시험).
	// 다음에 골드가 떨어지면 그때 산다(armed 를 다시 켰다)
	f := setUpCharging(t)
	f.enable("")
	f.deposit(60)
	f.spend() // 10: 떨어졌다. 적었다
	f.clock.advance(autocharge.PendingFor)

	stale := f.round()

	if stale.Skipped != 1 || f.charger.count() != 0 || !equal(f.requests(), "skipped:"+autocharge.SkipStale+":") || f.gold() != 10 {
		t.Fatalf("결과 = %+v, 보낸 수 = %d, 일 = %v, 골드 = %s", stale, f.charger.count(), f.requests(), f.gold())
	}
	if got := f.view().ConsecutiveFailures; got != 0 {
		t.Errorf("이어서 실패한 수 = %d. 세지 않아야 한다", got)
	}
	f.deposit(60) // 70
	f.spend()     // 20: 다시 떨어졌다
	next := f.round()

	if next.Paid != 1 || !equal(f.requests(), "skipped:"+autocharge.SkipStale+":", "paid::") || f.gold() != 20+1_000 {
		t.Errorf("다음 = %+v, 일 = %v, 골드 = %s", next, f.requests(), f.gold())
	}
}
