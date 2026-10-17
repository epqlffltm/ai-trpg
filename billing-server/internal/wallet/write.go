// billing-server/internal/wallet/write.go

package wallet

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// Deposit 은 주문 없이 산 크레딧을 넣는다. 주문이 없는 묶음 하나가 생긴다. 그 묶음은 어느 주문의 것도 아니다.
func (s *Service) Deposit(ctx context.Context, userID uuid.UUID, amount credit.Amount) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		return c.openLot(ctx, because(ReasonDeposit), amount)
	})
}

// DepositForOrder 는 주문으로 산 크레딧을 넣는다. 그 주문의 묶음 하나가 생긴다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 주문을 "치렀다"로 바꾸는 일과 크레딧을 넣는 일이 함께 되거나 함께 안 되게 하려는 것이다.
// 같은 주문으로 두 번 부르면 둘째는 DB 가 거절한다(paid_lots_order_once, ledger_entries_order_once).
func (s *Service) DepositForOrder(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, orderID uuid.UUID) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		return c.openLot(ctx, cause{operationID: uuid.New(), reason: ReasonDeposit, orderID: &orderID}, amount)
	})
}

// GrantFree 는 무료 크레딧을 준다. 준 크레딧은 정해진 시간(Policy.FreeTTL)이 지나면 사라진다.
func (s *Service) GrantFree(ctx context.Context, userID uuid.UUID, amount credit.Amount) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		return c.openGrant(ctx, because(ReasonGrant), amount, c.now.Add(s.policy.FreeTTL), pgtype.Text{})
	})
}

// GrantFreeOnce 는 한 사용자에게 한 번만 주는 무료 크레딧을 준다. key 는 그 지급의 이름이다(환영 크레딧은 "welcome").
// 이 사용자가 같은 이름으로 이미 받았으면 ErrAlreadyGranted 를 돌려주고 아무것도 바꾸지 않는다.
// 받은 것을 다 썼거나 기한이 지나 사라졌어도 다시 받지 못한다.
func (s *Service) GrantFreeOnce(ctx context.Context, userID uuid.UUID, amount credit.Amount, key string) (Grant, error) {
	if err := checkGrantOnce(amount, key); err != nil {
		return Grant{}, err
	}
	var grant Grant
	err := s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		var err error
		grant, err = s.grantOnce(ctx, c, amount, key)
		return err
	})
	if err != nil {
		return Grant{}, err
	}
	return grant, nil
}

// GrantFreeOnceInTx 는 GrantFreeOnce 와 같지만 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 출석처럼 "받았다는 기록"과 크레딧이 함께 되거나 함께 안 되어야 할 때 쓴다.
// ErrAlreadyGranted 를 돌려주면 부르는 쪽이 트랜잭션을 되돌린다.
func (s *Service) GrantFreeOnceInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, key string) (Grant, error) {
	if err := checkGrantOnce(amount, key); err != nil {
		return Grant{}, err
	}
	var grant Grant
	err := lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		var err error
		grant, err = s.grantOnce(ctx, c, amount, key)
		return err
	})
	if err != nil {
		return Grant{}, err
	}
	return grant, nil
}

// checkGrantOnce 는 한 번만 주는 지급의 양과 이름을 본다.
func checkGrantOnce(amount credit.Amount, key string) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	if !grantKeyPattern.MatchString(key) {
		return ErrInvalidGrantKey
	}
	return nil
}

// grantOnce 는 잠근 지갑(c)에 그 이름의 지급이 없으면 준다. 있으면 ErrAlreadyGranted 다.
func (s *Service) grantOnce(ctx context.Context, c change, amount credit.Amount, key string) (Grant, error) {
	// 지갑의 줄을 잠근 채로 본다. 같은 사용자의 두 요청이 함께 와도 뒤의 것은 앞의 것이 준 것을 본다
	taken, err := c.queries.HasFreeGrantWithKey(ctx, walletdb.HasFreeGrantWithKeyParams{UserID: c.userID, GrantKey: key})
	if err != nil {
		return Grant{}, err
	}
	if taken {
		return Grant{}, ErrAlreadyGranted
	}
	grant := Grant{Amount: amount, ExpiresAt: c.now.Add(s.policy.FreeTTL)}
	if err := c.openGrant(ctx, because(ReasonGrant), amount, grant.ExpiresAt, pgtype.Text{String: key, Valid: true}); err != nil {
		return Grant{}, err
	}
	return grant, nil
}

