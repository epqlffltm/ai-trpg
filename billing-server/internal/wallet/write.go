// billing-server/internal/wallet/write.go

package wallet

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// Deposit 은 산 크레딧을 넣는다.
func (s *Service) Deposit(ctx context.Context, userID uuid.UUID, amount credit.Amount) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		return c.movePaid(ctx, because(ReasonDeposit), amount)
	})
}

// DepositForOrder 는 주문으로 산 크레딧을 넣는다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 주문을 "치렀다"로 바꾸는 일과 크레딧을 넣는 일이 함께 되거나 함께 안 되게 하려는 것이다.
// 같은 주문으로 두 번 부르면 둘째는 DB 가 거절한다(ledger_entries_order_once).
func (s *Service) DepositForOrder(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, orderID uuid.UUID) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		return c.movePaid(ctx, cause{operationID: uuid.New(), reason: ReasonDeposit, orderID: &orderID}, amount)
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
	if err := checkAmount(amount); err != nil {
		return Grant{}, err
	}
	if !grantKeyPattern.MatchString(key) {
		return Grant{}, ErrInvalidGrantKey
	}
	var grant Grant
	err := s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		// 지갑의 줄을 잠근 채로 본다. 같은 사용자의 두 요청이 함께 와도 뒤의 것은 앞의 것이 준 것을 본다
		taken, err := c.queries.HasFreeGrantWithKey(ctx, walletdb.HasFreeGrantWithKeyParams{UserID: userID, GrantKey: key})
		if err != nil {
			return err
		}
		if taken {
			return ErrAlreadyGranted
		}
		grant = Grant{Amount: amount, ExpiresAt: c.now.Add(s.policy.FreeTTL)}
		return c.openGrant(ctx, because(ReasonGrant), amount, grant.ExpiresAt, pgtype.Text{String: key, Valid: true})
	})
	if err != nil {
		return Grant{}, err
	}
	return grant, nil
}

// Spend 는 크레딧을 쓴다. 가진 것이 모자라면 ErrInsufficient 를 돌려주고 아무것도 바꾸지 않는다.
// 무료 크레딧과 산 크레딧 가운데 어느 쪽을 먼저 쓰는지는 Policy.FreeFirst 가 정한다.
func (s *Service) Spend(ctx context.Context, userID uuid.UUID, amount credit.Amount) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return s.withLockedWallet(ctx, userID, func(ctx context.Context, c change) error {
		grants, err := c.openGrants(ctx)
		if err != nil {
			return err
		}
		plan, err := planSpend(amount, c.paid, grants, s.policy.FreeFirst)
		if err != nil {
			return err
		}
		return c.apply(ctx, because(ReasonSpend), plan)
	})
}

// TakeForHold 는 홀드로 크레딧을 뺀다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 홀드를 만드는 일과 크레딧을 빼는 일이 함께 되거나 함께 안 되게 하려는 것이다.
// 어디서 뺄지는 Spend 와 같은 규칙(Policy.FreeFirst)을 따른다. 가진 것이 모자라면 ErrInsufficient 다.
// 원장에는 hold 줄이 남고 그 줄이 홀드를 가리킨다. 어디서 얼마를 뺐는지는 그 줄들이 기억한다.
func (s *Service) TakeForHold(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, holdID uuid.UUID) error {
	if err := checkAmount(amount); err != nil {
		return err
	}
	return lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		grants, err := c.openGrants(ctx)
		if err != nil {
			return err
		}
		plan, err := planSpend(amount, c.paid, grants, s.policy.FreeFirst)
		if err != nil {
			return err
		}
		return c.apply(ctx, cause{operationID: uuid.New(), reason: ReasonHold, holdID: &holdID}, plan)
	})
}

// ReturnForHold 는 홀드로 뺀 크레딧을 뺐던 곳으로 돌려놓는다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 산 크레딧은 잔액으로, 무료 크레딧은 원래의 지급 묶음으로 간다. 지급 묶음의 사라지는 시각은 고치지 않는다.
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
	// paid 는 잠근 순간의 산 크레딧 잔액이다.
	paid credit.Amount
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
	paid, err := queries.LockWallet(ctx, userID)
	if err != nil {
		return change{}, err
	}
	return change{queries: queries, userID: userID, now: now, paid: paid}, nil
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

