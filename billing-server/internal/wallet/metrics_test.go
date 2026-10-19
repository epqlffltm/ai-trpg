// billing-server/internal/wallet/metrics_test.go

// 원장에 적은 일을 세는 것(billing_ledger_operations)을 시험한다. 실제 PostgreSQL 에서 돈다.
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
package wallet_test

import (
	"errors"
	"testing"

	"github.com/jackc/pgx/v5"
	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// measure 는 이 테스트의 지갑이 원장에 적은 일을 메모리에 모은다.
func (f fixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	if err := f.service.Measure(recorder.Meter()); err != nil {
		f.t.Fatalf("원장의 메트릭을 만들지 못했다: %v", err)
	}
	return recorder
}

// operation 은 센 일 하나의 label 이다.
type operation struct {
	reason wallet.Reason
	result string
}

// wantOperations 는 센 일이 기대와 같은지 본다. 적지 않은 이유는 어느 결과로도 세지 않았어야 한다.
func wantOperations(t *testing.T, recorder *metricstest.Recorder, want map[operation]int64) {
	t.Helper()
	reasons := []wallet.Reason{
		wallet.ReasonDeposit, wallet.ReasonGrant, wallet.ReasonSpend, wallet.ReasonExpire, wallet.ReasonHold,
		wallet.ReasonRelease, wallet.ReasonRefund, wallet.ReasonUnrefund, wallet.ReasonRegroup,
	}
	for _, reason := range reasons {
		for _, result := range []string{"success", "failure"} {
			labels := []attribute.KeyValue{attribute.String("reason", string(reason)), attribute.String("result", result)}
			count, counted := want[operation{reason, result}]
			if !counted {
				if recorder.HasPoint("billing_ledger_operations", labels...) {
					t.Errorf("%s/%s 를 셌다. 일어나지 않은 일이다", reason, result)
				}
				continue
			}
			if got := recorder.Int64("billing_ledger_operations", labels...); got != count {
				t.Errorf("%s/%s = %d. %d 여야 한다", reason, result, got, count)
			}
		}
	}
}

func TestEachChangeIsCountedOnceWhateverItsLines(t *testing.T) {
	f := setUp(t, freeFirst)
	recorder := f.measure()
	f.grant(10)
	f.grant(20)
	f.clock.Advance(week)

	// 무료 크레딧 둘이 사라지고(expire 줄 둘, 일 하나) 산 크레딧이 들어온다
	f.deposit(100)
	// 무료 크레딧이 없으니 산 크레딧의 묶음에서만 뺀다. 줄 하나, 일 하나
	f.spend(30)

	f.wantLedger(
		line{wallet.KindFree, wallet.ReasonGrant, 10}, line{wallet.KindFree, wallet.ReasonGrant, 20},
		line{wallet.KindFree, wallet.ReasonExpire, -10}, line{wallet.KindFree, wallet.ReasonExpire, -20},
		line{wallet.KindPaid, wallet.ReasonDeposit, 100}, line{wallet.KindPaid, wallet.ReasonSpend, -30},
	)
	wantOperations(t, recorder, map[operation]int64{
		{wallet.ReasonGrant, "success"}: 2, {wallet.ReasonExpire, "success"}: 1,
		{wallet.ReasonDeposit, "success"}: 1, {wallet.ReasonSpend, "success"}: 1,
	})
}

func TestASpendTakenFromSeveralPlacesIsOneOperation(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(10)
	f.deposit(100)
	recorder := f.measure()

	// 무료 10 과 산 것 20 에서 뺀다. 줄은 둘이지만 쓴 일은 하나다
	f.spend(30)

	wantOperations(t, recorder, map[operation]int64{{wallet.ReasonSpend, "success"}: 1})
}

func TestARolledBackDepositIsCountedAsFailure(t *testing.T) {
	// 주문을 치렀다고 적지 못해 트랜잭션을 되돌렸다. 크레딧은 들어오지 않았다
	f := setUp(t, freeFirst)
	recorder := f.measure()
	failed := errors.New("order could not be marked paid")

	if err := f.depositForOrder(f.newOrder(), 1000, failed); !errors.Is(err, failed) {
		t.Fatalf("오류 = %v", err)
	}

	f.wantBalance(0, 0)
	wantOperations(t, recorder, map[operation]int64{{wallet.ReasonDeposit, "failure"}: 1})
}

func TestARefusedSpendCountsNothingItDidNotWrite(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(10)
	recorder := f.measure()

	if err := f.service.Spend(ctx(t), f.user, 50); !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 여야 한다", err)
	}

	// 줄을 하나도 적지 않았다. 거절은 원장의 일이 아니다
	wantOperations(t, recorder, map[operation]int64{})
}