// Spend 는 크레딧을 쓴다. 가진 것이 모자라면 ErrInsufficient 를 돌려주고 아무것도 바꾸지 않는다.
// 무료 크레딧과 산 크레딧 가운데 어느 쪽을 먼저 쓰는지는 Policy.FreeFirst 가 정한다.
// 산 크레딧은 먼저 들어온 묶음부터 쓴다.
func (s *Service) Spend(ctx context.Context, userID uuid.UUID, amount credit.Amount) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		plan, err := c.plan(ctx, amount, s.policy.FreeFirst)
		if err != nil {
			return err
		}
		return c.apply(ctx, because(ReasonSpend), plan)
	})
}

// TakeForHold 는 홀드로 크레딧을 뺀다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 홀드를 만드는 일과 크레딧을 빼는 일이 함께 되거나 함께 안 되게 하려는 것이다.
// funds 가 AnyCredits 면 Spend 와 같은 규칙(Policy.FreeFirst)을 따르고, 모자라면 ErrInsufficient 다.
// PaidOnly 면 산 크레딧에서만 빼고, 모자라면 ErrPaidInsufficient 다.
// 원장에는 hold 줄이 남고 그 줄이 홀드를 가리킨다. 어디서 얼마를 뺐는지는 그 줄들이 기억한다.
// 그래서 돌려줄 때(ReturnForHold)는 funds 를 다시 받지 않는다. 뺐던 자리로 돌아간다.
func (s *Service) TakeForHold(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, holdID uuid.UUID, funds Funds) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		plan, err := c.planFrom(ctx, amount, s.policy.FreeFirst, funds)
		if err != nil {
			return err
		}
		return c.apply(ctx, cause{operationID: uuid.New(), reason: ReasonHold, holdID: &holdID}, plan)
	})
}

// ReturnForHold 는 홀드로 뺀 크레딧을 뺐던 곳으로 돌려놓는다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 산 크레딧은 원래의 묶음으로, 무료 크레딧은 원래의 지급 묶음으로 간다. 지급 묶음의 사라지는 시각은 고치지 않는다.
// 묶음을 두기 전(00007)에 건 홀드는 산 크레딧을 묶음 없이 뺐다. 그 크레딧은 주문 없는 새 묶음으로 돌아간다.
// 그사이에 기한이 지났으면 돌아온 크레딧은 곧바로 사라진 것으로 적힌다. 홀드로 기한을 피할 수 없다.
// 같은 홀드로 두 번 부르면 둘째는 DB 가 거절한다(ledger_entries_hold_line_once).
func (s *Service) ReturnForHold(ctx context.Context, tx pgx.Tx, userID uuid.UUID, holdID uuid.UUID) error {
	return lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		if err := c.giveBack(ctx, cause{operationID: uuid.New(), reason: ReasonRelease, holdID: &holdID}); err != nil {
			return err
		}
		// 기한이 지난 묶음으로 돌아간 것을 바로 정리한다. 원장에 "돌아왔다" 다음 줄로 "사라졌다"가 남는다
		return c.expireDue(ctx)
	})
}

// change 는 한 사용자의 크레딧을 바꾸는 트랜잭션 하나다. 지갑의 줄을 잠근 채로 만들어진다.
type change struct {
	queries *walletdb.Queries
	userID  uuid.UUID
	// now 는 이 변경이 일어난 시각이다. 이 트랜잭션이 적는 모든 줄이 같은 시각을 쓴다.
	now time.Time
}

// withLockedWallet 은 트랜잭션을 열고, 지갑의 줄을 잠그고, 기한이 지난 무료 크레딧을 정리한 뒤 run 을 부른다.
// run 이 오류를 돌려주면 정리한 것까지 모두 되돌린다. 정리는 다음 변경 때 다시 일어난다.
func (s *Service) withLockedWallet(ctx context.Context, userID uuid.UUID, run func(context.Context, change) error) error {
	now := s.clock()
	return pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		return lockAndRun(ctx, tx, userID, now, run)
	})
}

// lockAndRun 은 주어진 트랜잭션 안에서 지갑의 줄을 잠그고, 기한이 지난 무료 크레딧을 정리한 뒤 run 을 부른다.
// 트랜잭션을 열고 닫는 것은 부르는 쪽의 일이다.
func lockAndRun(ctx context.Context, tx pgx.Tx, userID uuid.UUID, now time.Time, run func(context.Context, change) error) error {
	c, err := lockWallet(ctx, walletdb.New(tx), userID, now)
	if err != nil {
		return err
	}
	if err := c.expireDue(ctx); err != nil {
		return err
	}
	return run(ctx, c)
}

