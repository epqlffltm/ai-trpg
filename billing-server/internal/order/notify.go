// billing-server/internal/order/notify.go

package order

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// Notify 는 결제 대행사의 알림(웹훅)을 받아, 결과를 모르던 주문을 마저 끝낸다.
//
// 알림에 적힌 결과를 믿지 않는다. 주문 번호와 결제 번호로 그 주문을 찾고, 결제 대행사에 다시 묻는다.
//   - confirming: 결과를 조회한다(승인을 다시 요청하지 않는다)
//   - refunding: 같은 취소를 다시 보낸다(취소는 다시 보내도 한 번만 된다)
//
// 끝낼 것이 없는 알림(모르는 주문, 이미 끝난 주문, 결제 번호가 다른 알림)은 결제 대행사를 부르지 않고 nil 이다.
// 서명이 없는 알림(토스페이먼츠)으로 남이 이 주소를 불러도, 결제 대행사를 부르는 것은 진행 중인 주문의 결제 번호를 알 때뿐이다.
// 결제 대행사에 묻지 못했으면 오류를 돌려준다. 결제 대행사가 알림을 다시 보내게 하려는 것이다.
//
// 작업 전체는 OperationTimeout 안에 끝난다. 넘으면 ErrTimedOut 을 감싼 오류다(detach). 결제 대행사가 알림을 다시 보낸다.
func (s *Service) Notify(ctx context.Context, orderID uuid.UUID, paymentKey string) error {
	ctx, cancel := s.detach(ctx)
	defer cancel()
	return timedOut(ctx, s.notify(ctx, orderID, paymentKey))
}

// notify 는 Notify 의 본문이다.
func (s *Service) notify(ctx context.Context, orderID uuid.UUID, paymentKey string) error {
	current, found, err := s.inFlight(ctx, orderID, paymentKey)
	if err != nil || !found {
		return err
	}
	if current.Status == StatusRefunding {
		return s.notifyRefund(ctx, current)
	}
	return s.notifyConfirm(ctx, current)
}

// inFlight 는 결과를 모르는 채로 진행 중인(confirming, refunding) 그 결제의 주문을 찾는다.
// 없거나, 끝났거나, 결제 번호가 다르면 found 가 false 다.
func (s *Service) inFlight(ctx context.Context, orderID uuid.UUID, paymentKey string) (Order, bool, error) {
	row, err := orderdb.New(s.pool).GetOrder(ctx, orderID)
	if errors.Is(err, pgx.ErrNoRows) {
		return Order{}, false, nil
	}
	if err != nil {
		return Order{}, false, err
	}
	current := toOrder(row)
	inFlight := current.Status == StatusConfirming || current.Status == StatusRefunding
	return current, inFlight && current.PaymentKey == paymentKey, nil
}

// notifyConfirm 은 confirming 인 주문의 결과를 결제 대행사에 묻고 적는다.
func (s *Service) notifyConfirm(ctx context.Context, current Order) error {
	result, err := s.lookUp(ctx, current)
	if err != nil {
		return err
	}
	_, err = s.settle(ctx, current, result, nil)
	return err
}

// notifyRefund 는 refunding 인 주문에 같은 취소를 다시 보내고 답을 적는다. 거절되어 되돌린 것은 오류가 아니다.
// 결제 대행사의 답을 받지 못했으면 오류다(대사의 resolveRefund 와 달리 refunding 에 두고 넘어가지 않는다).
func (s *Service) notifyRefund(ctx context.Context, current Order) error {
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Cancel(ctx, paymentRequest(current))
	})
	if err != nil {
		return err
	}
	_, err = s.settleRefund(ctx, current, result, nil)
	if errors.Is(err, ErrRefundRefused) {
		return nil
	}
	return err
}
