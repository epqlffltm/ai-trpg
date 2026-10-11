// billing-server/internal/wallet/plan.go

package wallet

import "github.com/epqlffltm/ai-trpg/billing-server/internal/credit"

// 크레딧을 어디서 얼마씩 뺄지 정하는 계산이다. DB 를 건드리지 않는다. 같은 입력에는 늘 같은 답이 나온다.

// openGrant 는 아직 쓸 수 있는 무료 크레딧의 지급 묶음 하나다.
type openGrant struct {
	ID        int64
	Remaining credit.Amount
}

// grantDraw 는 지급 묶음 하나에서 뺄 양이다.
type grantDraw struct {
	GrantID int64
	Amount  credit.Amount
}

// spendPlan 은 크레딧을 쓸 때 어디서 얼마씩 뺄지다. Paid 와 Free 의 양을 모두 더하면 쓰려던 양이다.
type spendPlan struct {
	// Paid 는 산 크레딧에서 뺄 양이다. 0 일 수 있다.
	Paid credit.Amount
	// Free 는 지급 묶음마다 뺄 양이다. 0 인 것은 넣지 않는다.
	Free []grantDraw
}

// planSpend 는 amount 를 산 크레딧(paid)과 무료 크레딧(grants)에서 어떻게 뺄지 정한다.
// grants 는 먼저 사라지는 것부터 놓여 있어야 한다. 가진 것이 모자라면 ErrInsufficient 다.
func planSpend(amount credit.Amount, paid credit.Amount, grants []openGrant, freeFirst bool) (spendPlan, error) {
	free := usableFree(grants, amount)
	// free 는 amount 를 넘지 않으므로 amount-free 는 0 이상이다. paid+free 처럼 더하지 않아서 넘칠 일이 없다
	if paid < amount-free {
		return spendPlan{}, ErrInsufficient
	}
	fromFree, fromPaid := split(amount, paid, free, freeFirst)
	return spendPlan{Paid: fromPaid, Free: drawFromGrants(grants, fromFree)}, nil
}

// usableFree 는 무료 크레딧 가운데 이번에 쓸 수 있는 양이다. 남은 양의 합이되 limit 를 넘지 않는다.
func usableFree(grants []openGrant, limit credit.Amount) credit.Amount {
	var total credit.Amount
	for _, grant := range grants {
		total += min(grant.Remaining, limit-total)
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

// drawFromGrants 는 amount 를 지급 묶음들에서 앞에서부터 차례로 뺀다. 앞의 묶음을 다 써야 다음 묶음으로 넘어간다.
func drawFromGrants(grants []openGrant, amount credit.Amount) []grantDraw {
	var draws []grantDraw
	for _, grant := range grants {
		if amount == 0 {
			break
		}
		take := min(grant.Remaining, amount)
		draws = append(draws, grantDraw{GrantID: grant.ID, Amount: take})
		amount -= take
	}
	return draws
}
