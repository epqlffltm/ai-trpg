// billing-server/internal/wallet/plan.go

package wallet

import "github.com/epqlffltm/ai-trpg/billing-server/internal/credit"

// 크레딧을 어디서 얼마씩 뺄지 정하는 계산이다. DB 를 건드리지 않는다. 같은 입력에는 늘 같은 답이 나온다.
//
// 산 크레딧과 무료 크레딧 모두 묶음으로 있다. 산 크레딧은 주문마다(paid_lots), 무료 크레딧은 지급마다(free_grants)다.
// 같은 종류 안에서는 앞에 놓인 묶음부터 뺀다. 산 크레딧은 먼저 들어온 것, 무료 크레딧은 먼저 사라지는 것이 앞이다.

// bucket 은 아직 남은 것이 있는 묶음 하나다. 산 크레딧의 묶음이든 무료 크레딧의 지급 묶음이든 같은 모양이다.
type bucket struct {
	ID        int64
	Remaining credit.Amount
}

// draw 는 묶음 하나에서 뺄 양이다.
type draw struct {
	ID     int64
	Amount credit.Amount
}

// spendPlan 은 크레딧을 쓸 때 어디서 얼마씩 뺄지다. 모든 draw 의 양을 더하면 쓰려던 양이다. 0 인 draw 는 넣지 않는다.
type spendPlan struct {
	// Paid 는 산 크레딧의 묶음마다 뺄 양이다.
	Paid []draw
	// Free 는 무료 크레딧의 지급 묶음마다 뺄 양이다.
	Free []draw
}

// planSpend 는 amount 를 산 크레딧의 묶음(lots)과 무료 크레딧의 지급 묶음(grants)에서 어떻게 뺄지 정한다.
// lots 는 먼저 들어온 것부터, grants 는 먼저 사라지는 것부터 놓여 있어야 한다. 가진 것이 모자라면 ErrInsufficient 다.
func planSpend(amount credit.Amount, lots []bucket, grants []bucket, freeFirst bool) (spendPlan, error) {
	free := usable(grants, amount)
	paid := usable(lots, amount)
	// 둘 다 amount 를 넘지 않으므로 amount-free 는 0 이상이다. paid+free 처럼 더하지 않아서 넘칠 일이 없다
	if paid < amount-free {
		return spendPlan{}, ErrInsufficient
	}
	fromFree, fromPaid := split(amount, paid, free, freeFirst)
	return spendPlan{Paid: drawFrom(lots, fromPaid), Free: drawFrom(grants, fromFree)}, nil
}

// usable 은 묶음들 가운데 이번에 쓸 수 있는 양이다. 남은 양의 합이되 limit 를 넘지 않는다.
func usable(buckets []bucket, limit credit.Amount) credit.Amount {
	var total credit.Amount
	for _, b := range buckets {
		total += min(b.Remaining, limit-total)
	}
	return total
}

// split 은 amount 를 무료 크레딧과 산 크레딧에 나눈다. 먼저 쓰는 쪽에서 되는 만큼 빼고 나머지를 다른 쪽에서 뺀다.
// 가진 것이 모자라지 않다는 것은 부르는 쪽이 확인했다.
func split(amount credit.Amount, paid credit.Amount, free credit.Amount, freeFirst bool) (fromFree, fromPaid credit.Amount) {
	if freeFirst {
		fromFree = min(amount, free)
		return fromFree, amount - fromFree
	}
	fromPaid = min(amount, paid)
	return amount - fromPaid, fromPaid
}

// drawFrom 은 amount 를 묶음들에서 앞에서부터 차례로 뺀다. 앞의 묶음을 다 써야 다음 묶음으로 넘어간다.
func drawFrom(buckets []bucket, amount credit.Amount) []draw {
	var draws []draw
	for _, b := range buckets {
		if amount == 0 {
			break
		}
		take := min(b.Remaining, amount)
		draws = append(draws, draw{ID: b.ID, Amount: take})
		amount -= take
	}
	return draws
}