// openGrants 는 지금 쓸 수 있는 지급 묶음을 먼저 사라지는 것부터 돌려준다.
// 기한이 지난 묶음은 expireDue 가 이미 비웠지만, 쿼리도 사라지는 시각을 한 번 더 본다.
// 둘 가운데 하나가 빠져도 사라진 크레딧을 쓰게 되지는 않는다.
func (c change) openGrants(ctx context.Context) ([]openGrant, error) {
	rows, err := c.queries.ListLiveFreeGrants(ctx, walletdb.ListLiveFreeGrantsParams{UserID: c.userID, Now: c.now})
	if err != nil {
		return nil, err
	}
	grants := make([]openGrant, 0, len(rows))
	for _, row := range rows {
		grants = append(grants, openGrant{ID: row.ID, Remaining: row.Remaining})
	}
	return grants, nil
}

// apply 는 정해 둔 대로 크레딧을 뺀다. 여러 곳에서 빼도 원장의 줄은 같은 작업 번호로 묶인다.
func (c change) apply(ctx context.Context, why cause, plan spendPlan) error {
	for _, draw := range plan.Free {
		if err := c.takeFromGrant(ctx, why, draw.GrantID, draw.Amount); err != nil {
			return err
		}
	}
	if plan.Paid == 0 {
		return nil
	}
	return c.movePaid(ctx, why, -plan.Paid)
}

// giveBack 은 홀드로 뺀 줄들을 읽어, 뺐던 곳마다 뺐던 만큼 돌려놓는다. 뺀 줄이 없으면 아무것도 하지 않는다.
func (c change) giveBack(ctx context.Context, why cause) error {
	lines, err := c.queries.ListHoldLines(ctx, walletdb.ListHoldLinesParams{UserID: c.userID, HoldID: *why.holdID})
	if err != nil {
		return err
	}
	for _, line := range lines {
		// 뺀 줄의 양은 음수다. 부호를 뒤집은 만큼 돌려놓는다
		if err := c.giveBackLine(ctx, why, line.GrantID, -line.Amount); err != nil {
			return err
		}
	}
	return nil
}

// giveBackLine 은 뺀 줄 하나를 되돌린다. 지급 묶음이 적힌 줄은 그 묶음으로, 아니면 산 크레딧의 잔액으로 돌려놓는다.
func (c change) giveBackLine(ctx context.Context, why cause, grantID pgtype.Int8, amount credit.Amount) error {
	if grantID.Valid {
		return c.returnToGrant(ctx, why, grantID.Int64, amount)
	}
	return c.movePaid(ctx, why, amount)
}

// movePaid 는 산 크레딧의 잔액을 delta 만큼 바꾸고(줄이려면 음수) 원장에 적는다. 둘은 늘 함께 일어난다.
func (c change) movePaid(ctx context.Context, why cause, delta credit.Amount) error {
	err := c.queries.AddPaidBalance(ctx, walletdb.AddPaidBalanceParams{UserID: c.userID, Delta: delta, Now: c.now})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindPaid, delta, pgtype.Int8{})
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
	return c.record(ctx, why, KindFree, amount, pgtype.Int8{Int64: grantID, Valid: true})
}

// takeFromGrant 는 지급 묶음에서 amount 만큼 빼고 원장에 적는다. 둘은 늘 함께 일어난다.
func (c change) takeFromGrant(ctx context.Context, why cause, grantID int64, amount credit.Amount) error {
	err := c.queries.TakeFromFreeGrant(ctx, walletdb.TakeFromFreeGrantParams{ID: grantID, Amount: amount})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindFree, -amount, pgtype.Int8{Int64: grantID, Valid: true})
}

// returnToGrant 는 지급 묶음에 amount 만큼 돌려놓고 원장에 적는다. 둘은 늘 함께 일어난다.
func (c change) returnToGrant(ctx context.Context, why cause, grantID int64, amount credit.Amount) error {
	err := c.queries.ReturnToFreeGrant(ctx, walletdb.ReturnToFreeGrantParams{ID: grantID, Amount: amount})
	if err != nil {
		return err
	}
	return c.record(ctx, why, KindFree, amount, pgtype.Int8{Int64: grantID, Valid: true})
}

// record 는 원장에 한 줄을 덧붙인다.
func (c change) record(ctx context.Context, why cause, kind Kind, amount credit.Amount, grantID pgtype.Int8) error {
	return c.queries.InsertEntry(ctx, walletdb.InsertEntryParams{
		UserID:      c.userID,
		OperationID: why.operationID,
		Kind:        string(kind),
		Reason:      string(why.reason),
		Amount:      amount,
		GrantID:     grantID,
		OrderID:     why.orderID,
		HoldID:      why.holdID,
		Now:         c.now,
	})
}
