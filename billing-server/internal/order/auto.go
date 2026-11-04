// billing-server/internal/order/auto.go

package order

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// ErrAutoOrderMismatch 는 같은 번호의 주문이 이미 있는데 자동 충전의 것이 아니거나 내용이 다르다는 오류다. 코드의 잘못이다.
var ErrAutoOrderMismatch = errors.New("같은 번호의 다른 주문이 있습니다")

// AutoPaid 는 자동 충전이 승인받은 결제 하나다.
type AutoPaid struct {
	// ID 는 충전할 일의 번호다. 결제 대행사에 주문 번호로 보낸 것이다.
	ID         uuid.UUID
	UserID     uuid.UUID
	ProductID  string
	Price      int64
	Credits    credit.Amount
	PaymentKey string
}

// RecordAutoPaidInTx 는 자동 충전이 승인받은 결제를 paid 인 주문으로 적고 골드를 넣는다. 부르는 쪽의 트랜잭션 안에서 한다.
// 같은 번호로 다시 부르면 아무것도 하지 않는다(골드도 다시 넣지 않는다). 새로 적었으면 true 다.
// 세는 것(paid 가 된 주문)은 부르는 쪽이 커밋한 뒤에 CountAutoPaid 로 한다.
func (s *Service) RecordAutoPaidInTx(ctx context.Context, tx pgx.Tx, paid AutoPaid) (bool, error) {
	now := s.clock()
	inserted, err := orderdb.New(tx).InsertAutoPaidOrder(ctx, orderdb.InsertAutoPaidOrderParams{
		ID: paid.ID, UserID: paid.UserID, ProductID: paid.ProductID, Price: paid.Price, Credits: paid.Credits,
		IdempotencyKey: autoKey(paid.ID), PaymentKey: pgtype.Text{String: paid.PaymentKey, Valid: true}, Now: now, ExpiresAt: now.Add(s.ttl),
	})
	if err != nil {
		return false, err
	}
	if inserted == 0 {
		return false, s.requireSameAuto(ctx, tx, paid)
	}
	return true, s.wallet.DepositForOrder(ctx, tx, paid.UserID, paid.Credits, paid.ID)
}

// requireSameAuto 는 이미 있는 주문이 같은 자동 충전의 것인지 본다. 아니면 ErrAutoOrderMismatch 다.
func (s *Service) requireSameAuto(ctx context.Context, tx pgx.Tx, paid AutoPaid) error {
	row, err := orderdb.New(tx).GetOrder(ctx, paid.ID)
	if err != nil {
		return err
	}
	if row.Channel != string(ChannelAuto) || row.UserID != paid.UserID || row.PaymentKey.String != paid.PaymentKey {
		return ErrAutoOrderMismatch
	}
	return nil
}

// CountAutoPaid 는 자동 충전으로 paid 가 된 주문을 센다. 커밋한 뒤에 부른다.
func (s *Service) CountAutoPaid(ctx context.Context) {
	s.metrics.became(ctx, StatusPaid, 1)
}

// AutoPaidSince 는 그 사람이 since 뒤에 자동 충전으로 치른 돈의 합(원)이다.
func (s *Service) AutoPaidSince(ctx context.Context, userID uuid.UUID, since time.Time) (int64, error) {
	return orderdb.New(s.pool).SumAutoPaidSince(ctx, orderdb.SumAutoPaidSinceParams{UserID: userID, Since: since})
}

// autoKey 는 자동 충전의 주문에 적는 중복 방지 키다. 웹의 주문은 화면이 보낸 키다. 자동 충전은 번호에서 만든다.
func autoKey(id uuid.UUID) string {
	return "auto-" + id.String()
}