// lockWallet 은 지갑이 없으면 만들고, 그 줄을 잠근다. 같은 사용자의 다른 변경은 여기서 기다린다.
func lockWallet(ctx context.Context, queries *walletdb.Queries, userID uuid.UUID, now time.Time) (change, error) {
	if err := queries.EnsureWallet(ctx, walletdb.EnsureWalletParams{UserID: userID, Now: now}); err != nil {
		return change{}, err
	}
	// 잔액은 쓰지 않는다. 어디서 뺄지는 묶음들을 읽어 정한다. 이 문장은 줄을 잠그려는 것이다
	if _, err := queries.LockWallet(ctx, userID); err != nil {
		return change{}, err
	}
	return change{queries: queries, userID: userID, now: now}, nil
}

// cause 는 원장의 줄에 적는 "왜"다. 한 번의 변경이 남기는 줄들이 같은 cause 를 쓴다.
type cause struct {
	// operationID 는 한 번의 변경이 남긴 줄들을 묶는 번호다.
	operationID uuid.UUID
	reason      Reason
	// orderID 는 주문으로 들어온 크레딧일 때만, holdID 는 홀드로 빠지거나 돌아온 크레딧일 때만 넣는다.
	orderID *uuid.UUID
	holdID  *uuid.UUID
}

// because 는 주문이나 홀드와 이어지지 않는 변경의 cause 를 만든다. 작업 번호는 새로 짓는다.
func because(reason Reason) cause {
	return cause{operationID: uuid.New(), reason: reason}
}

// expireDue 는 기한이 지났는데 남은 것이 있는 지급 묶음을 비우고, 사라진 만큼을 원장에 적는다.
// 잔액을 읽을 때는 기한이 지난 묶음을 이미 세지 않는다. 여기서 하는 일은 그 사실을 기록으로 남기는 것이다.
func (c change) expireDue(ctx context.Context) error {
	due, err := c.queries.ListDueFreeGrants(ctx, walletdb.ListDueFreeGrantsParams{UserID: c.userID, Now: c.now})
	if err != nil {
		return err
	}
	// 한 번에 사라진 묶음들은 같은 작업 번호로 묶는다
	expired := because(ReasonExpire)
	for _, grant := range due {
		if err := c.takeFromGrant(ctx, expired, grant.ID, grant.Remaining); err != nil {
			return err
		}
	}
	return nil
}

// plan 은 지금의 묶음들을 읽어 amount 를 어디서 얼마씩 뺄지 정한다. 가진 것이 모자라면 ErrInsufficient 다.
func (c change) plan(ctx context.Context, amount credit.Amount, freeFirst bool) (spendPlan, error) {
	lots, err := c.openLots(ctx)
	if err != nil {
		return spendPlan{}, err
	}
	grants, err := c.openGrants(ctx)
	if err != nil {
		return spendPlan{}, err
	}
	return planSpend(amount, lots, grants, freeFirst)
}

// planFrom 은 funds 에 맞춰 amount 를 어디서 뺄지 정한다. PaidOnly 면 무료 크레딧의 묶음을 읽지 않는다.
func (c change) planFrom(ctx context.Context, amount credit.Amount, freeFirst bool, funds Funds) (spendPlan, error) {
	if funds != PaidOnly {
		return c.plan(ctx, amount, freeFirst)
	}
	lots, err := c.openLots(ctx)
	if err != nil {
		return spendPlan{}, err
	}
	// 무료 크레딧의 묶음을 넘기지 않으므로 어느 쪽을 먼저 쓰는지(freeFirst)는 상관없다
	plan, err := planSpend(amount, lots, nil, false)
	if errors.Is(err, ErrInsufficient) {
		return spendPlan{}, ErrPaidInsufficient
	}
	return plan, err
}

// openLots 는 남은 것이 있는 산 크레딧의 묶음을 먼저 들어온 것부터 돌려준다.
func (c change) openLots(ctx context.Context) ([]bucket, error) {
	rows, err := c.queries.ListOpenPaidLots(ctx, c.userID)
	if err != nil {
		return nil, err
	}
	lots := make([]bucket, 0, len(rows))
	for _, row := range rows {
		lots = append(lots, bucket{ID: row.ID, Remaining: row.Remaining})
	}
	return lots, nil
}