func TestARefusedSpendRollsBackTheExpiryItTidied(t *testing.T) {
	// 지갑을 잠글 때 사라진 무료 크레딧을 먼저 적는다. 쓰기가 거절되면 그 줄도 함께 되돌린다.
	// 되돌린 것은 failure 다. 다음 변경이나 정리 작업이 다시 적는다
	f := setUp(t, freeFirst)
	f.grant(10)
	f.clock.Advance(week)
	recorder := f.measure()

	if err := f.service.Spend(ctx(t), f.user, 50); !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 여야 한다", err)
	}

	wantOperations(t, recorder, map[operation]int64{{wallet.ReasonExpire, "failure"}: 1})
}

func TestAHoldAndItsReturnAreCounted(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	recorder := f.measure()

	holdID := f.mustHold(50)
	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("홀드를 돌려주지 못했다: %v", err)
	}

	wantOperations(t, recorder, map[operation]int64{
		{wallet.ReasonHold, "success"}: 1, {wallet.ReasonRelease, "success"}: 1,
	})
}

func TestReturningAHoldWithNothingTakenCountsNothing(t *testing.T) {
	f := setUp(t, freeFirst)
	recorder := f.measure()

	// 뺀 줄이 없는 홀드다. 돌려줄 것이 없어 줄을 적지 않는다
	if err := f.returnForHold(f.newHold()); err != nil {
		t.Fatalf("오류 = %v", err)
	}

	wantOperations(t, recorder, map[operation]int64{})
}

func TestARefundAndItsReturnAreCounted(t *testing.T) {
	f := setUp(t, freeFirst)
	orderID := f.newOrder()
	if err := f.depositForOrder(orderID, 1000, nil); err != nil {
		t.Fatalf("주문의 크레딧을 넣지 못했다: %v", err)
	}
	recorder := f.measure()

	if err := f.takeForRefund(orderID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}
	if err := f.returnRefund(orderID); err != nil {
		t.Fatalf("되돌리지 못했다: %v", err)
	}

	wantOperations(t, recorder, map[operation]int64{
		{wallet.ReasonRefund, "success"}: 1, {wallet.ReasonUnrefund, "success"}: 1,
	})
}

func TestTheIdleSweepCountsTheExpiryItWrote(t *testing.T) {
	f := setUpSweep(t, freeFirst)
	f.grant(10)
	f.clock.Advance(week)
	recorder := f.measure()

	if _, err := f.service.ExpireIdle(ctx(t), 100_000); err != nil {
		t.Fatalf("정리 작업이 실패했다: %v", err)
	}

	wantOperations(t, recorder, map[operation]int64{{wallet.ReasonExpire, "success"}: 1})
}

func TestAChangeInATransactionNotOpenedByTxnIsNotCounted(t *testing.T) {
	// 세는 것의 한계를 적어 둔다. 부르는 쪽이 txn.Run 으로 열지 않으면 커밋을 알 수 없어 세지 않는다.
	// 서버의 부르는 쪽(주문, 홀드, 출석)은 모두 txn.Run 으로 연다. 그 패키지의 테스트가 센 것을 본다
	f := setUp(t, freeFirst)
	recorder := f.measure()

	err := pgx.BeginFunc(ctx(t), f.pool, func(tx pgx.Tx) error {
		return f.service.DepositForOrder(ctx(t), tx, f.user, 1000, f.newOrder())
	})

	if err != nil {
		t.Fatalf("오류 = %v", err)
	}
	f.wantBalance(1000, 0)
	wantOperations(t, recorder, map[operation]int64{})
}
