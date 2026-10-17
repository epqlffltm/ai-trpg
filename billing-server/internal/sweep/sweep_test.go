// billing-server/internal/sweep/sweep_test.go

package sweep_test

import (
	"context"
	"errors"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/guardiannotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/sweep"
)

// fakeStep 은 정해 둔 수와 오류로 답하는 가짜다. 받은 limit 과 부른 차례를 적는다.
type fakeStep struct {
	name  string
	count int
	err   error
	order *[]string
	limit int
}

func (f *fakeStep) ExpireDue(_ context.Context, limit int) (int, error) {
	return f.run(limit)
}

func (f *fakeStep) ExpireIdle(_ context.Context, limit int) (int, error) {
	return f.run(limit)
}

func (f *fakeStep) run(limit int) (int, error) {
	*f.order = append(*f.order, f.name)
	f.limit = limit
	return f.count, f.err
}

// steps 는 셋을 만든다.
func steps(order *[]string) (*fakeStep, *fakeStep, *fakeStep) {
	return &fakeStep{name: "holds", order: order}, &fakeStep{name: "wallets", order: order}, &fakeStep{name: "orders", order: order}
}

func TestARoundRunsEveryStepInOrder(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)
	holds.count, wallets.count, orders.count = 3, 2, 1

	result, err := sweep.New(holds, wallets, orders, 50).Round(context.Background())

	if err != nil || result != (sweep.Result{Holds: 3, FreeCreditUsers: 2, Orders: 1}) || !result.Any() {
		t.Errorf("결과 = %+v, %v", result, err)
	}
	if len(order) != 3 || order[0] != "holds" || order[1] != "wallets" || order[2] != "orders" {
		t.Errorf("차례 = %v. 홀드, 무료 크레딧, 주문 차례여야 한다", order)
	}
	if holds.limit != 50 || wallets.limit != 50 || orders.limit != 50 {
		t.Errorf("limit = %d, %d, %d", holds.limit, wallets.limit, orders.limit)
	}
}

func TestAFailingStepDoesNotStopTheOthers(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)
	broken := errors.New("holds table is locked")
	holds.err, holds.count = broken, 1
	orders.count = 4

	result, err := sweep.New(holds, wallets, orders, 0).Round(context.Background())

	if !errors.Is(err, broken) || len(order) != 3 {
		t.Fatalf("오류 = %v, 차례 = %v", err, order)
	}
	// 실패한 쪽도 그 전에 정리한 수는 센다
	if result != (sweep.Result{Holds: 1, Orders: 4}) {
		t.Errorf("결과 = %+v", result)
	}
}

func TestANonPositiveLimitUsesTheDefault(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)

	_, _ = sweep.New(holds, wallets, orders, -1).Round(context.Background())

	if holds.limit != sweep.DefaultLimit {
		t.Errorf("limit = %d, 기대 = %d", holds.limit, sweep.DefaultLimit)
	}
}

func TestAnEmptyRoundIsNothing(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)

	result, err := sweep.New(holds, wallets, orders, 10).Round(context.Background())

	if err != nil || result.Any() {
		t.Errorf("결과 = %+v, %v", result, err)
	}
}

// fakeNotices 는 정해 둔 대로 답하는 보호자 알림이다.
type fakeNotices struct {
	result guardiannotice.Result
	err    error
	limit  int
}

func (f *fakeNotices) Round(_ context.Context, limit int) (guardiannotice.Result, error) {
	f.limit = limit
	return f.result, f.err
}

func TestNoticesRunWhenAttached(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)
	notices := &fakeNotices{result: guardiannotice.Result{Queued: 1, Sent: 1}}

	result, err := sweep.New(holds, wallets, orders, 7).WithNotices(notices).Round(context.Background())

	if err != nil || result.Notices != notices.result || notices.limit != 7 || !result.Any() {
		t.Errorf("결과 = %+v, %v, limit = %d", result, err, notices.limit)
	}
}

func TestAFailingNoticeStepDoesNotStopTheOthers(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)
	notices := &fakeNotices{err: errors.New("DB 가 끊겼다")}

	_, err := sweep.New(holds, wallets, orders, 7).WithNotices(notices).Round(context.Background())

	if err == nil || len(order) != 3 {
		t.Errorf("오류 = %v, 돈 차례 = %v", err, order)
	}
}

func TestWithoutNoticesTheRoundIsAsBefore(t *testing.T) {
	var order []string
	holds, wallets, orders := steps(&order)

	result, err := sweep.New(holds, wallets, orders, 7).Round(context.Background())

	if err != nil || result.Notices != (guardiannotice.Result{}) {
		t.Errorf("결과 = %+v, %v", result, err)
	}
}
