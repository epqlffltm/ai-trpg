// billing-server/internal/attendance/metrics_test.go

package attendance_test

import (
	"context"
	"errors"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
)

// 출석이 연 트랜잭션에서 지갑이 준 실버가 원장의 일로 세어지는지 본다(billing_ledger_operations_total).
// 출석의 줄과 실버는 한 트랜잭션이다. 커밋되면 success, 되돌리면 failure 다.

// measure 는 서버처럼 서비스들의 메트릭을 켠다(app.MeasureServices).
func (f fixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := app.MeasureServices(f.services, recorder.Meter()); err != nil {
		f.t.Fatalf("서비스의 메트릭을 켜지 못했다: %v", err)
	}
	return recorder
}

// grants 는 지급(grant)이 result 로 끝난 수다. 세지 않았으면 0 이다.
func grants(recorder *metricstest.Recorder, result string) int64 {
	labels := []attribute.KeyValue{attribute.String("reason", "grant"), attribute.String("result", result)}
	if !recorder.HasPoint("billing_ledger_operations", labels...) {
		return 0
	}
	return recorder.Int64("billing_ledger_operations", labels...)
}

func TestAClaimCountsItsSilverAfterCommit(t *testing.T) {
	f := setUp(t, 0)
	recorder := f.measure()

	f.claim(f.verified())

	if got := grants(recorder, "success"); got != 1 {
		t.Errorf("grant/success = %d. 1 이어야 한다", got)
	}
}

func TestARolledBackClaimCountsItsSilverAsFailure(t *testing.T) {
	// 7일째에 하루 양을 주고 상자의 지급에서 막혔다. 하루 양도 함께 되돌렸다
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
	recorder := f.measure()

	if _, err := f.service.Claim(context.Background(), user); !errors.Is(err, attendance.ErrAlreadyClaimed) {
		t.Fatalf("오류 = %v. ErrAlreadyClaimed 여야 한다", err)
	}

	if success, failure := grants(recorder, "success"), grants(recorder, "failure"); success != 0 || failure != 1 {
		t.Errorf("grant 의 success = %d, failure = %d. 0, 1 이어야 한다", success, failure)
	}
}
