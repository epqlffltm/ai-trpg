// billing-server/internal/eligibility/guard.go

package eligibility

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// Orders 는 사용자가 부르는 주문의 일이다. *order.Service 가 이 모양이다(httpapi.OrderService 와 같다).
type Orders interface {
	Create(ctx context.Context, userID uuid.UUID, productID string, idempotencyKey string) (order.Order, bool, error)
	Get(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (order.Order, error)
	Confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (order.Order, error)
	Refund(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (order.Order, error)
}

// Checker 는 결제할 수 있는지 보는 것이다. *Service 가 이 모양이다.
type Checker interface {
	Check(ctx context.Context, userID uuid.UUID) error
}

// Guarded 는 결제 자격을 먼저 보는 주문의 일이다. 주문을 만들 때와 승인을 요청할 때 본다.
//
// 승인 때 다시 보는 까닭: 주문은 하루 동안 열려 있다. 그 사이에 보호자가 동의를 철회할 수 있다.
// 승인을 요청하기 전에 막으면 결제 대행사가 돈을 가져가지 않는다(결제창에서 인증한 것은 승인 전까지 청구되지 않는다).
// 조회와 청약철회는 막지 않는다. 철회는 돈을 돌려주는 일이다.
// 결제 대행사의 알림(가상계좌의 입금)은 이 층을 지나지 않는다. 승인 때 이미 보았다.
//
// 주문 패키지에 넣지 않고 감싸는 까닭: 주문은 "무엇을 얼마에 어떻게 치르는가"를 맡고, 누가 결제할 수 있는가는 따로 바뀐다.
// 정리 작업과 대사는 감싸지 않은 주문 서비스를 그대로 쓴다.
type Guarded struct {
	Orders
	checker Checker
}

// Guard 는 orders 를 결제 자격으로 감싼다.
func Guard(orders Orders, checker Checker) Guarded {
	return Guarded{Orders: orders, checker: checker}
}

// Create 는 결제할 수 있는 사용자의 주문만 만든다.
func (g Guarded) Create(ctx context.Context, userID uuid.UUID, productID string, idempotencyKey string) (order.Order, bool, error) {
	if err := g.checker.Check(ctx, userID); err != nil {
		return order.Order{}, false, err
	}
	return g.Orders.Create(ctx, userID, productID, idempotencyKey)
}

// Confirm 은 결제할 수 있는 사용자의 승인만 요청한다.
func (g Guarded) Confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (order.Order, error) {
	if err := g.checker.Check(ctx, userID); err != nil {
		return order.Order{}, err
	}
	return g.Orders.Confirm(ctx, userID, orderID, paymentKey)
}
