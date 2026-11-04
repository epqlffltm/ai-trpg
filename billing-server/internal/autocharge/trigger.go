// billing-server/internal/autocharge/trigger.go

package autocharge

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 떨어진 것 적기(#980 의 둘째 단계). 홀드를 거는 트랜잭션이 골드를 뺀 뒤에 부른다(hold.Service.WithLowBalance).
// 지갑이 잠긴 채라서 한 사람의 홀드들은 차례로 지나간다. 그래서 같은 사람의 일이 둘 적히지 않는다.
//
// 한 번 떨어지면 한 번만 산다. 설정의 armed 가 그 표시다.
//   - 켜져 있고(enabled) armed 이고 골드가 기준 아래면: 충전할 일을 적고 armed 를 끈다
//   - 골드가 기준 이상이면: armed 를 켠다(다음에 떨어질 때 산다)
//   - 그 밖에는 아무것도 하지 않는다. 결제가 실패한 뒤 골드가 그대로 기준 아래면 다시 적지 않는다(다시 하지 않고 알린다)
//
// 결제 대행사는 부르지 않는다. 적어 둔 일은 따로 도는 작업(cmd/autocharge)이 결제한다.

// Decision 은 떨어진 것을 본 뒤에 할 일이다. 규칙만이다. DB 를 보지 않는다.
type Decision int

const (
	// DecideNothing 은 아무것도 하지 않는다는 것이다.
	DecideNothing Decision = iota
	// DecideArm 은 armed 를 켠다는 것이다. 골드가 기준 이상이다.
	DecideArm
	// DecideCharge 는 충전할 일을 적고 armed 를 끈다는 것이다.
	DecideCharge
)

// Decide 는 설정과 지금의 골드로 할 일을 정한다.
func Decide(enabled bool, armed bool, threshold credit.Amount, paid credit.Amount) Decision {
	switch {
	case !enabled:
		return DecideNothing
	case paid >= threshold:
		if armed {
			return DecideNothing
		}
		return DecideArm
	case armed:
		return DecideCharge
	default:
		return DecideNothing
	}
}

// NoteBalanceInTx 는 골드를 뺀 뒤의 잔액을 보고, 정한 대로 충전할 일을 적거나 armed 를 켠다. 부르는 쪽의 트랜잭션 안에서 한다.
// 설정이 없으면 아무것도 하지 않는다. 일을 적었으면 true 다.
func (s *Service) NoteBalanceInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (bool, error) {
	queries := autochargedb.New(tx)
	row, err := queries.GetTrigger(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	switch Decide(row.Enabled, row.Armed, row.Threshold, credit.Amount(row.Paid)) {
	case DecideArm:
		return false, queries.SetArmed(ctx, autochargedb.SetArmedParams{UserID: userID, Armed: true})
	case DecideCharge:
		return s.queueCharge(ctx, queries, userID, row.ProductID)
	default:
		return false, nil
	}
}

// queueCharge 는 충전할 일을 적고 armed 를 끈다. 끝나지 않은 일이 이미 있으면 적지 않는다(armed 는 끈다).
// 상품의 값은 지금의 목록에서 옮겨 적는다. 목록에서 없어진 상품이면 적지 않는다.
func (s *Service) queueCharge(ctx context.Context, queries *autochargedb.Queries, userID uuid.UUID, productID string) (bool, error) {
	if err := queries.SetArmed(ctx, autochargedb.SetArmedParams{UserID: userID, Armed: false}); err != nil {
		return false, err
	}
	product, ok := catalog.Find(productID)
	if !ok {
		return false, nil
	}
	now := s.clock()
	inserted, err := queries.InsertRequest(ctx, autochargedb.InsertRequestParams{
		ID: uuid.New(), UserID: userID, ProductID: product.ID, Price: product.Price, Credits: product.Credits, Now: now,
	})
	return inserted > 0, err
}
