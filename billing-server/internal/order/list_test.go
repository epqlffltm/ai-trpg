// billing-server/internal/order/list_test.go

// 사용자의 주문 목록(#430). 실제 PostgreSQL 에서 돈다.
package order_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// list 는 이 사용자의 주문 한 쪽을 읽는다. 읽지 못하면 테스트를 멈춘다.
func (f fixture) list(before *uuid.UUID, limit int) order.OrderPage {
	f.t.Helper()
	page, err := f.service.List(ctx(f.t), f.user, before, limit)
	if err != nil {
		f.t.Fatalf("주문 목록을 읽지 못했다: %v", err)
	}
	return page
}

// orderIDs 는 한 쪽의 주문 번호들이다.
func orderIDs(page order.OrderPage) []uuid.UUID {
	list := make([]uuid.UUID, 0, len(page.Orders))
	for _, current := range page.Orders {
		list = append(list, current.ID)
	}
	return list
}

// sameIDs 는 두 목록이 같은 차례의 같은 번호인지 본다.
func sameIDs(got []uuid.UUID, want ...uuid.UUID) bool {
	if len(got) != len(want) {
		return false
	}
	for index := range want {
		if got[index] != want[index] {
			return false
		}
	}
	return true
}

func TestAUserWithoutOrdersHasAnEmptyList(t *testing.T) {
	f := setUp(t, approving())

	page := f.list(nil, 20)

	if len(page.Orders) != 0 || page.NextBefore != nil {
		t.Errorf("목록 = %+v. 비어 있어야 한다", page)
	}
}

func TestOrdersComeNewestFirstWhateverTheirStatus(t *testing.T) {
	f := setUp(t, approving())
	first := f.paid()
	f.clock.Advance(time.Minute)
	second := f.create()
	f.clock.Advance(time.Minute)
	third := f.create()

	page := f.list(nil, 20)

	if !sameIDs(orderIDs(page), third.ID, second.ID, first.ID) || page.NextBefore != nil {
		t.Errorf("목록 = %v, 다음 = %v. 늦게 만든 것부터 셋이어야 한다", orderIDs(page), page.NextBefore)
	}
	if page.Orders[2].Status != order.StatusPaid || page.Orders[0].Status != order.StatusPending {
		t.Errorf("상태 = %s, %s", page.Orders[2].Status, page.Orders[0].Status)
	}
}

func TestOrdersAreReadPageByPage(t *testing.T) {
	f := setUp(t, approving())
	var made []uuid.UUID
	for range 5 {
		made = append(made, f.create().ID)
		f.clock.Advance(time.Minute)
	}

	first := f.list(nil, 2)
	second := f.list(first.NextBefore, 2)
	third := f.list(second.NextBefore, 2)

	if !sameIDs(orderIDs(first), made[4], made[3]) || first.NextBefore == nil || *first.NextBefore != made[3] {
		t.Errorf("첫 쪽 = %v, 다음 = %v", orderIDs(first), first.NextBefore)
	}
	if !sameIDs(orderIDs(second), made[2], made[1]) || second.NextBefore == nil {
		t.Errorf("둘째 쪽 = %v, 다음 = %v", orderIDs(second), second.NextBefore)
	}
	// 마지막 쪽은 다음이 없다. 딱 맞게 끝나도(하나 남음) 더 읽지 않게 한다
	if !sameIDs(orderIDs(third), made[0]) || third.NextBefore != nil {
		t.Errorf("셋째 쪽 = %v, 다음 = %v", orderIDs(third), third.NextBefore)
	}
}

func TestAPageThatEndsExactlyHasNoNext(t *testing.T) {
	f := setUp(t, approving())
	f.create()
	f.clock.Advance(time.Minute)
	f.create()

	page := f.list(nil, 2)

	if len(page.Orders) != 2 || page.NextBefore != nil {
		t.Errorf("목록 = %v, 다음 = %v. 둘이고 다음이 없어야 한다", orderIDs(page), page.NextBefore)
	}
}

func TestOrdersMadeAtTheSameMomentKeepAnOrder(t *testing.T) {
	// 시계를 돌리지 않는다. 같은 시각이면 번호로 차례를 정한다. 쪽을 넘겨도 겹치거나 빠지지 않는다
	f := setUp(t, approving())
	seen := map[uuid.UUID]bool{}
	for range 4 {
		f.create()
	}

	var before *uuid.UUID
	for range 4 {
		page := f.list(before, 1)
		for _, id := range orderIDs(page) {
			if seen[id] {
				t.Fatalf("주문 %s 가 두 번 나왔다", id)
			}
			seen[id] = true
		}
		before = page.NextBefore
	}

	if len(seen) != 4 || before != nil {
		t.Errorf("읽은 주문 = %d 개, 다음 = %v. 넷을 한 번씩 읽어야 한다", len(seen), before)
	}
}

func TestAnotherUsersOrdersAreNotListed(t *testing.T) {
	f := setUp(t, approving())
	other := setUpAt(t, f.pool, startedAt, approving())
	theirs := other.create()
	mine := f.create()

	page := f.list(nil, 20)

	if !sameIDs(orderIDs(page), mine.ID) {
		t.Errorf("목록 = %v. 내 주문 하나여야 한다", orderIDs(page))
	}
	// 남의 주문 번호를 기준으로 넘겨도 아무것도 나오지 않는다. 그 주문이 있는지도 알려 주지 않는다
	if after := f.list(&theirs.ID, 20); len(after.Orders) != 0 || after.NextBefore != nil {
		t.Errorf("남의 주문 뒤의 목록 = %v", orderIDs(after))
	}
}

func TestListedOrdersSayWhetherAndWhyTheyCanBeRefunded(t *testing.T) {
	f := setUp(t, approving())
	used := f.paid()
	if err := f.wallet.Spend(ctx(t), f.user, 1); err != nil {
		t.Fatalf("크레딧을 쓰지 못했다: %v", err)
	}
	f.clock.Advance(time.Minute)
	pending := f.create()

	page := f.list(nil, 20)

	if !sameIDs(orderIDs(page), pending.ID, used.ID) {
		t.Fatalf("목록 = %v", orderIDs(page))
	}
	if got := page.Orders[1]; got.Refundable || got.RefundBlocked != order.RefundBlockCreditsUsed {
		t.Errorf("쓴 주문 = %v, %q. credits_used 여야 한다", got.Refundable, got.RefundBlocked)
	}
	if got := page.Orders[0]; got.Refundable || got.RefundBlocked != "" {
		t.Errorf("치르지 않은 주문 = %v, %q", got.Refundable, got.RefundBlocked)
	}

	f.clock.Advance(order.RefundWindow)
	if got := f.list(nil, 20).Orders[1]; got.RefundBlocked != order.RefundBlockWindowClosed {
		t.Errorf("7일 뒤의 쓴 주문 = %q. window_closed 여야 한다", got.RefundBlocked)
	}
}

func TestAListOutOfRangeIsRefused(t *testing.T) {
	f := setUp(t, approving())

	for _, limit := range []int{0, -1, order.MaxListSize + 1} {
		if _, err := f.service.List(ctx(t), f.user, nil, limit); !errors.Is(err, order.ErrInvalidListRange) {
			t.Errorf("limit %d: 오류 = %v", limit, err)
		}
	}
	if _, err := f.service.List(ctx(t), f.user, nil, order.MaxListSize); err != nil {
		t.Errorf("가장 큰 쪽을 읽지 못했다: %v", err)
	}
}
