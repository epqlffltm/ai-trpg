// billing-server/internal/autocharge/resolve_test.go
// 다시 보내는 기한(ResendFor) 뒤의 조회와, 사람이 결과를 정하는 것(Resolve)을 테스트용 스키마에서 본다.
// 결제 대행사는 가짜다. 빌링키의 표시가 답을 정한다(charge_lost 는 결제에 답하지 않고, lookup_paid·lookup_missing 은 조회의 답이다).
package autocharge_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// lostCharge 는 marks 를 넣은 카드로 켜고 골드를 떨어뜨려 한 바퀴를 돈다. 결제에 답이 오지 않아 charging 으로 남는다.
// 테스트가 끝나면 끝나지 않은 일을 끝난 일(skipped)로 바꾼다. 결제 작업은 사용자를 가리지 않으므로,
// 남겨 두면 다른 테스트의 바퀴가 이 일을 가져가 그 테스트의 수가 흔들린다.
func (f chargeFixture) lostCharge(marks string) uuid.UUID {
	f.t.Helper()
	f.t.Cleanup(func() {
		_, _ = f.pool.Exec(context.Background(), `UPDATE auto_charge_requests
			SET status = 'skipped', skip_reason = 'disabled', billing_key = NULL, customer_key = NULL, finished_at = created_at
			WHERE user_id = $1 AND status IN ('pending', 'charging')`, f.user)
	})
	f.enable("_" + payment.FakeChargeLost + marks)
	f.deposit(60)
	f.spend()
	if result := f.round(); result.Retried != 1 || !equal(f.requests(), "charging::") {
		f.t.Fatalf("바퀴 = %+v, 일 = %v. 답이 오지 않아야 한다", result, f.requests())
	}
	var id uuid.UUID
	if err := f.pool.QueryRow(context.Background(), "SELECT id FROM auto_charge_requests WHERE user_id = $1", f.user).Scan(&id); err != nil {
		f.t.Fatalf("일을 읽지 못했다: %v", err)
	}
	return id
}

// payNow 는 다음 시도 시각을 지금으로 당긴다. 바퀴를 돌면 바로 가져간다.
func (f chargeFixture) payNow(id uuid.UUID) {
	f.t.Helper()
	if _, err := f.pool.Exec(context.Background(), "UPDATE auto_charge_requests SET next_attempt_at = $1 WHERE id = $2", f.clock.Now(), id); err != nil {
		f.t.Fatalf("시각을 당기지 못했다: %v", err)
	}
}

// pastResend 는 시계를 그 일이 적힌 때부터 ResendFor 가 지난 때로 옮긴다.
func (f chargeFixture) pastResend(id uuid.UUID) {
	f.t.Helper()
	f.clock.advance(autocharge.ResendFor)
	f.payNow(id)
}

func TestItIsSentAgainOnlyUntilTheResendWindowEnds(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("")

	// 기한 1초 전: 다시 보낸다
	f.clock.advance(autocharge.ResendFor - time.Second)
	f.payNow(id)
	before := f.round()
	// 기한: 보내지 않고 조회한다
	f.clock.advance(time.Second)
	f.payNow(id)
	after := f.round()

	if before.LookedUp != 0 || f.charger.count() != 2 {
		t.Errorf("기한 전 = %+v, 보낸 수 = %d. 다시 보내야 한다", before, f.charger.count())
	}
	if after.LookedUp != 1 || after.Retried != 1 || f.charger.count() != 2 || f.charger.lookupCount() != 1 {
		t.Errorf("기한 = %+v, 보낸 수 = %d, 조회 수 = %d. 보내지 않고 조회해야 한다", after, f.charger.count(), f.charger.lookupCount())
	}
	if got := f.charger.lookups[0]; got.OrderID != id || got.Amount != 1_000 {
		t.Errorf("조회한 것 = %+v", got)
	}
	if !equal(f.requests(), "charging::") {
		t.Errorf("일 = %v. 조회에도 답이 없으면 그대로다", f.requests())
	}
}

func TestALookupThatFindsThePaymentPays(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("_" + payment.FakeLookupPaid)
	f.pastResend(id)

	result := f.round()

	if result.LookedUp != 1 || result.Paid != 1 || !equal(f.requests(), "paid::") || f.gold() != 10+1_000 {
		t.Fatalf("결과 = %+v, 일 = %v, 골드 = %s", result, f.requests(), f.gold())
	}
	var key string
	if err := f.pool.QueryRow(context.Background(), "SELECT payment_key FROM orders WHERE id = $1", id).Scan(&key); err != nil ||
		key != "fake_auto_"+stripDashes(id) {
		t.Errorf("주문의 결제 번호 = %q, %v", key, err)
	}
}

func TestALookupThatFindsNoPaymentDeclines(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("_" + payment.FakeLookupMissing)
	f.pastResend(id)

	result := f.round()

	if result.LookedUp != 1 || result.Declined != 1 || !equal(f.requests(), "declined::"+payment.CodeChargeNotFound) || f.gold() != 10 {
		t.Fatalf("결과 = %+v, 일 = %v, 골드 = %s", result, f.requests(), f.gold())
	}
	// 거절과 같다. 이어서 실패한 수가 는다
	if got := f.view().ConsecutiveFailures; got != 1 {
		t.Errorf("이어서 실패한 수 = %d", got)
	}
}

