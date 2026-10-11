// billing-server/internal/wallet/plan_internal_test.go

// 어디서 얼마씩 뺄지 정하는 계산을 DB 없이 확인한다.
package wallet

import (
	"errors"
	"reflect"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// grants 는 남은 양들로 지급 묶음의 목록을 만든다. 번호는 1 부터 차례로 붙는다.
func grants(remaining ...credit.Amount) []openGrant {
	list := make([]openGrant, 0, len(remaining))
	for index, amount := range remaining {
		list = append(list, openGrant{ID: int64(index + 1), Remaining: amount})
	}
	return list
}

func TestPlanSpend(t *testing.T) {
	cases := []struct {
		name      string
		amount    credit.Amount
		paid      credit.Amount
		grants    []openGrant
		freeFirst bool
		want      spendPlan
	}{
		{
			name: "무료부터: 무료로 다 된다", amount: 20, paid: 100, grants: grants(30), freeFirst: true,
			want: spendPlan{Free: []grantDraw{{1, 20}}},
		},
		{
			name: "무료부터: 모자란 만큼만 산 것에서", amount: 50, paid: 100, grants: grants(30), freeFirst: true,
			want: spendPlan{Paid: 20, Free: []grantDraw{{1, 30}}},
		},
		{
			name: "무료부터: 무료가 없다", amount: 50, paid: 100, grants: nil, freeFirst: true,
			want: spendPlan{Paid: 50},
		},
		{
			name: "무료부터: 앞의 묶음을 다 쓰고 다음으로", amount: 25, paid: 0, grants: grants(10, 10, 10), freeFirst: true,
			want: spendPlan{Free: []grantDraw{{1, 10}, {2, 10}, {3, 5}}},
		},
		{
			name: "무료부터: 딱 맞으면 뒤의 묶음은 건드리지 않는다", amount: 10, paid: 0, grants: grants(10, 10), freeFirst: true,
			want: spendPlan{Free: []grantDraw{{1, 10}}},
		},
		{
			name: "무료부터: 가진 것을 전부 쓴다", amount: 130, paid: 100, grants: grants(10, 20), freeFirst: true,
			want: spendPlan{Paid: 100, Free: []grantDraw{{1, 10}, {2, 20}}},
		},
		{
			name: "산 것부터: 산 것으로 다 된다", amount: 20, paid: 100, grants: grants(30), freeFirst: false,
			want: spendPlan{Paid: 20},
		},
		{
			name: "산 것부터: 모자란 만큼만 무료에서", amount: 120, paid: 100, grants: grants(15, 15), freeFirst: false,
			want: spendPlan{Paid: 100, Free: []grantDraw{{1, 15}, {2, 5}}},
		},
		{
			name: "산 것부터: 산 것이 없다", amount: 20, paid: 0, grants: grants(30), freeFirst: false,
			want: spendPlan{Free: []grantDraw{{1, 20}}},
		},
		{
			name: "산 것부터: 가진 것을 전부 쓴다", amount: 130, paid: 100, grants: grants(10, 20), freeFirst: false,
			want: spendPlan{Paid: 100, Free: []grantDraw{{1, 10}, {2, 20}}},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := planSpend(tc.amount, tc.paid, tc.grants, tc.freeFirst)
			if err != nil {
				t.Fatalf("오류가 났다: %v", err)
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Errorf("계획 = %+v, 기대 = %+v", got, tc.want)
			}
		})
	}
}

func TestPlanSpendRefusesWhenShort(t *testing.T) {
	cases := []struct {
		name   string
		amount credit.Amount
		paid   credit.Amount
		grants []openGrant
	}{
		{"아무것도 없다", 1, 0, nil},
		{"산 것만 있고 하나 모자란다", 101, 100, nil},
		{"무료만 있고 하나 모자란다", 31, 0, grants(10, 20)},
		{"둘을 더해도 하나 모자란다", 131, 100, grants(10, 20)},
	}
	for _, tc := range cases {
		for _, freeFirst := range []bool{true, false} {
			t.Run(tc.name, func(t *testing.T) {
				got, err := planSpend(tc.amount, tc.paid, tc.grants, freeFirst)
				if !errors.Is(err, ErrInsufficient) {
					t.Errorf("계획 = %+v, 오류 = %v. ErrInsufficient 이어야 한다", got, err)
				}
			})
		}
	}
}

func TestPlanSpendAlwaysAddsUpToTheAmount(t *testing.T) {
	// 어떤 조합이든 계획에 적힌 양을 모두 더하면 쓰려던 양이고, 어느 곳에서도 가진 것보다 많이 빼지 않는다
	held := grants(7, 1, 13, 4)
	const paid credit.Amount = 20
	for _, freeFirst := range []bool{true, false} {
		for amount := credit.Amount(1); amount <= 45; amount++ {
			plan, err := planSpend(amount, paid, held, freeFirst)
			if err != nil {
				t.Fatalf("amount %d: 오류가 났다: %v", amount, err)
			}
			total := plan.Paid
			for _, draw := range plan.Free {
				if draw.Amount <= 0 || draw.Amount > held[draw.GrantID-1].Remaining {
					t.Errorf("amount %d: 묶음 %d 에서 %d 를 뺀다", amount, draw.GrantID, draw.Amount)
				}
				total += draw.Amount
			}
			if total != amount || plan.Paid < 0 || plan.Paid > paid {
				t.Errorf("amount %d (무료부터=%v): 계획 = %+v", amount, freeFirst, plan)
			}
		}
	}
}

func TestPlanSpendDoesNotOverflowWithHugeBalances(t *testing.T) {
	// 산 크레딧이 int64 의 끝에 가까워도 더하다가 넘치지 않는다
	const huge credit.Amount = 9_223_372_036_854_775_807
	plan, err := planSpend(MaxAmount, huge, grants(MaxAmount, MaxAmount), true)
	if err != nil {
		t.Fatalf("오류가 났다: %v", err)
	}
	if want := (spendPlan{Free: []grantDraw{{1, MaxAmount}}}); !reflect.DeepEqual(plan, want) {
		t.Errorf("계획 = %+v, 기대 = %+v", plan, want)
	}
}

func TestPlanSpendDoesNotOverflowWithHugeGrants(t *testing.T) {
	// 남은 양을 그대로 다 더하면 int64 를 넘어 음수(-2)가 되는 두 묶음이다. 쓸 만큼만 더하므로 넘치지 않는다
	const huge credit.Amount = 9_223_372_036_854_775_807
	for _, freeFirst := range []bool{true, false} {
		plan, err := planSpend(10, 0, grants(huge, huge), freeFirst)
		if err != nil {
			t.Fatalf("오류가 났다: %v", err)
		}
		if want := (spendPlan{Free: []grantDraw{{1, 10}}}); !reflect.DeepEqual(plan, want) {
			t.Errorf("계획 = %+v, 기대 = %+v", plan, want)
		}
	}
}
