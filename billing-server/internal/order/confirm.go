// billing-server/internal/order/confirm.go

package order

import (
	"context"
	"errors"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// uniqueViolation 은 PostgreSQL 이 "이미 있는 값"이라고 알리는 오류의 번호(SQLSTATE)다.
const uniqueViolation = "23505"

// Confirm 은 결제 대행사에 결제의 승인을 요청하고, 승인되면 크레딧을 넣는다. 끝난 뒤의 주문을 돌려준다.
//
// 돌려받은 주문의 상태로 결과를 안다. paid 면 크레딧이 들어갔고, failed 면 거절되었고,
// confirming 이면 아직 결과를 모른다. 같은 결제 번호로 다시 부르면 이어서 끝낸다. 몇 번을 불러도 크레딧은 한 번만 들어간다.
//
// 요청을 보낸 쪽이 중간에 연결을 끊어도 멈추지 않는다. 결제 대행사의 답을 받고도 적지 못하는 일을 줄인다.
//
// 작업 전체는 OperationTimeout 안에 끝난다. 넘으면 ErrTimedOut 을 감싼 오류다(detach).
func (s *Service) Confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	ctx, cancel := s.detach(ctx)
	defer cancel()
	confirmed, err := s.confirm(ctx, userID, orderID, paymentKey)
	if err != nil {
		return confirmed, timedOut(ctx, err)
	}
	withRefundability, err := s.withRefundability(ctx, confirmed)
	return withRefundability, timedOut(ctx, err)
}

// confirm 은 Confirm 의 본문이다. 돌려주는 주문에 청약철회할 수 있는지는 아직 적지 않았다.
func (s *Service) confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	if !paymentKeyPattern.MatchString(paymentKey) {
		return Order{}, ErrInvalidPaymentKey
	}

	started, err := s.startConfirming(ctx, userID, orderID, paymentKey)
	if errors.Is(err, pgx.ErrNoRows) {
		// pending 이 아니다. 이미 진행된 주문이거나, 없는 주문이다
		return s.resume(ctx, userID, orderID, paymentKey)
	}
	if err != nil {
		return Order{}, err
	}
	result, err := s.askProvider(ctx, started, func(ctx context.Context, provider payment.Provider) (payment.Result, error) {
		return provider.Confirm(ctx, paymentRequest(started))
	})
	return s.settle(ctx, started, result, err)
}

// startConfirming 은 pending 인 주문에 결제 번호를 적고 confirming 으로 바꾼다. 결제 대행사를 부르기 전에 한다.
// 바꿀 주문이 없으면 pgx.ErrNoRows, 그 결제 번호가 다른 주문에 쓰였으면 ErrPaymentKeyUsed 다.
func (s *Service) startConfirming(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	row, err := orderdb.New(s.pool).StartConfirming(ctx, orderdb.StartConfirmingParams{
		ID:         orderID,
		UserID:     userID,
		PaymentKey: paymentKey,
		Now:        s.clock(),
	})
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation {
		return Order{}, ErrPaymentKeyUsed
	}
	if err != nil {
		return Order{}, err
	}
	s.metrics.became(ctx, StatusConfirming, 1)
	return toOrder(row), nil
}

// resume 은 pending 에서 confirming 으로 바꾸지 못한 주문에 승인 요청이 왔을 때의 처리다.
// 만료된 주문이면 ErrExpired 다. 이미 진행된 주문이면, 끝났으면 그대로 돌려주고 결과를 모르면 결제 대행사에 물어 마저 끝낸다.
func (s *Service) resume(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	current, err := s.Get(ctx, userID, orderID)
	if err != nil {
		return Order{}, err
	}
	if current.Status == StatusPending || current.Status == StatusExpired {
		return current, s.refuseExpired(ctx, current)
	}
	if current.PaymentKey != paymentKey {
		return Order{}, ErrPaymentKeyMismatch
	}
	if current.Status != StatusConfirming {
		return current, nil
	}
	result, err := s.lookUp(ctx, current)
	return s.settle(ctx, current, result, err)
}

// refuseExpired 는 승인을 요청받았지만 confirming 으로 바꾸지 못한 pending·expired 주문을 다룬다.
// 만료 시각이 지났으면 expired 로 적고(정리 작업보다 먼저 왔을 때) ErrExpired 를 돌려준다.
// 만료되지 않은 pending 이면 다른 요청과 엇갈린 것이다. 아주 드물다. 오류 없이 돌려주고, 부르는 쪽이 다시 보내면 된다.
func (s *Service) refuseExpired(ctx context.Context, current Order) error {
	if current.Status == StatusExpired {
		return ErrExpired
	}
	_, err := orderdb.New(s.pool).ExpireOrder(ctx, orderdb.ExpireOrderParams{ID: current.ID, Now: s.clock()})
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return err
	}
	s.metrics.became(ctx, StatusExpired, 1)
	return ErrExpired
}

