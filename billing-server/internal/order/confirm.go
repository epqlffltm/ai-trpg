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
)

// uniqueViolation 은 PostgreSQL 이 "이미 있는 값"이라고 알리는 오류의 번호(SQLSTATE)다.
const uniqueViolation = "23505"

// Confirm 은 결제 대행사에 결제의 승인을 요청하고, 승인되면 크레딧을 넣는다. 끝난 뒤의 주문을 돌려준다.
//
// 돌려받은 주문의 상태로 결과를 안다. paid 면 크레딧이 들어갔고, failed 면 거절되었고,
// confirming 이면 아직 결과를 모른다. 같은 결제 번호로 다시 부르면 이어서 끝낸다. 몇 번을 불러도 크레딧은 한 번만 들어간다.
//
// 요청을 보낸 쪽이 중간에 연결을 끊어도 멈추지 않는다. 결제 대행사의 답을 받고도 적지 못하는 일을 줄인다.
func (s *Service) Confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	if !paymentKeyPattern.MatchString(paymentKey) {
		return Order{}, ErrInvalidPaymentKey
	}
	ctx = context.WithoutCancel(ctx)

	started, err := s.startConfirming(ctx, userID, orderID, paymentKey)
	if errors.Is(err, pgx.ErrNoRows) {
		// pending 이 아니다. 이미 진행된 주문이거나, 없는 주문이다
		return s.resume(ctx, userID, orderID, paymentKey)
	}
	if err != nil {
		return Order{}, err
	}
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Confirm(ctx, payment.Request{PaymentKey: paymentKey, OrderID: started.ID, Amount: started.Price})
	})
	return s.settle(ctx, started, result, err)
}

// Notify 는 결제 대행사의 알림을 받아, 결과를 모르던 주문을 마저 끝낸다.
// 알림에 적힌 결과를 믿지 않고 결제 대행사에 다시 묻는다. 끝낼 것이 없는 알림(모르는 주문, 이미 끝난 주문,
// 결제 번호가 다른 알림)은 아무것도 하지 않고 nil 을 돌려준다. 결제 대행사가 같은 알림을 여러 번 보내도 된다.
// 결제 대행사에 묻지 못했으면 오류를 돌려준다. 결제 대행사가 알림을 다시 보내게 하려는 것이다.
func (s *Service) Notify(ctx context.Context, orderID uuid.UUID, paymentKey string) error {
	ctx = context.WithoutCancel(ctx)
	row, err := orderdb.New(s.pool).GetOrder(ctx, orderID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return err
	}
	current := toOrder(row)
	if current.Status != StatusConfirming || current.PaymentKey != paymentKey {
		return nil
	}
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Lookup(ctx, paymentKey)
	})
	if err != nil {
		return err
	}
	_, err = s.settle(ctx, current, result, nil)
	return err
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
	return toOrder(row), nil
}

// resume 은 이미 진행된 주문에 같은 승인 요청이 다시 왔을 때의 처리다.
// 끝난 주문이면 그대로 돌려주고, 결과를 모르는 주문이면 결제 대행사에 물어 마저 끝낸다.
func (s *Service) resume(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (Order, error) {
	current, err := s.Get(ctx, userID, orderID)
	if err != nil {
		return Order{}, err
	}
	if current.PaymentKey != paymentKey {
		return Order{}, ErrPaymentKeyMismatch
	}
	if current.Status != StatusConfirming {
		return current, nil
	}
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Lookup(ctx, paymentKey)
	})
	return s.settle(ctx, current, result, err)
}

// askProvider 는 결제 대행사를 부르되 ProviderTimeout 까지만 기다린다.
func (s *Service) askProvider(ctx context.Context, ask func(context.Context) (payment.Result, error)) (payment.Result, error) {
	ctx, cancel := context.WithTimeout(ctx, ProviderTimeout)
	defer cancel()
	return ask(ctx)
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
	default:
		return current, nil
	}
}

// pay 는 주문을 paid 로 바꾸고 크레딧을 넣는다. 둘은 한 트랜잭션이다.
// 다른 요청이 먼저 끝냈으면 아무것도 하지 않는다. 어느 쪽이든 지금의 주문을 돌려준다.
func (s *Service) pay(ctx context.Context, current Order) (Order, error) {
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		_, err := orderdb.New(tx).MarkPaid(ctx, orderdb.MarkPaidParams{ID: current.ID, Now: s.clock()})
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		return s.wallet.DepositForOrder(ctx, tx, current.UserID, current.Credits, current.ID)
	})
	if err != nil {
		return Order{}, err
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
