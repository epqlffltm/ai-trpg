// billing-server/internal/sweep/sweep.go

// Package sweep 은 정리 작업의 한 바퀴를 맡는다. 끝이 열린 것을 닫는다.
//
//  1. 만료 시각이 지난 held 홀드를 돌려준다(hold.ExpireDue). 크레딧이 사용자에게 돌아간다.
//  2. 사라질 시각이 지난 무료 크레딧을 원장에 적는다(wallet.ExpireIdle). 변경이 없는 사용자의 것이다.
//  3. 만료 시각이 지난 pending 주문을 expired 로 끝낸다(order.ExpireDue).
//
// 홀드를 먼저 한다. 돌아온 무료 크레딧이 이미 기한이 지났으면 2 에서 함께 적히게 하려는 것이다(실제로는 돌려줄 때 바로 적힌다).
// 셋은 서로 기대지 않는다. 하나가 실패해도 나머지는 한다.
//
// 정리 작업을 둘 띄워도 된다. 모든 변경이 "아직 그 상태일 때만" 바꾸거나(조건이 붙은 UPDATE), 지갑을 잠그거나,
// 다른 쪽이 잠근 줄을 건너뛴다(SKIP LOCKED). 그래서 같은 홀드를 두 번 돌려주지 않는다. 따로 잠금(advisory lock)을 두지 않는다.
package sweep

import (
	"context"
	"errors"
	"fmt"
)

// DefaultLimit 은 한 바퀴에 종류마다 다루는 가장 많은 수다. 밀려 있으면 다음 바퀴가 마저 한다.
// 한 바퀴를 짧게 끊어, 끌 때 오래 기다리지 않고 한 번에 DB 를 오래 붙잡지 않는다.
const DefaultLimit = 500

// Holds 는 만료된 홀드를 돌려주는 것이다. *hold.Service 가 이 모양이다.
type Holds interface {
	ExpireDue(ctx context.Context, limit int) (int, error)
}

// Wallets 는 사라진 무료 크레딧을 원장에 적는 것이다. *wallet.Service 가 이 모양이다.
type Wallets interface {
	ExpireIdle(ctx context.Context, limit int) (int, error)
}

// Orders 는 만료된 주문을 끝내는 것이다. *order.Service 가 이 모양이다.
type Orders interface {
	ExpireDue(ctx context.Context, limit int) (int, error)
}

// Result 는 한 바퀴에서 정리한 수다.
type Result struct {
	// Holds 는 만료되어 돌려준 홀드의 수다.
	Holds int
	// FreeCreditUsers 는 사라진 무료 크레딧을 원장에 적은 사용자의 수다.
	FreeCreditUsers int
	// Orders 는 만료되어 끝낸 주문의 수다.
	Orders int
}

// Any 는 이 바퀴에서 정리한 것이 하나라도 있는지다.
func (r Result) Any() bool {
	return r.Holds > 0 || r.FreeCreditUsers > 0 || r.Orders > 0
}

// Sweeper 는 정리 작업의 한 바퀴를 돈다.
type Sweeper struct {
	holds   Holds
	wallets Wallets
	orders  Orders
	limit   int
}

// New 는 Sweeper 를 만든다. limit 은 한 바퀴에 종류마다 다루는 가장 많은 수다. 0 이하면 DefaultLimit 이다.
func New(holds Holds, wallets Wallets, orders Orders, limit int) *Sweeper {
	if limit <= 0 {
		limit = DefaultLimit
	}
	return &Sweeper{holds: holds, wallets: wallets, orders: orders, limit: limit}
}

// Round 는 한 바퀴를 돈다. 하나가 실패해도 나머지는 하고, 실패한 것들을 묶어 돌려준다. 정리한 수는 오류가 있어도 맞다.
func (s *Sweeper) Round(ctx context.Context) (Result, error) {
	var result Result
	var holdsErr, walletsErr, ordersErr error
	result.Holds, holdsErr = s.holds.ExpireDue(ctx, s.limit)
	result.FreeCreditUsers, walletsErr = s.wallets.ExpireIdle(ctx, s.limit)
	result.Orders, ordersErr = s.orders.ExpireDue(ctx, s.limit)
	return result, errors.Join(
		label("홀드를", holdsErr),
		label("무료 크레딧을", walletsErr),
		label("주문을", ordersErr),
	)
}

// label 은 오류에 무엇을 하다 났는지 붙인다. what 은 조사까지 붙인 말이다(홀드를). 오류가 없으면 nil 이다.
func label(what string, err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s 정리하지 못했습니다: %w", what, err)
}
