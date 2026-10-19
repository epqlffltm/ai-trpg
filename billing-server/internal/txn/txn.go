// billing-server/internal/txn/txn.go

// Package txn 은 "커밋한 뒤에 할 일"을 함께 실어 나르는 트랜잭션을 연다.
//
// 트랜잭션 안에서 한 일은 커밋되기 전까지 일어난 것이 아니다. 그 일을 바로 세면(메트릭) 되돌린 것까지 센다.
// 그래서 트랜잭션 안의 코드는 할 일을 바구니(AfterCommit)에 담기만 하고, 트랜잭션을 연 쪽(Run)이
// 커밋했으면 onCommit 을, 되돌렸으면 onRollback 을 부른다.
//
// 바구니는 트랜잭션(Tx)에 붙어 다닌다. context 에 싣지 않는다. context 는 트랜잭션 밖으로도 흘러서,
// 안에서 따로 연 다른 트랜잭션의 일이 바깥 바구니에 섞일 수 있다.
//
// 이 패키지는 담긴 일이 무엇인지 모른다. 지금은 원장의 메트릭(wallet)이 쓴다.
package txn

import (
	"context"

	"github.com/jackc/pgx/v5"
)

// Beginner 는 트랜잭션을 여는 것이다. *pgxpool.Pool 이 이 모양이다.
type Beginner interface {
	Begin(ctx context.Context) (pgx.Tx, error)
}

// Tx 는 바구니가 붙은 트랜잭션이다. pgx.Tx 를 그대로 품어서 pgx.Tx 를 받는 곳(sqlc 의 Queries 등)에 그대로 넘긴다.
type Tx struct {
	pgx.Tx
	basket *basket
}

// hook 은 바구니에 담긴 일 하나다.
type hook struct {
	onCommit   func(context.Context)
	onRollback func(context.Context)
}

// basket 은 한 트랜잭션에 담긴 일들이다. 한 트랜잭션은 한 고루틴에서 돌므로 잠그지 않는다.
type basket struct {
	hooks []hook
}

// Run 은 트랜잭션을 열고 fn 을 부른다. fn 이 오류 없이 끝나면 커밋하고, 아니면 되돌린다(pgx.BeginFunc 와 같다).
// 커밋했으면 담긴 일의 onCommit 을, 되돌렸거나 커밋하지 못했으면 onRollback 을 담긴 차례로 부른다.
// 커밋이 실패한 것도 되돌린 것으로 친다. 커밋됐는지 모르는 것을 일어났다고 세지 않는다.
func Run(ctx context.Context, db Beginner, fn func(tx pgx.Tx) error) error {
	b := &basket{}
	err := pgx.BeginFunc(ctx, db, func(tx pgx.Tx) error {
		return fn(Tx{Tx: tx, basket: b})
	})
	b.finish(ctx, err == nil)
	return err
}

// AfterCommit 은 tx 가 커밋되면 onCommit 을, 되돌려지면 onRollback 을 부르게 담는다. 둘 다 nil 이어도 된다.
// tx 가 Run 으로 연 것이 아니면 담지 못하고 false 다. 그때 담으려던 일은 일어나지 않는다.
func AfterCommit(tx pgx.Tx, onCommit, onRollback func(context.Context)) bool {
	carrier, ok := tx.(Tx)
	if !ok || carrier.basket == nil {
		return false
	}
	carrier.basket.hooks = append(carrier.basket.hooks, hook{onCommit: onCommit, onRollback: onRollback})
	return true
}

// finish 는 담긴 일을 끝난 결과에 맞춰 부른다.
func (b *basket) finish(ctx context.Context, committed bool) {
	for _, h := range b.hooks {
		run := h.onRollback
		if committed {
			run = h.onCommit
		}
		if run != nil {
			run(ctx)
		}
	}
}
