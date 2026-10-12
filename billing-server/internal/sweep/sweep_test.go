// billing-server/internal/sweep/sweep_test.go

package sweep_test

import (
	"context"
	"errors"
	"testing"

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
