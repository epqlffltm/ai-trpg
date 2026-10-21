// billing-server/internal/withdrawal/withdrawal.go

// Package withdrawal 은 인증 서버가 알린 탈퇴를 이 서버의 데이터에 반영한다(#603, docs/architecture/withdrawal.md).
//
// 인증 서버는 유예(7일)가 지난 계정을 비운 뒤 서버마다 알린다. 이 서버가 하는 일은 넷이다.
//
//  1. 걸린 홀드를 돌려준다(홀드의 이유 withdrawn). 크레딧이 뺐던 자리로 돌아간다
//  2. 남은 골드와 실버를 소멸로 적는다(원장의 이유 forfeit). 정한 것: "알리고 소멸". 탈퇴 화면이 먼저 알린다
//  3. 결제 자격을 지운다. 본인인증에서 온 값(성년이 되는 날, 보호자 동의)이다
//  4. 아직 보내지 않은 사용자의 알림을 보내지 않기로 한다
//
// 1 과 2 는 한 트랜잭션이다. 지갑을 먼저 잠근다. 그 뒤로는 새 홀드가 걸리지 않아 돌려준 홀드와 없앤 크레딧 사이에 틈이 없다.
// 3 과 4 는 따로 한다. 돈이 아니다. 하나가 실패하면 인증 서버가 다시 보내고, 이미 한 일은 다시 해도 같다.
//
// 남기는 것: 원장, 주문, 홀드, 출석의 기록, 보호자 알림의 기록. 원장과 주문은 법정 보존이고, 공개 ID 만 있어 사람을 알아볼 수 없다.
// 결과를 모르는 주문(confirming, refunding)은 대사가 그대로 끝낸다.
//
// 몇 번을 불러도 결과가 같다. 이 서버가 모르는 사용자(지갑이 없다)도 오류가 아니다. 할 일이 없을 뿐이다.
package withdrawal

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// Wallet 은 지갑을 잠그고 남은 크레딧을 없애는 것의 모양이다. *wallet.Service 가 이 모양이다.
type Wallet interface {
	LockExisting(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (bool, error)
	ForfeitInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (wallet.Forfeited, error)
}

// Holds 는 그 사람의 걸린 홀드를 돌려주는 것의 모양이다. *hold.Service 가 이 모양이다.
type Holds interface {
	ReleaseHeldInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID) (int, error)
}

// Eligibility 는 결제 자격을 지우는 것의 모양이다. *eligibility.Service 가 이 모양이다.
type Eligibility interface {
	Erase(ctx context.Context, userID uuid.UUID) (bool, error)
}

// Notices 는 보내지 않은 사용자의 알림을 멈추는 것의 모양이다. *usernotice.Service 가 이 모양이다.
type Notices interface {
	CancelFor(ctx context.Context, userID uuid.UUID) (int64, error)
}

// Outcome 은 탈퇴 하나를 반영한 결과다. 이미 반영한 사용자를 다시 받으면 모두 0 이다.
type Outcome struct {
	// ReleasedHolds 는 돌려준 홀드의 수다.
	ReleasedHolds int
	// Forfeited 는 없앤 크레딧이다.
	Forfeited wallet.Forfeited
	// ErasedEligibility 는 결제 자격을 지웠는지다.
	ErasedEligibility bool
	// CancelledNotices 는 보내지 않기로 한 사용자의 알림의 수다.
	CancelledNotices int64
}

// Service 는 탈퇴를 반영한다. 서버가 뜰 때 하나 만들어 쓴다.
type Service struct {
	db          txn.Beginner
	wallet      Wallet
	holds       Holds
	eligibility Eligibility
	notices     Notices
}

// NewService 는 Service 를 만든다. db 는 홀드와 지갑을 한 트랜잭션으로 묶을 곳이다(*pgxpool.Pool).
func NewService(db txn.Beginner, wallet Wallet, holds Holds, eligibility Eligibility, notices Notices) *Service {
	return &Service{db: db, wallet: wallet, holds: holds, eligibility: eligibility, notices: notices}
}

// Process 는 그 사용자의 탈퇴를 반영한다. 몇 번을 불러도 결과가 같다. 오류면 부르는 쪽(인증 서버)이 다시 보낸다.
func (s *Service) Process(ctx context.Context, userID uuid.UUID) (Outcome, error) {
	outcome, err := s.closeWallet(ctx, userID)
	if err != nil {
		return Outcome{}, err
	}
	if outcome.ErasedEligibility, err = s.eligibility.Erase(ctx, userID); err != nil {
		return Outcome{}, err
	}
	if outcome.CancelledNotices, err = s.notices.CancelFor(ctx, userID); err != nil {
		return Outcome{}, err
	}
	return outcome, nil
}

// closeWallet 은 한 트랜잭션에서 지갑을 잠그고, 걸린 홀드를 돌려주고, 남은 크레딧을 없앤다. 지갑이 없으면 아무것도 하지 않는다.
func (s *Service) closeWallet(ctx context.Context, userID uuid.UUID) (Outcome, error) {
	var outcome Outcome
	err := txn.Run(ctx, s.db, func(tx pgx.Tx) error {
		found, err := s.wallet.LockExisting(ctx, tx, userID)
		if err != nil || !found {
			return err
		}
		if outcome.ReleasedHolds, err = s.holds.ReleaseHeldInTx(ctx, tx, userID); err != nil {
			return err
		}
		outcome.Forfeited, err = s.wallet.ForfeitInTx(ctx, tx, userID)
		return err
	})
	if err != nil {
		return Outcome{}, err
	}
	return outcome, nil
}
