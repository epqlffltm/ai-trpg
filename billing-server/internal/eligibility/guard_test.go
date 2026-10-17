// billing-server/internal/eligibility/guard_test.go

package eligibility_test

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// recordingOrders 는 불린 일을 적는 가짜 주문 서비스다.
type recordingOrders struct {
	called []string
}

func (r *recordingOrders) Create(context.Context, uuid.UUID, string, string) (order.Order, bool, error) {
	r.called = append(r.called, "create")
	return order.Order{}, true, nil
}

func (r *recordingOrders) Get(context.Context, uuid.UUID, uuid.UUID) (order.Order, error) {
	r.called = append(r.called, "get")
	return order.Order{}, nil
}

func (r *recordingOrders) Confirm(context.Context, uuid.UUID, uuid.UUID, string) (order.Order, error) {
	r.called = append(r.called, "confirm")
	return order.Order{}, nil
}

func (r *recordingOrders) Refund(context.Context, uuid.UUID, uuid.UUID) (order.Order, error) {
	r.called = append(r.called, "refund")
	return order.Order{}, nil
}

// refusing 은 늘 같은 답을 하는 가짜 확인이다.
type refusing struct{ err error }

func (r refusing) Check(context.Context, uuid.UUID) error { return r.err }

func TestAGuardStopsCreatingAndConfirming(t *testing.T) {
	orders := &recordingOrders{}
	guarded := eligibility.Guard(orders, refusing{err: eligibility.ErrGuardianConsentRequired})
	ctx := context.Background()

	_, _, createErr := guarded.Create(ctx, uuid.New(), "credits-1000", "key")
	_, confirmErr := guarded.Confirm(ctx, uuid.New(), uuid.New(), "fake_ok_1")

	if !errors.Is(createErr, eligibility.ErrGuardianConsentRequired) || !errors.Is(confirmErr, eligibility.ErrGuardianConsentRequired) {
		t.Errorf("만들기 = %v, 승인 = %v", createErr, confirmErr)
	}
	if len(orders.called) != 0 {
		t.Errorf("주문 서비스가 불렸다: %v", orders.called)
	}
}

func TestAGuardLetsReadingAndRefundingThrough(t *testing.T) {
	// 조회와 청약철회는 결제가 아니다. 철회는 돈을 돌려주는 일이다
	orders := &recordingOrders{}
	guarded := eligibility.Guard(orders, refusing{err: eligibility.ErrVerificationRequired})
	ctx := context.Background()

	_, getErr := guarded.Get(ctx, uuid.New(), uuid.New())
	_, refundErr := guarded.Refund(ctx, uuid.New(), uuid.New())

	if getErr != nil || refundErr != nil || len(orders.called) != 2 {
		t.Errorf("조회 = %v, 철회 = %v, 불린 것 = %v", getErr, refundErr, orders.called)
	}
}

func TestAnAllowedUserGoesThrough(t *testing.T) {
	orders := &recordingOrders{}
	guarded := eligibility.Guard(orders, refusing{})
	ctx := context.Background()

	_, _, createErr := guarded.Create(ctx, uuid.New(), "credits-1000", "key")
	_, confirmErr := guarded.Confirm(ctx, uuid.New(), uuid.New(), "fake_ok_1")

	if createErr != nil || confirmErr != nil || len(orders.called) != 2 {
		t.Errorf("만들기 = %v, 승인 = %v, 불린 것 = %v", createErr, confirmErr, orders.called)
	}
}