// openGrants 는 지금 쓸 수 있는 지급 묶음을 먼저 사라지는 것부터 돌려준다.
// 기한이 지난 묶음은 expireDue 가 이미 비웠지만, 쿼리도 사라지는 시각을 한 번 더 본다.
// 둘 가운데 하나가 빠져도 사라진 크레딧을 쓰게 되지는 않는다.
func (c change) openGrants(ctx context.Context) ([]bucket, error) {
	rows, err := c.queries.ListLiveFreeGrants(ctx, walletdb.ListLiveFreeGrantsParams{UserID: c.userID, Now: c.now})
	if err != nil {
		return nil, err
	}
	grants := make([]bucket, 0, len(rows))
	for _, row := range rows {
		grants = append(grants, bucket{ID: row.ID, Remaining: row.Remaining})
	}
	return grants, nil
}

// apply 는 정해 둔 대로 크레딧을 뺀다. 여러 곳에서 빼도 원장의 줄은 같은 작업 번호로 묶인다.
func (c change) apply(ctx context.Context, why cause, plan spendPlan) error {
	for _, d := range plan.Free {
		if err := c.takeFromGrant(ctx, why, d.ID, d.Amount); err != nil {
			return err
		}
	}
	for _, d := range plan.Paid {
		if err := c.takeFromLot(ctx, why, d.ID, d.Amount); err != nil {
			return err
		}
	}
	return nil
}

// giveBack 은 홀드로 뺀 줄들을 읽어, 뺐던 곳마다 뺐던 만큼 돌려놓는다. 뺀 줄이 없으면 아무것도 하지 않는다.
func (c change) giveBack(ctx context.Context, why cause) error {
	lines, err := c.queries.ListHoldLines(ctx, walletdb.ListHoldLinesParams{UserID: c.userID, HoldID: *why.holdID})
	if err != nil {
		return err
	}
	for _, line := range lines {
		// 뺀 줄의 양은 음수다. 부호를 뒤집은 만큼 돌려놓는다
		if err := c.giveBackLine(ctx, why, line, -line.Amount); err != nil {
			return err
		}
	}
	return nil
}

// giveBackLine 은 뺀 줄 하나를 되돌린다. 지급 묶음이 적힌 줄은 그 지급 묶음으로, 산 크레딧의 묶음이 적힌 줄은 그 묶음으로 돌려놓는다.
// 묶음이 없는 산 크레딧의 줄은 묶음을 두기 전(00007)에 건 홀드의 것이다. 묶음 없이 돌려놓고 곧바로 새 묶음으로 옮긴다.
// 돌려놓는 줄은 뺀 줄과 같은 묶음(없으면 없음)을 적는다. 그래야 같은 홀드를 두 번 돌려줄 때 DB 가 막는다(ledger_entries_hold_line_once).
func (c change) giveBackLine(ctx context.Context, why cause, line walletdb.ListHoldLinesRow, amount credit.Amount) error {
	switch {
	case line.GrantID.Valid:
		return c.returnToGrant(ctx, why, line.GrantID.Int64, amount)
	case line.LotID.Valid:
		return c.returnToLot(ctx, why, line.LotID.Int64, amount)
	default:
		if err := c.movePaid(ctx, why, noLot, amount); err != nil {
			return err
		}
		return c.regroup(ctx, amount)
	}
}

// openLot 은 산 크레딧의 묶음을 만들어 amount 를 넣고 원장에 적는다. why 에 주문이 있으면 그 주문의 묶음이다.
func (c change) openLot(ctx context.Context, why cause, amount credit.Amount) error {
	lotID, err := c.queries.CreatePaidLot(ctx, walletdb.CreatePaidLotParams{
		UserID: c.userID, OrderID: why.orderID, Amount: amount, Now: c.now,
	})
	if err != nil {
		return err
	}
	return c.movePaid(ctx, why, lotRef(lotID), amount)
}

// takeFromLot 은 산 크레딧의 묶음에서 amount 만큼 빼고, 잔액과 원장에 적는다. 셋은 늘 함께 일어난다.
func (c change) takeFromLot(ctx context.Context, why cause, lotID int64, amount credit.Amount) error {
	err := c.queries.TakeFromPaidLot(ctx, walletdb.TakeFromPaidLotParams{ID: lotID, Amount: amount})
	if err != nil {
		return err
	}
	return c.movePaid(ctx, why, lotRef(lotID), -amount)
}

// returnToLot 은 산 크레딧의 묶음에 amount 만큼 돌려놓고, 잔액과 원장에 적는다. 셋은 늘 함께 일어난다.
func (c change) returnToLot(ctx context.Context, why cause, lotID int64, amount credit.Amount) error {
	err := c.queries.ReturnToPaidLot(ctx, walletdb.ReturnToPaidLotParams{ID: lotID, Amount: amount})
	if err != nil {
		return err
	}
	return c.movePaid(ctx, why, lotRef(lotID), amount)
}

