// billing-server/internal/wallet/plan_internal_test.go

// 어디서 얼마씩 뺄지 정하는 계산을 DB 없이 확인한다.
package wallet

import (
	"errors"
	"reflect"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// grants 는 남은 양들로 무료 크레딧의 지급 묶음 목록을 만든다. 번호는 1 부터 차례로 붙는다.
func grants(remaining ...credit.Amount) []bucket {
	return buckets(1, remaining...)
}

// lots 는 남은 양들로 산 크레딧의 묶음 목록을 만든다. 번호는 101 부터 차례로 붙는다. 지급 묶음과 번호가 겹치지 않는다.
func lots(remaining ...credit.Amount) []bucket {
	return buckets(101, remaining...)
}

// buckets 는 남은 양들로 묶음의 목록을 만든다. 번호는 first 부터 차례로 붙는다.
func buckets(first int64, remaining ...credit.Amount) []bucket {
	list := make([]bucket, 0, len(remaining))
	for index, amount := range remaining {
		list = append(list, bucket{ID: first + int64(index), Remaining: amount})
	}
	return list
}

func TestPlanSpend(t *testing.T) {
	cases := []struct {
		name      string
		amount    credit.Amount
		lots      []bucket
		grants    []bucket
		freeFirst bool
		want      spendPlan
	}{
		{
			name: "무료부터: 무료로 다 된다", amount: 20, lots: lots(100), grants: grants(30), freeFirst: true,
			want: spendPlan{Free: []draw{{1, 20}}},
		},
		{
			name: "무료부터: 모자란 만큼만 산 것에서", amount: 50, lots: lots(100), grants: grants(30), freeFirst: true,
			want: spendPlan{Paid: []draw{{101, 20}}, Free: []draw{{1, 30}}},
		},
		{
			name: "무료부터: 무료가 없다", amount: 50, lots: lots(100), grants: nil, freeFirst: true,
			want: spendPlan{Paid: []draw{{101, 50}}},
		},
		{
			name: "무료부터: 앞의 묶음을 다 쓰고 다음으로", amount: 25, lots: nil, grants: grants(10, 10, 10), freeFirst: true,
			want: spendPlan{Free: []draw{{1, 10}, {2, 10}, {3, 5}}},
		},
		{
			name: "무료부터: 딱 맞으면 뒤의 묶음은 건드리지 않는다", amount: 10, lots: nil, grants: grants(10, 10), freeFirst: true,
			want: spendPlan{Free: []draw{{1, 10}}},
		},
		{
			name: "무료부터: 가진 것을 전부 쓴다", amount: 130, lots: lots(100), grants: grants(10, 20), freeFirst: true,
			want: spendPlan{Paid: []draw{{101, 100}}, Free: []draw{{1, 10}, {2, 20}}},
		},
		{
			name: "산 것부터: 산 것으로 다 된다", amount: 20, lots: lots(100), grants: grants(30), freeFirst: false,
			want: spendPlan{Paid: []draw{{101, 20}}},
		},
		{
			name: "산 것부터: 모자란 만큼만 무료에서", amount: 120, lots: lots(100), grants: grants(15, 15), freeFirst: false,
			want: spendPlan{Paid: []draw{{101, 100}}, Free: []draw{{1, 15}, {2, 5}}},
		},
		{
			name: "산 것부터: 산 것이 없다", amount: 20, lots: nil, grants: grants(30), freeFirst: false,
			want: spendPlan{Free: []draw{{1, 20}}},
		},
		{
			name: "산 것부터: 가진 것을 전부 쓴다", amount: 130, lots: lots(100), grants: grants(10, 20), freeFirst: false,
			want: spendPlan{Paid: []draw{{101, 100}}, Free: []draw{{1, 10}, {2, 20}}},
		},
		{
			name: "산 것은 먼저 들어온 묶음부터", amount: 25, lots: lots(10, 10, 10), grants: nil, freeFirst: false,
			want: spendPlan{Paid: []draw{{101, 10}, {102, 10}, {103, 5}}},
		},
		{
			name: "산 것: 딱 맞으면 뒤의 묶음은 그대로", amount: 10, lots: lots(10, 10), grants: nil, freeFirst: true,
			want: spendPlan{Paid: []draw{{101, 10}}},
		},
		{
			name: "무료부터: 남은 만큼을 산 묶음 여럿에서", amount: 45, lots: lots(20, 20, 20), grants: grants(10), freeFirst: true,
			want: spendPlan{Paid: []draw{{101, 20}, {102, 15}}, Free: []draw{{1, 10}}},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := planSpend(tc.amount, tc.lots, tc.grants, tc.freeFirst)
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
		lots   []bucket
		grants []bucket
	}{
		{"아무것도 없다", 1, nil, nil},
		{"산 것만 있고 하나 모자란다", 101, lots(100), nil},
		{"산 묶음 여럿을 더해도 하나 모자란다", 31, lots(10, 20), nil},
		{"무료만 있고 하나 모자란다", 31, nil, grants(10, 20)},
		{"둘을 더해도 하나 모자란다", 131, lots(60, 40), grants(10, 20)},
	}
	for _, tc := range cases {
		for _, freeFirst := range []bool{true, false} {
			t.Run(tc.name, func(t *testing.T) {
				got, err := planSpend(tc.amount, tc.lots, tc.grants, freeFirst)
				if !errors.Is(err, ErrInsufficient) {
					t.Errorf("계획 = %+v, 오류 = %v. ErrInsufficient 이어야 한다", got, err)
				}
			})
		}
	}
}

func TestPlanSpendAlwaysAddsUpToTheAmount(t *testing.T) {
	// 어떤 조합이든 계획에 적힌 양을 모두 더하면 쓰려던 양이고, 어느 묶음에서도 가진 것보다 많이 빼지 않는다
	held := grants(7, 1, 13, 4)
	paid := lots(5, 9, 6)
	remaining := map[int64]credit.Amount{}
	for _, b := range append(append([]bucket{}, held...), paid...) {
		remaining[b.ID] = b.Remaining
	}
	for _, freeFirst := range []bool{true, false} {
		for amount := credit.Amount(1); amount <= 45; amount++ {
			plan, err := planSpend(amount, paid, held, freeFirst)
			if err != nil {
				t.Fatalf("amount %d: 오류가 났다: %v", amount, err)
			}
			var total credit.Amount
			for _, d := range append(append([]draw{}, plan.Paid...), plan.Free...) {
				if d.Amount <= 0 || d.Amount > remaining[d.ID] {
					t.Errorf("amount %d: 묶음 %d 에서 %d 를 뺀다", amount, d.ID, d.Amount)
				}
				total += d.Amount
			}
			if total != amount {
				t.Errorf("amount %d (무료부터=%v): 계획 = %+v", amount, freeFirst, plan)
			}
		}
	}
}

func TestPlanSpendDoesNotOverflowWithHugeBalances(t *testing.T) {
	// 남은 양을 그대로 다 더하면 int64 를 넘어 음수(-2)가 되는 두 묶음이다. 쓸 만큼만 더하므로 넘치지 않는다
	const huge credit.Amount = 9_223_372_036_854_775_807
	for _, freeFirst := range []bool{true, false} {
		plan, err := planSpend(10, lots(huge, huge), grants(huge, huge), freeFirst)
		if err != nil {
			t.Fatalf("오류가 났다: %v", err)
		}
		want := spendPlan{Free: []draw{{1, 10}}}
		if !freeFirst {
			want = spendPlan{Paid: []draw{{101, 10}}}
		}
		if !reflect.DeepEqual(plan, want) {
			t.Errorf("계획 = %+v, 기대 = %+v", plan, want)
		}
	}
}
