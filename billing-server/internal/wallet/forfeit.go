// billing-server/internal/wallet/forfeit.go

package wallet

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// 탈퇴한 사람의 남은 크레딧을 없앤다(#603, docs/architecture/withdrawal.md 의 "남은 골드": 알리고 소멸).
// 부르는 쪽(internal/withdrawal)이 한 트랜잭션에서 지갑을 잠그고(LockExisting), 걸린 홀드를 돌려준 뒤, 남은 것을 없앤다(ForfeitInTx).

// Forfeited 는 탈퇴로 없앤 크레딧이다.
type Forfeited struct {
	// Paid 는 없앤 산 크레딧(골드)이다.
	Paid credit.Amount
	// Free 는 없앤 무료 크레딧(실버)이다. 이미 기한이 지난 것은 없애기 전에 사라진 것(expire)으로 적혀 여기에 들지 않는다.
	Free credit.Amount
}

// LockExisting 은 지갑이 있으면 그 줄을 잠그고 true 다. 없으면 만들지 않고 false 다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 탈퇴처럼 "있는 것만 정리하는" 일이 쓴다. 지갑이 없는 사람에게 빈 지갑을 만들지 않는다.
// 잠근 뒤에는 그 사람의 새 홀드와 쓰기가 이 트랜잭션이 끝날 때까지 기다린다.
func (s *Service) LockExisting(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (bool, error) {
	_, err := walletdb.New(tx).LockWallet(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// ForfeitInTx 는 그 사람의 남은 산 크레딧과 무료 크레딧을 모두 없애고 원장에 forfeit 로 적는다. 부르는 쪽이 연 트랜잭션(tx) 안에서 한다.
// 묶음마다 남은 만큼 한 줄이다. 한 번에 없앤 줄들은 같은 작업 번호로 묶인다. 남은 것이 없으면 아무것도 적지 않는다.
// 몇 번을 불러도 같다. 두 번째에는 남은 것이 없다.
// 지갑이 없는 사람에게 부르면 빈 지갑이 생긴다. 부르는 쪽이 먼저 LockExisting 으로 본다.
func (s *Service) ForfeitInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (Forfeited, error) {
	var forfeited Forfeited
	err := s.lockAndRun(ctx, tx, userID, s.clock(), func(ctx context.Context, c change) error {
		var err error
		forfeited, err = c.forfeitAll(ctx)
		return err
	})
	if err != nil {
		return Forfeited{}, err
	}
	return forfeited, nil
}

// forfeitAll 은 잠근 지갑(c)의 남은 묶음을 모두 비우고 원장에 적는다. 없앤 양을 돌려준다.
// 기한이 지난 무료 크레딧은 지갑을 잠글 때 이미 사라진 것으로 적혔다(lockAndRun 의 expireDue).
func (c change) forfeitAll(ctx context.Context) (Forfeited, error) {
	why := because(ReasonForfeit)
	paid, err := c.forfeitLots(ctx, why)
	if err != nil {
		return Forfeited{}, err
	}
	free, err := c.forfeitGrants(ctx, why)
	if err != nil {
		return Forfeited{}, err
	}
	return Forfeited{Paid: paid, Free: free}, nil
}

// forfeitLots 는 남은 것이 있는 산 크레딧의 묶음을 모두 비운다. 비운 양의 합을 돌려준다.
func (c change) forfeitLots(ctx context.Context, why cause) (credit.Amount, error) {
	lots, err := c.openLots(ctx)
	if err != nil {
		return 0, err
	}
	var total credit.Amount
	for _, lot := range lots {
		if err := c.takeFromLot(ctx, why, lot.ID, lot.Remaining); err != nil {
			return 0, err
		}
		total += lot.Remaining
	}
	return total, nil
}

// forfeitGrants 는 아직 쓸 수 있는 무료 크레딧의 묶음을 모두 비운다. 비운 양의 합을 돌려준다.
func (c change) forfeitGrants(ctx context.Context, why cause) (credit.Amount, error) {
	grants, err := c.openGrants(ctx)
	if err != nil {
		return 0, err
	}
	var total credit.Amount
	for _, grant := range grants {
		if err := c.takeFromGrant(ctx, why, grant.ID, grant.Remaining); err != nil {
			return 0, err
		}
		total += grant.Remaining
	}
	return total, nil
}
