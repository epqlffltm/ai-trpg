// billing-server/internal/order/stuck.go

package order

import (
	"context"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// StuckAfter 는 결과를 모르는 주문(confirming, refunding)을 사람이 볼 주문으로 보는 때다. 그 상태가 된 때부터 센다.
// 하루면 스스로 끝내는 길(같은 요청을 다시 보냄, 결제 대행사의 알림 일곱 번 가운데 여섯 번, 대사의 조회)이 거의 다 지나갔다.
// 사람이 볼 주문으로 세어도 상태는 그대로이고, 알림과 대사는 계속 끝내려 한다. 끝나면 목록에서 빠진다.
const StuckAfter = 24 * time.Hour

// ListStuck 은 olderThan 보다 오래 confirming·refunding 에 머문 주문을 종류마다 limit 개까지, 오래된 것부터 돌려준다.
// 읽기만 한다. 운영자가 결제 대행사의 상점관리자에서 확인하고 Decide 로 결과를 정한다.
func (s *Service) ListStuck(ctx context.Context, olderThan time.Duration, limit int) ([]Order, error) {
	queries := orderdb.New(s.pool)
	before := s.clock().Add(-olderThan)
	confirming, err := queries.ListStaleConfirming(ctx, orderdb.ListStaleConfirmingParams{Before: before, RowLimit: int32(limit)})
	if err != nil {
		return nil, err
	}
	refunding, err := queries.ListStaleRefunding(ctx, orderdb.ListStaleRefundingParams{Before: before, RowLimit: int32(limit)})
	if err != nil {
		return nil, err
	}
	return toOrders(append(confirming, refunding...)), nil
}

// toOrders 는 DB 의 줄들을 주문들로 바꾼다.
func toOrders(rows []orderdb.Order) []Order {
	orders := make([]Order, 0, len(rows))
	for _, row := range rows {
		orders = append(orders, toOrder(row))
	}
	return orders
}
