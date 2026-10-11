// billing-server/internal/order/create.go

package order

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// Create 는 주문을 만든다. 값과 크레딧의 양은 상품 목록에서 찾는다. 클라이언트가 보낸 값을 쓰지 않는다.
//
// 같은 사용자가 같은 키(idempotencyKey)로 다시 부르면 새로 만들지 않고 먼저 만든 주문을 돌려준다.
// 두 번째 값은 이번에 새로 만들었으면 true 다. 요청이 중간에 끊겨 클라이언트가 다시 보내도 주문이 둘 생기지 않는다.
func (s *Service) Create(ctx context.Context, userID uuid.UUID, productID string, idempotencyKey string) (Order, bool, error) {
	if !idempotencyKeyPattern.MatchString(idempotencyKey) {
		return Order{}, false, ErrInvalidKey
	}
	product, ok := catalog.Find(productID)
	if !ok {
		return Order{}, false, ErrUnknownProduct
	}

	queries := orderdb.New(s.pool)
	row, err := queries.InsertOrder(ctx, orderdb.InsertOrderParams{
		ID:             uuid.New(),
		UserID:         userID,
		ProductID:      product.ID,
		Price:          product.Price,
		Credits:        product.Credits,
		IdempotencyKey: idempotencyKey,
		Now:            s.clock(),
	})
	if err == nil {
		return toOrder(row), true, nil
	}
	// 줄을 돌려받지 못했으면 같은 키의 주문이 이미 있다는 뜻이다
	if !errors.Is(err, pgx.ErrNoRows) {
		return Order{}, false, err
	}
	return existingOrder(ctx, queries, userID, product.ID, idempotencyKey)
}

// existingOrder 는 같은 키로 먼저 만든 주문을 돌려준다. 그 주문의 상품이 이번 요청과 다르면 ErrKeyReused 다.
// 키는 같은데 내용이 다르면 다시 보낸 요청이 아니라 다른 요청이다. 조용히 먼저 것을 돌려주면 클라이언트의 버그를 가린다.
func existingOrder(ctx context.Context, queries *orderdb.Queries, userID uuid.UUID, productID string, idempotencyKey string) (Order, bool, error) {
	row, err := queries.GetOrderByKey(ctx, orderdb.GetOrderByKeyParams{UserID: userID, IdempotencyKey: idempotencyKey})
	if err != nil {
		return Order{}, false, err
	}
	if row.ProductID != productID {
		return Order{}, false, ErrKeyReused
	}
	return toOrder(row), false, nil
}

// Get 은 사용자의 주문 하나를 돌려준다. 없거나 남의 주문이면 ErrNotFound 다.
func (s *Service) Get(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (Order, error) {
	row, err := orderdb.New(s.pool).GetOrderOfUser(ctx, orderdb.GetOrderOfUserParams{ID: orderID, UserID: userID})
	if errors.Is(err, pgx.ErrNoRows) {
		return Order{}, ErrNotFound
	}
	if err != nil {
		return Order{}, err
	}
	return toOrder(row), nil
}

// toOrder 는 DB 의 줄을 이 패키지의 모양으로 바꾼다.
func toOrder(row orderdb.Order) Order {
	order := Order{
		ID:          row.ID,
		UserID:      row.UserID,
		ProductID:   row.ProductID,
		Price:       row.Price,
		Credits:     row.Credits,
		Status:      Status(row.Status),
		PaymentKey:  row.PaymentKey.String,
		FailureCode: row.FailureCode.String,
		CreatedAt:   row.CreatedAt,
	}
	if row.PaidAt.Valid {
		order.PaidAt = &row.PaidAt.Time
	}
	return order
}
