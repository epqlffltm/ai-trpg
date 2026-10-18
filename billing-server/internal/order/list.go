// billing-server/internal/order/list.go

package order

import (
	"context"
	"errors"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// MaxListSize 는 주문을 한 번에 읽을 수 있는 가장 많은 수다.
// 한 쪽의 치른 주문마다 청약철회할 수 있는지(그 주문의 크레딧이 줄었는지)를 따로 읽으므로 크게 두지 않는다.
const MaxListSize = 50

// ErrInvalidListRange 는 주문을 읽는 범위가 틀렸다는 오류다.
var ErrInvalidListRange = errors.New("주문을 읽는 범위가 틀렸습니다")

// OrderPage 는 주문 목록의 한 쪽이다(#430).
type OrderPage struct {
	// Orders 는 만든 시각이 늦은 것부터 놓인 주문들이다. 청약철회할 수 있는지와 그 까닭이 적혀 있다.
	Orders []Order
	// NextBefore 는 다음 쪽을 읽을 때 넘길 주문 번호다. 더 읽을 것이 없으면 nil 이다.
	NextBefore *uuid.UUID
}

// List 는 사용자의 주문을 만든 시각이 늦은 것부터 limit 개까지 돌려준다. 상태와 상관없이 모두 싣는다.
// before 가 nil 이면 처음부터, 아니면 그 주문보다 앞선 것부터다. before 가 그 사용자의 주문이 아니면 빈 쪽이다.
func (s *Service) List(ctx context.Context, userID uuid.UUID, before *uuid.UUID, limit int) (OrderPage, error) {
	if limit < 1 || limit > MaxListSize {
		return OrderPage{}, ErrInvalidListRange
	}
	// 하나를 더 읽어서 다음 쪽이 있는지 안다. 개수를 세는 쿼리를 따로 보내지 않는다
	rows, err := s.listRows(ctx, userID, before, int32(limit)+1)
	if err != nil {
		return OrderPage{}, err
	}
	rows, next := cutPage(rows, limit)
	orders, err := s.withRefundabilities(ctx, rows)
	if err != nil {
		return OrderPage{}, err
	}
	return OrderPage{Orders: orders, NextBefore: next}, nil
}

// listRows 는 한 쪽의 주문을 DB 에서 읽는다. before 가 있으면 그 주문보다 앞선 것이다.
func (s *Service) listRows(ctx context.Context, userID uuid.UUID, before *uuid.UUID, rowLimit int32) ([]orderdb.Order, error) {
	queries := orderdb.New(s.pool)
	if before == nil {
		return queries.ListOrdersOfUser(ctx, orderdb.ListOrdersOfUserParams{UserID: userID, RowLimit: rowLimit})
	}
	return queries.ListOrdersOfUserBefore(ctx, orderdb.ListOrdersOfUserBeforeParams{
		Before: *before, UserID: userID, RowLimit: rowLimit,
	})
}

// cutPage 는 하나를 더 읽어 온 결과를 한 쪽으로 자른다. 더 읽어 온 것이 있으면 이 쪽의 마지막 주문이 다음 쪽의 기준이다.
func cutPage(rows []orderdb.Order, limit int) ([]orderdb.Order, *uuid.UUID) {
	if len(rows) <= limit {
		return rows, nil
	}
	rows = rows[:limit]
	next := rows[limit-1].ID
	return rows, &next
}

// withRefundabilities 는 주문마다 지금 청약철회할 수 있는지와 그 까닭을 적는다.
// 기한 안의 치른 주문만 지갑을 읽는다. 그 밖의 주문은 DB 를 부르지 않는다.
func (s *Service) withRefundabilities(ctx context.Context, rows []orderdb.Order) ([]Order, error) {
	orders := make([]Order, 0, len(rows))
	for _, row := range rows {
		current, err := s.withRefundability(ctx, toOrder(row))
		if err != nil {
			return nil, err
		}
		orders = append(orders, current)
	}
	return orders, nil
}