// regroup 은 묶음 없이 잔액에 있는 산 크레딧 amount 를 주문 없는 새 묶음으로 옮긴다. 잔액은 그대로다.
// 원장에는 묶음 없는 쪽에서 빠지는 줄과 새 묶음으로 들어가는 줄이 같은 작업 번호로 남는다. 둘의 합은 0 이다.
func (c change) regroup(ctx context.Context, amount credit.Amount) error {
	lotID, err := c.queries.CreatePaidLot(ctx, walletdb.CreatePaidLotParams{UserID: c.userID, Amount: amount, Now: c.now})
	if err != nil {
		return err
	}
	moved := because(ReasonRegroup)
	if err := c.record(ctx, moved, KindPaid, -amount, noGrant, noLot); err != nil {
		return err
	}
	return c.record(ctx, moved, KindPaid, amount, noGrant, lotRef(lotID))
}

// movePaid 는 산 크레딧의 잔액을 delta 만큼 바꾸고(줄이려면 음수) 원장에 적는다. 둘은 늘 함께 일어난다.
// lot 은 그 크레딧의 묶음이다. 묶음의 남은 양은 부르는 쪽이 바꾼다.
func (c change) movePaid(ctx context.Context, why cause, lot pgtype.Int8, delta credit.Amount) error {
	err := c.queries.AddPaidBalance(ctx, walletdb.AddPaidBalanceParams{UserID: c.userID, Delta: delta, Now: c.now})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindPaid, delta, noGrant, lot)
}

// openGrant 는 무료 크레딧의 지급 묶음을 만들고 원장에 적는다. 둘은 늘 함께 일어난다.
// key 는 한 번만 주는 지급의 이름이다. 몇 번이고 줄 수 있는 지급이면 비워 둔다.
func (c change) openGrant(ctx context.Context, why cause, amount credit.Amount, expiresAt time.Time, key pgtype.Text) error {
	grantID, err := c.queries.CreateFreeGrant(ctx, walletdb.CreateFreeGrantParams{
		UserID: c.userID, Amount: amount, ExpiresAt: expiresAt, GrantKey: key, Now: c.now,
	})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindFree, amount, grantRef(grantID), noLot)
}

// takeFromGrant 는 지급 묶음에서 amount 만큼 빼고 원장에 적는다. 둘은 늘 함께 일어난다.
func (c change) takeFromGrant(ctx context.Context, why cause, grantID int64, amount credit.Amount) error {
	err := c.queries.TakeFromFreeGrant(ctx, walletdb.TakeFromFreeGrantParams{ID: grantID, Amount: amount})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindFree, -amount, grantRef(grantID), noLot)
}

// returnToGrant 는 지급 묶음에 amount 만큼 돌려놓고 원장에 적는다. 둘은 늘 함께 일어난다.
func (c change) returnToGrant(ctx context.Context, why cause, grantID int64, amount credit.Amount) error {
	err := c.queries.ReturnToFreeGrant(ctx, walletdb.ReturnToFreeGrantParams{ID: grantID, Amount: amount})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindFree, amount, grantRef(grantID), noLot)
}

// noGrant 와 noLot 은 원장의 줄에 묶음을 적지 않는다는 뜻이다.
var (
	noGrant = pgtype.Int8{}
	noLot   = pgtype.Int8{}
)

// grantRef 와 lotRef 는 원장의 줄에 적을 묶음의 번호다.
func grantRef(id int64) pgtype.Int8 { return pgtype.Int8{Int64: id, Valid: true} }
func lotRef(id int64) pgtype.Int8   { return pgtype.Int8{Int64: id, Valid: true} }

// record 는 원장에 한 줄을 덧붙인다. 무료 크레딧의 줄은 grant 에, 산 크레딧의 줄은 lot 에 묶음을 적는다.
func (c change) record(ctx context.Context, why cause, kind Kind, amount credit.Amount, grant pgtype.Int8, lot pgtype.Int8) error {
	return c.queries.InsertEntry(ctx, walletdb.InsertEntryParams{
		UserID:      c.userID,
		OperationID: why.operationID,
		Kind:        string(kind),
		Reason:      string(why.reason),
		Amount:      amount,
		GrantID:     grant,
		LotID:       lot,
		OrderID:     why.orderID,
		HoldID:      why.holdID,
		Now:         c.now,
	})
}
