// billing-server/internal/wallet/refund.go

package wallet

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// 청약철회(#150)에 쓰는 것들. 주문의 묶음을 통째로 비우고, 결제 대행사가 취소를 거절하면 다시 채운다.
// 둘 다 부르는 쪽(주문)이 연 트랜잭션 안에서 한다. 주문의 상태와 묶음이 함께 바뀌거나 함께 안 바뀐다.

// OrderLotFull 은 그 주문의 묶음이 하나도 줄지 않았는지 본다. 읽기만 한다. 묶음이 없으면 false 다.
// 화면이 환불 단추를 보일지 정하는 데 쓴다. 실제로 비울 때(TakeForRefund)는 지갑을 잠그고 다시 본다.
func (s *Service) OrderLotFull(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (bool, error) {
	lot, err := walletdb.New(s.pool).GetOrderLot(ctx, walletdb.GetOrderLotParams{UserID: userID, OrderID: orderID})
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return lot.Remaining == lot.Amount, nil
}

// TakeForRefund 는 그 주문의 묶음을 비운다. 원장에 refund 줄이 그 묶음을 가리켜 남는다.
// 묶음이 하나도 줄지 않았을 때만 한다. 줄었으면(쓴 것, 홀드로 묶인 것) ErrLotUsed, 묶음이 없으면 ErrNoOrderLot 이고 아무것도 바꾸지 않는다.
func (s *Service) TakeForRefund(ctx context.Context, tx pgx.Tx, userID uuid.UUID, orderID uuid.UUID) error {
	return s.lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		lot, err := c.orderLot(ctx, orderID)
		if err != nil {
			return err
		}
		if lot.Remaining != lot.Amount {
			return ErrLotUsed
		}
		return c.takeFromLot(ctx, because(ReasonRefund), lot.ID, lot.Amount)
	})
}

// ReturnRefund 는 TakeForRefund 로 비운 그 주문의 묶음을 다시 채운다. 원장에 unrefund 줄이 남는다.
// 결제 대행사가 취소를 확실히 거절했을 때만 부른다. 묶음이 비어 있지 않으면 DB 가 막는다(넣은 양을 넘을 수 없다).
func (s *Service) ReturnRefund(ctx context.Context, tx pgx.Tx, userID uuid.UUID, orderID uuid.UUID) error {
	return s.lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		lot, err := c.orderLot(ctx, orderID)
		if err != nil {
			return err
		}
		return c.returnToLot(ctx, because(ReasonUnrefund), lot.ID, lot.Amount)
	})
}

// orderLot 은 지갑을 잠근 채로 그 주문의 묶음을 읽는다. 없으면 ErrNoOrderLot 이다.
func (c change) orderLot(ctx context.Context, orderID uuid.UUID) (walletdb.GetOrderLotRow, error) {
	lot, err := c.queries.GetOrderLot(ctx, walletdb.GetOrderLotParams{UserID: c.userID, OrderID: orderID})
	if errors.Is(err, pgx.ErrNoRows) {
		return walletdb.GetOrderLotRow{}, ErrNoOrderLot
	}
	return lot, err
}