func TestAPersonCanResolveOnlyAfterTheResendWindow(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("")
	key := "tviva_manual_" + stripDashes(uuid.New())
	paid := autocharge.Resolution{ID: id, Outcome: autocharge.OutcomePaid, PaymentKey: key, Reason: "상점관리자에서 완료", DecidedBy: "test"}

	early := f.service.Resolve(context.Background(), paid)
	f.clock.advance(autocharge.ResendFor)
	late := f.service.Resolve(context.Background(), paid)

	if !errors.Is(early, autocharge.ErrStillResending) {
		t.Errorf("기한 전 = %v. 아직 정할 수 없어야 한다", early)
	}
	if late != nil || !equal(f.requests(), "paid::") || f.gold() != 10+1_000 {
		t.Fatalf("기한 뒤 = %v, 일 = %v, 골드 = %s", late, f.requests(), f.gold())
	}
	var got, channel string
	if err := f.pool.QueryRow(context.Background(), "SELECT payment_key, channel FROM orders WHERE id = $1", id).Scan(&got, &channel); err != nil ||
		key != paid.PaymentKey || channel != "auto" {
		t.Errorf("주문 = %q %q, %v", key, channel, err)
	}
	// 끝난 일은 다시 정할 수 없다
	if again := f.service.Resolve(context.Background(), paid); !errors.Is(again, autocharge.ErrNotCharging) {
		t.Errorf("다시 정함 = %v", again)
	}
}

func TestAPaymentKeyAlreadyUsedIsRefused(t *testing.T) {
	// 상점관리자에서 옮겨 적다 다른 주문의 결제 번호를 적으면 거절한다. 아무것도 적지 않는다
	f := setUpCharging(t)
	id := f.lostCharge("")
	f.clock.advance(autocharge.ResendFor)
	var used string
	if err := f.pool.QueryRow(context.Background(), "SELECT payment_key FROM orders WHERE payment_key IS NOT NULL LIMIT 1").Scan(&used); err != nil {
		t.Fatalf("쓰인 결제 번호를 읽지 못했다: %v", err)
	}

	err := f.service.Resolve(context.Background(), autocharge.Resolution{
		ID: id, Outcome: autocharge.OutcomePaid, PaymentKey: used, Reason: "근거", DecidedBy: "test",
	})

	if !errors.Is(err, order.ErrPaymentKeyUsed) || !equal(f.requests(), "charging::") || f.gold() != 10 {
		t.Errorf("결과 = %v, 일 = %v, 골드 = %s", err, f.requests(), f.gold())
	}
}

func TestAPersonCanResolveItAsDeclined(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("")
	f.clock.advance(autocharge.ResendFor)

	err := f.service.Resolve(context.Background(), autocharge.Resolution{
		ID: id, Outcome: autocharge.OutcomeDeclined, Reason: "상점관리자에 결제가 없음", DecidedBy: "test",
	})

	if err != nil || !equal(f.requests(), "declined::"+autocharge.FailureCodeResolved) || f.gold() != 10 {
		t.Fatalf("결과 = %v, 일 = %v, 골드 = %s", err, f.requests(), f.gold())
	}
	if got := f.view().ConsecutiveFailures; got != 1 {
		t.Errorf("이어서 실패한 수 = %d", got)
	}
}

func TestAResolutionNeedsEverything(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("")
	f.clock.advance(autocharge.ResendFor)
	full := autocharge.Resolution{ID: id, Outcome: autocharge.OutcomePaid, PaymentKey: "tviva_manual_x", Reason: "근거", DecidedBy: "test"}

	for name, change := range map[string]func(*autocharge.Resolution){
		"근거가 없다":          func(r *autocharge.Resolution) { r.Reason = " " },
		"정한 사람이 없다":       func(r *autocharge.Resolution) { r.DecidedBy = "" },
		"결제됨인데 결제 번호가 없다": func(r *autocharge.Resolution) { r.PaymentKey = "" },
		"결제 번호에 빈칸이 있다":   func(r *autocharge.Resolution) { r.PaymentKey = "tviva manual" },
		"결제 번호가 너무 길다":    func(r *autocharge.Resolution) { r.PaymentKey = string(make([]byte, 201)) },
		"거절인데 결제 번호가 있다":  func(r *autocharge.Resolution) { r.Outcome = autocharge.OutcomeDeclined },
		"모르는 결과":          func(r *autocharge.Resolution) { r.Outcome = "refunded" },
	} {
		resolution := full
		change(&resolution)
		if err := f.service.Resolve(context.Background(), resolution); !errors.Is(err, autocharge.ErrResolutionIncomplete) {
			t.Errorf("%s: %v", name, err)
		}
	}
	if missing := f.service.Resolve(context.Background(), autocharge.Resolution{
		ID: uuid.New(), Outcome: autocharge.OutcomeDeclined, Reason: "근거", DecidedBy: "test",
	}); !errors.Is(missing, autocharge.ErrRequestNotFound) {
		t.Errorf("없는 일 = %v", missing)
	}
	// 하나도 적지 않았다
	if !equal(f.requests(), "charging::") {
		t.Errorf("일 = %v", f.requests())
	}
}

