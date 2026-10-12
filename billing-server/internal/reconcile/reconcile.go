// billing-server/internal/reconcile/reconcile.go

// Package reconcile 은 하루 한 번 도는 대사(對査)다. 장부가 맞는지 보고, 결과를 모르는 채로 남은 주문을 끝낸다.
//
//  1. 오래 confirming 에 머문 주문을 결제 대행사에 물어 끝낸다(order.ResolveStale). 이것만 상태를 바꾼다.
//  2. "지금의 값"과 원장이 맞는지 본다. 읽기만 한다. 맞지 않는 줄의 번호를 돌려줄 뿐 고치지 않는다.
//     원장은 지울 수 없고, 무엇이 맞는지는 사람이 정한다.
//  3. 정리 작업이 밀려 있지 않은지 센다(만료 시각이 한참 지났는데 아직 끝나지 않은 것).
//
// 2 의 검사는 한 트랜잭션(REPEATABLE READ, READ ONLY)에서 한다. 검사들이 같은 순간의 장부를 보고, DB 가 쓰기를 막는다.
package reconcile

import (
	"context"
	"errors"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/reconcile/reconciledb"
)

// 검사의 이름. 로그의 check 칸에 적힌다. 정해진 수의 이름만 쓴다.
const (
	// CheckPaidBalance 는 지갑의 산 크레딧이 원장의 paid 줄의 합과 같은지다. 번호는 사용자다.
	CheckPaidBalance = "paid_balance"
	// CheckGrantRemaining 은 무료 크레딧 묶음의 남은 양이 그 묶음을 가리키는 원장 줄의 합과 같은지다. 번호는 지급 묶음이다.
	CheckGrantRemaining = "grant_remaining"
	// CheckPaidOrderDeposit 은 치른 주문마다 크레딧이 그만큼 들어왔는지다. 번호는 주문이다.
	CheckPaidOrderDeposit = "paid_order_deposit"
	// CheckDepositOrder 는 주문으로 들어온 크레딧마다 그 주문이 치른 상태인지다. 번호는 원장의 줄이다.
	CheckDepositOrder = "deposit_order"
	// CheckHoldLines 는 홀드의 상태와 원장의 줄(빠진 것, 돌아온 것)이 맞는지다. 번호는 홀드다.
	CheckHoldLines = "hold_lines"
)

// DefaultLimit 은 검사마다 돌려주는 맞지 않는 줄의 가장 많은 수다. 그보다 많으면 무언가 크게 잘못된 것이다. 다 볼 필요가 없다.
const DefaultLimit = 1000

// StaleResolver 는 오래된 confirming 주문을 끝내는 것이다. *order.Service 가 이 모양이다.
type StaleResolver interface {
	ResolveStale(ctx context.Context, olderThan time.Duration, limit int) (order.StaleReport, error)
}

// Mismatch 는 맞지 않는 줄 하나다.
type Mismatch struct {
	// Check 는 어느 검사에서 걸렸는지다(CheckPaidBalance 같은 것).
	Check string
	// ID 는 걸린 줄의 번호다. 무엇의 번호인지는 검사마다 다르다.
	ID string
}

// Overdue 는 정리 작업이 아직 손대지 못한 것의 수다. 기준 시각보다 먼저 만료된 것만 센다.
type Overdue struct {
	Holds      int64
	Orders     int64
	FreeGrants int64
}

// Any 는 밀린 것이 하나라도 있는지다.
func (o Overdue) Any() bool {
	return o.Holds > 0 || o.Orders > 0 || o.FreeGrants > 0
}

// Report 는 대사 한 번의 결과다.
type Report struct {
	Stale      order.StaleReport
	Mismatches []Mismatch
	Overdue    Overdue
}

// Clean 은 장부에 맞지 않는 줄이 없는지다.
func (r Report) Clean() bool {
	return len(r.Mismatches) == 0
}

// Options 는 대사 한 번을 어떻게 할지다.
type Options struct {
	// StaleAfter 는 confirming 에 이만큼 머문 주문을 결제 대행사에 묻는다. 정리 작업이 밀렸다고 볼 때도 이만큼 지난 것만 센다.
	StaleAfter time.Duration
	// Limit 은 검사마다, 그리고 결제 대행사에 물을 주문의 가장 많은 수다. 0 이하면 DefaultLimit 이다.
	Limit int
}

// Reconciler 는 대사를 한다.
type Reconciler struct {
	pool   *pgxpool.Pool
	orders StaleResolver
	now    func() time.Time
}

