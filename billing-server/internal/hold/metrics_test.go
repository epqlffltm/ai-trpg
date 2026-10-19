// billing-server/internal/hold/metrics_test.go

// 홀드의 이름표(중복 방지 키)의 결과와, 홀드가 연 트랜잭션에서 지갑이 적은 일이 세어지는지 시험한다.
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
package hold_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// measure 는 이 테스트의 홀드와 지갑이 센 것을 메모리에 모은다.
func (f fixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := f.service.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("홀드의 메트릭을 만들지 못했다: %v", err)
	}
	if err := f.wallet.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("원장의 메트릭을 만들지 못했다: %v", err)
	}
	return recorder
}

// count 는 그 이름과 label 의 수다. 세지 않았으면 0 이다.
func count(recorder *metricstest.Recorder, name string, labels ...attribute.KeyValue) int64 {
	if !recorder.HasPoint(name, labels...) {
		return 0
	}
	return recorder.Int64(name, labels...)
}

// keys 는 홀드의 이름표 가운데 outcome 인 것의 수다.
func keys(recorder *metricstest.Recorder, outcome string) int64 {
	return count(recorder, "billing_idempotency", attribute.String("kind", "hold"), attribute.String("outcome", outcome))
}

// ledger 는 원장의 일 가운데 reason 이 커밋된 수다.
func ledger(recorder *metricstest.Recorder, reason wallet.Reason) int64 {
	return count(recorder, "billing_ledger_operations",
		attribute.String("reason", string(reason)), attribute.String("result", "success"))
}

func TestHoldReferencesAreCountedAsFirstReplayedOrConflict(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	stranger := uuid.New()
	if err := f.wallet.Deposit(ctx(t), stranger, 100); err != nil {
		t.Fatalf("다른 사용자에게 크레딧을 넣지 못했다: %v", err)
	}
	recorder := f.measure()
	reference := newReference()

	f.place(reference)
	f.place(reference)
	// 같은 이름표를 다른 사용자로 건다. 부르는 서버의 버그다
	if _, _, err := f.service.Place(ctx(t), source, stranger, reference, priceCode); !errors.Is(err, hold.ErrReferenceReused) {
		t.Fatalf("오류 = %v. ErrReferenceReused 여야 한다", err)
	}

	want := map[string]int64{"first": 1, "replayed": 1, "conflict": 1}
	for outcome, n := range want {
		if got := keys(recorder, outcome); got != n {
			t.Errorf("%s = %d. %d 여야 한다", outcome, got, n)
		}
	}
	// 다시 보낸 요청은 크레딧을 다시 빼지 않았다. 원장의 hold 는 한 번이다
	if got := ledger(recorder, wallet.ReasonHold); got != 1 {
		t.Errorf("hold = %d. 1 이어야 한다", got)
	}
}

func TestAHoldThatCouldNotBePaidIsNotAKeyResult(t *testing.T) {
	// 크레딧이 모자라 홀드도 남지 않았다. 이름표는 다음에 다시 쓸 수 있다. 키의 결과로 세지 않는다
	f := setUp(t)
	recorder := f.measure()

	if _, _, err := f.service.Place(ctx(t), source, f.user, newReference(), priceCode); !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 여야 한다", err)
	}

	for _, outcome := range []string{"first", "replayed", "conflict"} {
		if got := keys(recorder, outcome); got != 0 {
			t.Errorf("%s = %d. 세지 않아야 한다", outcome, got)
		}
	}
}

func TestReleasingAHoldCountsTheReturnInTheLedger(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	recorder := f.measure()
	released := newReference()
	f.place(released)
	captured := newReference()
	f.place(captured)

	if _, err := f.service.Release(ctx(t), source, released); err != nil {
		t.Fatalf("홀드를 돌려주지 못했다: %v", err)
	}
	// 확정은 원장에 줄을 남기지 않는다. 뺀 그대로 쓰였다
	if _, err := f.service.Capture(ctx(t), source, captured); err != nil {
		t.Fatalf("홀드를 확정하지 못했다: %v", err)
	}

	if hold, release := ledger(recorder, wallet.ReasonHold), ledger(recorder, wallet.ReasonRelease); hold != 2 || release != 1 {
		t.Errorf("hold = %d, release = %d. 2, 1 이어야 한다", hold, release)
	}
}

func TestAnExpiredHoldCountsTheReturnInTheLedger(t *testing.T) {
	f := setUpSweep(t)
	f.fund(100, 0)
	f.place(newReference())
	recorder := f.measure()
	f.clock.Advance(ttl)

	if expired, err := f.service.ExpireDue(ctx(t), 100); err != nil || expired != 1 {
		t.Fatalf("만료한 수 = %d, %v. 1 이어야 한다", expired, err)
	}

	if got := ledger(recorder, wallet.ReasonRelease); got != 1 {
		t.Errorf("release = %d. 1 이어야 한다", got)
	}
}