func TestAResolutionAfterTheJobFinishedItIsRefused(t *testing.T) {
	// 사람이 정하려고 읽은 뒤, 적기 전에 결제 작업의 조회가 먼저 적으면 사람의 것은 쓰이지 않는다
	f := setUpCharging(t)
	id := f.lostCharge("_" + payment.FakeLookupMissing)
	f.pastResend(id)
	open, err := f.service.ListOpen(context.Background(), 0, 1000)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	found := false
	for _, o := range open {
		if o.ID == id {
			found = o.Decidable && o.Status == "charging"
		}
	}
	if !found {
		t.Fatalf("목록에 정할 수 있는 일로 없다: %+v", open)
	}
	f.round()

	err = f.service.Resolve(context.Background(), autocharge.Resolution{
		ID: id, Outcome: autocharge.OutcomePaid, PaymentKey: "tviva_manual", Reason: "근거", DecidedBy: "test",
	})

	if !errors.Is(err, autocharge.ErrNotCharging) || !equal(f.requests(), "declined::"+payment.CodeChargeNotFound) {
		t.Errorf("결과 = %v, 일 = %v", err, f.requests())
	}
}

func TestAResolutionThatLosesTheRaceIsNotUsed(t *testing.T) {
	// 사람이 읽은 뒤 적기 전에 결제 작업이 먼저 끝내면(줄의 잠금을 기다리는 사이), 사람의 것은 쓰이지 않고 그렇다고 알린다
	f := setUpCharging(t)
	id := f.lostCharge("")
	f.clock.advance(autocharge.ResendFor)
	ctx := context.Background()
	tx, err := f.pool.Begin(ctx)
	if err != nil {
		t.Fatalf("트랜잭션을 열지 못했다: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, "SELECT 1 FROM auto_charge_requests WHERE id = $1 FOR UPDATE", id); err != nil {
		t.Fatalf("잠그지 못했다: %v", err)
	}

	done := make(chan error, 1)
	go func() {
		done <- f.service.Resolve(ctx, autocharge.Resolution{
			ID: id, Outcome: autocharge.OutcomeDeclined, Reason: "근거", DecidedBy: "test",
		})
	}()
	f.waitForALockWaiter()
	// 결제 작업이 먼저 승인으로 끝냈다
	if _, err := tx.Exec(ctx, `UPDATE auto_charge_requests
		SET status = 'paid', billing_key = NULL, customer_key = NULL, finished_at = created_at WHERE id = $1`, id); err != nil {
		t.Fatalf("끝내지 못했다: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("커밋하지 못했다: %v", err)
	}

	if err := <-done; !errors.Is(err, autocharge.ErrResolvedElsewhere) {
		t.Errorf("결과 = %v. 먼저 끝난 것을 알려야 한다", err)
	}
	if !equal(f.requests(), "paid::") || f.view().ConsecutiveFailures != 0 {
		t.Errorf("일 = %v, 이어서 실패한 수 = %d. 사람의 거절이 쓰이지 않아야 한다", f.requests(), f.view().ConsecutiveFailures)
	}
}

// waitForALockWaiter 는 auto_charge_requests 의 줄 잠금을 기다리는 연결이 생길 때까지 기다린다(5초까지).
func (f chargeFixture) waitForALockWaiter() {
	f.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		var waiting int
		err := f.pool.QueryRow(context.Background(), `SELECT count(*) FROM pg_stat_activity
			WHERE wait_event_type = 'Lock' AND query ILIKE '%auto_charge_requests%'`).Scan(&waiting)
		if err != nil {
			f.t.Fatalf("기다리는 연결을 읽지 못했다: %v", err)
		}
		if waiting > 0 {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	f.t.Fatal("잠금을 기다리는 연결이 생기지 않았다")
}

func TestTheOpenListShowsWhatIsNotYetDecidable(t *testing.T) {
	f := setUpCharging(t)
	id := f.lostCharge("")
	f.clock.advance(time.Hour)

	open, err := f.service.ListOpen(context.Background(), 30*time.Minute, 1000)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	none, err := f.service.ListOpen(context.Background(), 2*time.Hour, 1000)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}

	var mine *autocharge.OpenRequest
	for i := range open {
		if open[i].ID == id {
			mine = &open[i]
		}
	}
	if mine == nil || mine.Decidable || mine.Attempts != 1 || mine.Price != 1_000 || mine.LastError == "" {
		t.Errorf("목록의 일 = %+v", mine)
	}
	for _, o := range none {
		if o.ID == id {
			t.Error("기준보다 새 일이 목록에 있다")
		}
	}
}

func stripDashes(id uuid.UUID) string {
	out := make([]byte, 0, 32)
	for _, c := range []byte(id.String()) {
		if c != '-' {
			out = append(out, c)
		}
	}
	return string(out)
}
