// billing-server/internal/order/refund.go

package order

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 청약철회(#150 의 2단계). 치른 지 7일(RefundWindow) 안이고 그 주문으로 산 크레딧이 하나도 줄지 않았으면,
// 사용자가 직접 전액을 취소한다. 수수료는 없다. 무료 크레딧은 상관없다.
//
// 승인과 같은 모양으로 나눈다. 결제 대행사를 부르는 동안 트랜잭션을 열어 두지 않는다.
//  1. 한 트랜잭션에서 주문을 refunding 으로 바꾸고 그 주문의 크레딧을 비운다. 그사이에 그 크레딧을 쓸 수 없다
//  2. 결제 대행사에 취소를 요청한다(트랜잭션 밖)
//  3. 답에 따라 적는다. 취소됨 → refunded. 확실한 거절 → 한 트랜잭션에서 paid 로 되돌리고 크레딧을 다시 채운다.
//     답을 받지 못함 → refunding 그대로. 같은 요청을 다시 보내거나 대사가 같은 취소를 다시 보낸다(취소는 다시 보내도 한 번만 된다)

// Refund 는 청약철회를 한다. 끝난 뒤의 주문을 돌려준다.
//
// 돌려받은 주문의 상태로 결과를 안다. refunded 면 돈이 돌아갔고, refunding 이면 아직 결과를 모른다.
// 몇 번을 불러도 한 번만 취소된다. 이미 refunded 면 그대로 돌려준다.
// 결제 대행사가 거절했으면 ErrRefundRefused 를 감싼 오류다. 그때 주문은 paid 로 돌아가 있고 크레딧도 돌아와 있다.
func (s *Service) Refund(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (Order, error) {
	ctx = context.WithoutCancel(ctx)
	started, err := s.startRefunding(ctx, userID, orderID)
	if errors.Is(err, pgx.ErrNoRows) {
		// paid 이고 기한 안인 주문이 아니다. 이미 진행된 환불이거나, 할 수 없는 주문이거나, 없는 주문이다
		return s.resumeRefund(ctx, userID, orderID)
	}
	if err != nil {
		return Order{}, err
	}
	refunded, err := s.cancelAndSettle(ctx, started)
	if err != nil {
		return refunded, err
	}
	return s.withRefundability(ctx, refunded)
}

// startRefunding 은 한 트랜잭션에서 주문을 refunding 으로 바꾸고 그 주문의 크레딧을 비운다.
// 바꿀 주문이 없으면 pgx.ErrNoRows, 크레딧이 줄었으면 ErrCreditsUsed 이고 아무것도 바뀌지 않는다.
// 주문의 줄을 먼저 잠그고 지갑의 줄을 잠근다. 승인(pay)과 같은 차례라 서로를 기다리며 멈추지 않는다.
func (s *Service) startRefunding(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (Order, error) {
	now := s.clock()
	var started Order
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		row, err := orderdb.New(tx).StartRefunding(ctx, orderdb.StartRefundingParams{
			ID: orderID, UserID: userID, Now: now, PaidAfter: now.Add(-RefundWindow),
		})
		if err != nil {
			return err
		}
		started = toOrder(row)
		return s.wallet.TakeForRefund(ctx, tx, userID, orderID)
	})
	if errors.Is(err, wallet.ErrLotUsed) || errors.Is(err, wallet.ErrNoOrderLot) {
		return Order{}, ErrCreditsUsed
	}
	return started, err
}

// resumeRefund 는 paid 에서 refunding 으로 바꾸지 못한 주문에 청약철회가 왔을 때의 처리다.
// refunded 면 그대로 돌려주고, refunding 이면 같은 취소를 다시 보내 마저 끝낸다. 그 밖에는 할 수 없는 까닭을 오류로 알린다.
func (s *Service) resumeRefund(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (Order, error) {
	current, err := s.Get(ctx, userID, orderID)
	if err != nil {
		return Order{}, err
	}
	switch current.Status {
	case StatusRefunded:
		return current, nil
	case StatusRefunding:
		refunded, err := s.cancelAndSettle(ctx, current)
		if err != nil {
			return refunded, err
		}
		return s.withRefundability(ctx, refunded)
	case StatusPaid:
		if !s.clock().Before(*current.RefundableUntil) {
			return current, ErrRefundWindowClosed
		}
		// 기한 안의 paid 인데 바꾸지 못했다. 같은 주문의 다른 요청과 엇갈렸다
		return current, ErrRefundBusy
	default:
		return current, ErrNotRefundable
	}
}

// cancelAndSettle 은 결제 대행사에 취소를 요청하고 답을 주문에 적는다. refunding 인 주문에만 부른다.
func (s *Service) cancelAndSettle(ctx context.Context, current Order) (Order, error) {
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Cancel(ctx, paymentRequest(current))
	})
	return s.settleRefund(ctx, current, result, err)
}

