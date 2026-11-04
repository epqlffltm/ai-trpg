// billing-server/internal/autocharge/metrics_test.go
// 결제 작업이 충전할 일을 끝낸 결과를 세는지 본다(billing_auto_charges_total). 테스트용 스키마에서 진짜 결제 작업을 돌린다.
package autocharge_test

import (
	"context"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

const autoChargesMetric = "billing_auto_charges"

// measure 는 결제 작업처럼 이 서비스의 메트릭을 켠다(cmd/autocharge).
func (f chargeFixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := f.service.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("메트릭을 켜지 못했다: %v", err)
	}
	return recorder
}

// charges 는 그 label 로 센 수다. 세지 않았으면 0 이다.
func charges(recorder *metricstest.Recorder, labels ...attribute.KeyValue) int64 {
	if !recorder.HasPoint(autoChargesMetric, labels...) {
		return 0
	}
	return recorder.Int64(autoChargesMetric, labels...)
}

func outcome(value string) attribute.KeyValue { return attribute.String("outcome", value) }

func TestAPaidChargeIsCounted(t *testing.T) {
	f := setUpCharging(t)
	recorder := f.measure()
	f.enable("")
	f.deposit(60)
	f.spend()

	f.round()

	if got := charges(recorder, outcome("paid")); got != 1 {
		t.Errorf("paid = %d. 1 이어야 한다", got)
	}
	if recorder.HasPoint(autoChargesMetric, outcome("paid"), attribute.String("reason", "")) {
		t.Errorf("결제된 것에 까닭을 붙였다")
	}
}

func TestADeclinedChargeIsCounted(t *testing.T) {
	f := setUpCharging(t)
	recorder := f.measure()
	f.enable(payment.FakeChargeDeclined)
	f.deposit(60)
	f.spend()

	f.round()

	if got := charges(recorder, outcome("declined")); got != 1 || charges(recorder, outcome("paid")) != 0 {
		t.Errorf("declined = %d. 1 이어야 한다", got)
	}
}

func TestASkippedChargeIsCountedWithItsReason(t *testing.T) {
	ctx := context.Background()
	for name, tc := range map[string]struct {
		before func(f chargeFixture)
		reason string
	}{
		"그새 껐다":   {func(f chargeFixture) { f.settings(false, 30_000) }, autocharge.SkipDisabled},
		"하루가 지났다": {func(f chargeFixture) { f.clock.advance(autocharge.PendingFor) }, autocharge.SkipStale},
		"동의가 없다": {func(f chargeFixture) {
			f.pool.Exec(ctx, "DELETE FROM auto_charge_consents WHERE user_id = $1", f.user)
		}, autocharge.SkipTermsOutdated},
	} {
		f := setUpCharging(t)
		recorder := f.measure()
		f.enable("")
		f.deposit(60)
		f.spend()
		tc.before(f)

		f.round()

		if got := charges(recorder, outcome("skipped"), attribute.String("reason", tc.reason)); got != 1 {
			t.Errorf("%s: skipped/%s = %d. 1 이어야 한다", name, tc.reason, got)
		}
	}
}

func TestAChargeWithoutAnAnswerIsCountedAsRetried(t *testing.T) {
	f := setUpCharging(t)
	recorder := f.measure()

	f.lostCharge("")

	if got := charges(recorder, outcome("retried")); got != 1 || charges(recorder, outcome("paid")) != 0 {
		t.Errorf("retried = %d. 1 이어야 한다", got)
	}
}

func TestNothingIsCountedWithoutMeasure(t *testing.T) {
	// 결제 작업이 아닌 곳(서버, 테스트)은 Measure 를 부르지 않는다. 그래도 결제는 된다
	f := setUpCharging(t)
	f.enable("")
	f.deposit(60)
	f.spend()

	if result := f.round(); result.Paid != 1 {
		t.Errorf("결과 = %+v", result)
	}
}