// New 는 Reconciler 를 만든다. now 는 지금 시각을 돌려주는 함수다.
func New(pool *pgxpool.Pool, orders StaleResolver, now func() time.Time) *Reconciler {
	return &Reconciler{pool: pool, orders: orders, now: now}
}

// Run 은 대사를 한 번 한다. 주문을 끝내다 오류가 나도 검사는 한다. 오류들은 묶어 돌려준다.
// 검사를 하지 못했으면 Report 의 Mismatches 가 비어 있어도 깨끗하다는 뜻이 아니다. 오류를 먼저 본다.
func (r *Reconciler) Run(ctx context.Context, options Options) (Report, error) {
	limit := options.Limit
	if limit <= 0 {
		limit = DefaultLimit
	}
	var report Report
	var staleErr, checkErr error
	report.Stale, staleErr = r.orders.ResolveStale(ctx, options.StaleAfter, limit)
	checkErr = r.readOnly(ctx, func(queries *reconciledb.Queries) error {
		var err error
		if report.Mismatches, err = runChecks(ctx, queries, int32(limit)); err != nil {
			return err
		}
		report.Overdue, err = countOverdue(ctx, queries, r.now().Add(-options.StaleAfter))
		return err
	})
	return report, errors.Join(staleErr, checkErr)
}

// readOnly 는 읽기만 하는 트랜잭션 하나에서 read 를 한다.
func (r *Reconciler) readOnly(ctx context.Context, read func(*reconciledb.Queries) error) error {
	options := pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly}
	return pgx.BeginTxFunc(ctx, r.pool, options, func(tx pgx.Tx) error {
		return read(reconciledb.New(tx))
	})
}

// check 는 검사 하나다. 맞지 않는 줄의 번호를 글자로 돌려준다.
type check struct {
	name string
	find func(ctx context.Context, queries *reconciledb.Queries, limit int32) ([]string, error)
}

// checks 는 하는 검사들이다.
var checks = []check{
	{CheckPaidBalance, func(ctx context.Context, q *reconciledb.Queries, limit int32) ([]string, error) {
		return uuidStrings(q.PaidBalanceMismatches(ctx, limit))
	}},
	{CheckGrantRemaining, func(ctx context.Context, q *reconciledb.Queries, limit int32) ([]string, error) {
		return intStrings(q.GrantRemainingMismatches(ctx, limit))
	}},
	{CheckPaidOrderDeposit, func(ctx context.Context, q *reconciledb.Queries, limit int32) ([]string, error) {
		return uuidStrings(q.PaidOrdersWithoutDeposit(ctx, limit))
	}},
	{CheckDepositOrder, func(ctx context.Context, q *reconciledb.Queries, limit int32) ([]string, error) {
		return intStrings(q.DepositsWithoutPaidOrder(ctx, limit))
	}},
	{CheckHoldLines, func(ctx context.Context, q *reconciledb.Queries, limit int32) ([]string, error) {
		return uuidStrings(q.HoldLineMismatches(ctx, limit))
	}},
}

// runChecks 는 검사들을 차례로 하고, 걸린 줄들을 모은다. 검사 하나라도 하지 못하면 오류다.
func runChecks(ctx context.Context, queries *reconciledb.Queries, limit int32) ([]Mismatch, error) {
	var found []Mismatch
	for _, c := range checks {
		ids, err := c.find(ctx, queries, limit)
		if err != nil {
			return nil, err
		}
		for _, id := range ids {
			found = append(found, Mismatch{Check: c.name, ID: id})
		}
	}
	return found, nil
}

// countOverdue 는 before 보다 먼저 만료되었는데 아직 정리되지 않은 것을 센다.
func countOverdue(ctx context.Context, queries *reconciledb.Queries, before time.Time) (Overdue, error) {
	row, err := queries.CountOverdue(ctx, before.UTC())
	if err != nil {
		return Overdue{}, err
	}
	return Overdue{Holds: row.HeldHolds, Orders: row.PendingOrders, FreeGrants: row.FreeGrants}, nil
}

// uuidStrings 는 UUID 들을 글자로 바꾼다. 앞의 오류를 그대로 넘긴다.
func uuidStrings(ids []uuid.UUID, err error) ([]string, error) {
	if err != nil {
		return nil, err
	}
	out := make([]string, len(ids))
	for i, id := range ids {
		out[i] = id.String()
	}
	return out, nil
}

// intStrings 는 숫자 번호들을 글자로 바꾼다. 앞의 오류를 그대로 넘긴다.
func intStrings(ids []int64, err error) ([]string, error) {
	if err != nil {
		return nil, err
	}
	out := make([]string, len(ids))
	for i, id := range ids {
		out[i] = strconv.FormatInt(id, 10)
	}
	return out, nil
}