// lookUp 은 결과를 모르는 주문의 결제를 결제 대행사에 묻는다. 승인을 다시 요청하지 않는다.
func (s *Service) lookUp(ctx context.Context, current Order) (payment.Result, error) {
	return s.askProvider(ctx, current, func(ctx context.Context, provider payment.Provider) (payment.Result, error) {
		return provider.Lookup(ctx, paymentRequest(current))
	})
}

// paymentRequest 는 주문을 결제 대행사에 보내는 모양으로 바꾼다. 금액은 주문에 적힌 값이다. 클라이언트가 보낸 값이 아니다.
// 결제 번호가 적힌 주문(confirming 이후)에만 쓴다.
func paymentRequest(current Order) payment.Request {
	return payment.Request{PaymentKey: current.PaymentKey, OrderID: current.ID, Amount: current.Price}
}

// settle 은 결제 대행사의 답을 주문에 적는다. 승인이면 크레딧을 넣고, 거절이면 실패로 적는다.
// 답을 받지 못했거나(askErr) 결제 대행사도 아직 모르면 주문을 confirming 그대로 돌려준다. 오류가 아니다.
func (s *Service) settle(ctx context.Context, current Order, result payment.Result, askErr error) (Order, error) {
	if askErr != nil {
		// 결제 번호는 적지 않는다. 주문 번호로 찾을 수 있다
		slog.WarnContext(ctx, "결제 대행사의 답을 받지 못했다. 결과를 모르는 채로 둔다",
			slog.String("operation", "order.confirm"),
			slog.String("error_code", "payment.provider_unavailable"),
			slog.String("order_id", current.ID.String()),
			slog.String("error_message", askErr.Error()),
		)
		return current, nil
	}
	switch result.Status {
	case payment.StatusApproved:
		return s.pay(ctx, current)
	case payment.StatusDeclined:
		return s.fail(ctx, current, result.Code)
	case payment.StatusAwaitingDeposit:
		return s.refuseDeposit(ctx, current)
	default:
		return current, nil
	}
}

// pay 는 주문을 paid 로 바꾸고 크레딧을 넣는다. 둘은 한 트랜잭션이다.
// 다른 요청이 먼저 끝냈으면 아무것도 하지 않는다. 어느 쪽이든 지금의 주문을 돌려준다.
func (s *Service) pay(ctx context.Context, current Order) (Order, error) {
	paid := false
	// 지갑이 원장에 적은 일은 커밋한 뒤에 세어진다(txn.Run)
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		_, err := orderdb.New(tx).MarkPaid(ctx, orderdb.MarkPaidParams{ID: current.ID, Now: s.clock()})
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		paid = true
		return s.wallet.DepositForOrder(ctx, tx, current.UserID, current.Credits, current.ID)
	})
	if err != nil {
		return Order{}, err
	}
	// 커밋한 뒤에 센다. 크레딧을 넣지 못해 되돌린 것은 paid 가 아니다
	if paid {
		s.metrics.became(ctx, StatusPaid, 1)
	}
	return s.reload(ctx, current.ID)
}

// fail 은 주문을 failed 로 바꾸고 거절된 이유를 적는다. 다른 요청이 먼저 끝냈으면 아무것도 하지 않는다.
func (s *Service) fail(ctx context.Context, current Order, code string) (Order, error) {
	if code == "" {
		code = FailureCodeUnspecified
	}
	_, err := orderdb.New(s.pool).MarkFailed(ctx, orderdb.MarkFailedParams{
		ID:          current.ID,
		FailureCode: code,
		Now:         s.clock(),
	})
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return Order{}, err
	}
	if err == nil {
		s.metrics.became(ctx, StatusFailed, 1)
	}
	return s.reload(ctx, current.ID)
}

// reload 는 주문을 다시 읽는다. 상태를 바꾼 것이 이 요청이든 다른 요청이든 지금의 값을 돌려주려는 것이다.
func (s *Service) reload(ctx context.Context, orderID uuid.UUID) (Order, error) {
	row, err := orderdb.New(s.pool).GetOrder(ctx, orderID)
	if err != nil {
		return Order{}, err
	}
	return toOrder(row), nil
}
