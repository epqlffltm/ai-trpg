// billing-server/internal/usernotice/autocharge_test.go

// 되지 않은 자동 충전(#980)을 알림함에 알리는지 본다. 충전할 일은 줄을 손으로 적는다(결제 작업의 테스트는 internal/autocharge).
package usernotice_test

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
)

// finished 는 끝난 충전할 일 하나를 적는다. status 는 declined 나 skipped 다.
func (f fixture) finished(user uuid.UUID, status, skipReason string, turnedOff bool, at time.Time) uuid.UUID {
	f.t.Helper()
	id := uuid.New()
	_, err := f.pool.Exec(context.Background(), `
		INSERT INTO auto_charge_requests
		    (id, user_id, product_id, price, credits, status, skip_reason, failure_code, turned_off, next_attempt_at, created_at, finished_at)
		VALUES ($1, $2, 'credits-5000', 5000, 5000, $3, $4, 'REJECT_CARD_COMPANY', $5, $6, $6, $6)`,
		id, user, status, skipReason, turnedOff, at)
	if err != nil {
		f.t.Fatalf("충전할 일을 적지 못했다: %v", err)
	}
	return id
}

func TestAFailedAutoChargeIsTold(t *testing.T) {
	f := setUp(t)
	user := f.user()
	declined := f.finished(user, "declined", "", true, f.clock.now)
	limited := f.finished(user, "skipped", "monthly_limit", false, f.clock.now)

	f.round()
	f.round()

	got := f.sender.of(user)
	if len(got) != 2 {
		t.Fatalf("보낸 것 = %+v. 둘이어야 한다", got)
	}
	byKey := map[string]usernotice.Notice{}
	for _, notice := range got {
		byKey[notice.Key] = notice
	}
	first, second := byKey["autocharge.failed:"+declined.String()], byKey["autocharge.failed:"+limited.String()]
	if first.Kind != usernotice.KindAutoChargeFailed || second.Kind != usernotice.KindAutoChargeFailed {
		t.Fatalf("종류 = %+v", got)
	}
	want := map[string]any{"product_id": "credits-5000", "price": float64(5000), "reason": "declined", "turned_off": true}
	for key, value := range want {
		if payload(t, first)[key] != value {
			t.Errorf("거절의 %s = %v, 기대 = %v", key, payload(t, first)[key], value)
		}
	}
	if payload(t, second)["reason"] != "monthly_limit" || payload(t, second)["turned_off"] != false {
		t.Errorf("한 달 상한 = %v", payload(t, second))
	}
	// 결제 대행사의 거절 코드는 싣지 않는다
	for _, notice := range got {
		if _, ok := payload(t, notice)["failure_code"]; ok {
			t.Errorf("거절 코드를 실었다: %v", payload(t, notice))
		}
	}
}

func TestWhatTheUserDidIsNotTold(t *testing.T) {
	// 사용자가 끈 것, 탈퇴, 결제 작업이 멈춰 늦어서 그만둔 것(stale), 끝나지 않은 일, 오래된 일은 알리지 않는다
	f := setUp(t)
	user := f.user()
	f.finished(user, "skipped", "disabled", false, f.clock.now)
	f.finished(user, "skipped", "withdrawn", false, f.clock.now)
	f.finished(user, "skipped", "stale", false, f.clock.now)
	f.finished(user, "declined", "", false, f.clock.now.Add(-usernotice.LookBack-time.Minute))
	// 다음 시도 시각은 아주 먼 뒤로 둔다. 결제 작업은 사용자를 가리지 않아, 지금으로 두면 함께 도는 autocharge 의 시험이
	// 이 일을 가져가 그 시험의 수가 흔들린다
	if _, err := f.pool.Exec(context.Background(), `
		INSERT INTO auto_charge_requests (id, user_id, product_id, price, credits, status, next_attempt_at, created_at)
		VALUES ($1, $2, 'credits-5000', 5000, 5000, 'pending', '2999-01-01T00:00:00Z', $3)`, uuid.New(), user, f.clock.now); err != nil {
		t.Fatalf("충전할 일을 적지 못했다: %v", err)
	}

	f.round()

	if got := f.sender.of(user); len(got) != 0 {
		t.Errorf("보낸 것 = %+v", got)
	}
}