// settleRefund 는 취소의 답을 주문에 적는다. 취소됨이면 refunded, 확실한 거절이면 paid 로 되돌리고 크레딧을 다시 채운다.
// 답을 받지 못했거나 결제 대행사도 아직 모르면 refunding 그대로 돌려준다. 오류가 아니다.
func (s *Service) settleRefund(ctx context.Context, current Order, result payment.Result, askErr error) (Order, error) {
	if askErr != nil {
		// 결제 번호는 적지 않는다. 주문 번호로 찾을 수 있다
		slog.WarnContext(ctx, "결제 대행사의 취소 답을 받지 못했다. 환불 중인 채로 둔다",
			slog.String("operation", "order.refund"),
			slog.String("error_code", "payment.provider_unavailable"),
			slog.String("order_id", current.ID.String()),
			slog.String("error_message", askErr.Error()),
		)
		return current, nil
	}
	switch result.Status {
	case payment.StatusCanceled:
		return s.markRefunded(ctx, current)
	case payment.StatusDeclined:
		return s.restorePaid(ctx, current, result.Code)
	default:
		return current, nil
	}
}

// markRefunded 는 주문을 refunded 로 바꾼다. 다른 요청이 먼저 끝냈으면 아무것도 하지 않는다. 어느 쪽이든 지금의 주문을 돌려준다.
func (s *Service) markRefunded(ctx context.Context, current Order) (Order, error) {
	_, err := orderdb.New(s.pool).MarkRefunded(ctx, orderdb.MarkRefundedParams{ID: current.ID, Now: s.clock()})
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return Order{}, err
	}
	return s.reload(ctx, current.ID)
}

// restorePaid 는 한 트랜잭션에서 주문을 paid 로 되돌리고 비웠던 크레딧을 다시 채운다.
// 다른 요청이 먼저 끝냈으면 아무것도 하지 않는다. 되돌렸으면 결제 대행사의 이유를 담은 ErrRefundRefused 를 함께 돌려준다.
func (s *Service) restorePaid(ctx context.Context, current Order, code string) (Order, error) {
	restored := false
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		_, err := orderdb.New(tx).RestorePaid(ctx, orderdb.RestorePaidParams{ID: current.ID, Now: s.clock()})
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		restored = true
		return s.wallet.ReturnRefund(ctx, tx, current.UserID, current.ID)
	})
	if err != nil {
		return Order{}, err
	}
	reloaded, err := s.reload(ctx, current.ID)
	if err != nil || !restored {
		return reloaded, err
	}
	if code == "" {
		code = FailureCodeUnspecified
	}
	return reloaded, fmt.Errorf("%w(%s)", ErrRefundRefused, code)
}

// withRefundability 는 주문에 지금 청약철회할 수 있는지를 적는다. paid 이고 기한 안이면 그 주문의 크레딧이 줄지 않았는지 본다.
func (s *Service) withRefundability(ctx context.Context, current Order) (Order, error) {
	current.Refundable = false
	if current.Status != StatusPaid || current.RefundableUntil == nil || !s.clock().Before(*current.RefundableUntil) {
		return current, nil
	}
	full, err := s.wallet.OrderLotFull(ctx, current.UserID, current.ID)
	if err != nil {
		return Order{}, err
	}
	current.Refundable = full
	return current, nil
}

// resolveRefund 는 refunding 주문 하나에 같은 취소를 다시 보내 끝낸다(대사). 거절로 되돌린 것은 오류가 아니다.
func (s *Service) resolveRefund(ctx context.Context, current Order) (Order, error) {
	refunded, err := s.cancelAndSettle(ctx, current)
	if errors.Is(err, ErrRefundRefused) {
		return refunded, nil
	}
	return refunded, err
}
