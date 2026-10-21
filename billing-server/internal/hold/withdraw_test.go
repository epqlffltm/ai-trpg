// billing-server/internal/hold/withdraw_test.go

// 탈퇴한 사람의 걸린 홀드를 돌려주는 일(withdraw.go)을 시험한다.
package hold_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// releaseHeld 는 탈퇴처럼 한 트랜잭션에서 지갑을 잠그고 그 사람의 걸린 홀드를 모두 돌려준다.
func (f fixture) releaseHeld(user uuid.UUID) int {
	f.t.Helper()
	var released int
	err := txn.Run(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		if _, err := f.wallet.LockExisting(ctx(f.t), tx, user); err != nil {
			return err
		}
		var err error
		released, err = f.service.ReleaseHeldInTx(ctx(f.t), tx, user)
		return err
	})
	if err != nil {
		f.t.Fatalf("걸린 홀드를 돌려주지 못했다: %v", err)
	}
	return released
}

// wantReleaseReason 은 DB 에 적힌 그 홀드의 돌려준 이유가 기대와 같은지 본다.
func (f fixture) wantReleaseReason(reference string, want hold.ReleaseReason) {
	f.t.Helper()
	var reason *string
	const query = "SELECT release_reason FROM holds WHERE source = $1 AND reference = $2"
	if err := f.pool.QueryRow(ctx(f.t), query, source, reference).Scan(&reason); err != nil {
		f.t.Fatalf("홀드를 읽지 못했다: %v", err)
	}
	if reason == nil || hold.ReleaseReason(*reason) != want {
		f.t.Errorf("돌려준 이유 = %v, 기대 = %s", reason, want)
	}
}

func TestHeldHoldsOfAWithdrawnUserAreReleased(t *testing.T) {
	f := setUp(t)
	f.fund(200, 0)
	first, second := newReference(), newReference()
	f.place(first)
	f.place(second)
	f.wantBalance(200-2*price, 0)

	released := f.releaseHeld(f.user)

	if released != 2 {
		t.Errorf("돌려준 홀드 = %d, 기대 = 2", released)
	}
	f.wantStatus(first, hold.StatusReleased)
	f.wantReleaseReason(first, hold.ReleaseWithdrawn)
	f.wantReleaseReason(second, hold.ReleaseWithdrawn)
	f.wantBalance(200, 0)
}

func TestSettledHoldsAreLeftAlone(t *testing.T) {
	f := setUp(t)
	f.fund(200, 0)
	captured, released := newReference(), newReference()
	f.place(captured)
	f.place(released)
	if _, err := f.service.Capture(ctx(t), source, captured); err != nil {
		t.Fatalf("확정하지 못했다: %v", err)
	}
	if _, err := f.service.Release(ctx(t), source, released); err != nil {
		t.Fatalf("돌려주지 못했다: %v", err)
	}

	if n := f.releaseHeld(f.user); n != 0 {
		t.Errorf("돌려준 홀드 = %d. 끝난 홀드는 건드리지 않는다", n)
	}
	f.wantStatus(captured, hold.StatusCaptured)
	f.wantReleaseReason(released, hold.ReleaseRequested)
	f.wantBalance(200-price, 0)
}

func TestOnlyTheWithdrawnUsersHoldsAreReleased(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)

	if n := f.releaseHeld(uuid.New()); n != 0 {
		t.Errorf("다른 사람의 탈퇴로 돌려준 홀드 = %d", n)
	}
	f.wantStatus(reference, hold.StatusHeld)
}

func TestTheHoldingServerCannotCaptureAfterWithdrawal(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)
	f.releaseHeld(f.user)

	_, captureErr := f.service.Capture(ctx(t), source, reference)
	_, extendErr := f.service.Extend(ctx(t), source, reference)
	got, releaseErr := f.service.Release(ctx(t), source, reference)

	if !errors.Is(captureErr, hold.ErrAlreadyReleased) || !errors.Is(extendErr, hold.ErrAlreadyReleased) {
		t.Errorf("확정 = %v, 연장 = %v. 이미 돌려준 홀드다", captureErr, extendErr)
	}
	if releaseErr != nil || got.ReleaseReason != hold.ReleaseWithdrawn {
		t.Errorf("반환 = (%s, %v). 그대로 돌려준 홀드여야 한다", got.ReleaseReason, releaseErr)
	}
	f.wantBalance(100, 0)
}

// TestACaptureRacingTheWithdrawalSettlesOnce 는 홀드를 건 서버의 확정과 탈퇴가 함께 와도 하나만 되는지 본다.
// 확정이 먼저면 크레딧은 쓰인 채로, 탈퇴가 먼저면 돌아온 채로 끝난다. 확정한 홀드의 크레딧이 돌아오는 일은 없다.
func TestACaptureRacingTheWithdrawalSettlesOnce(t *testing.T) {
	for round := range 10 {
		f := setUp(t)
		f.fund(100, 0)
		reference := newReference()
		f.place(reference)

		errs := together(2, func(index int) error {
			if index == 0 {
				_, err := f.service.Capture(ctx(t), source, reference)
				return err
			}
			f.releaseHeld(f.user)
			return nil
		})

		var status hold.Status
		const query = "SELECT status FROM holds WHERE source = $1 AND reference = $2"
		if err := f.pool.QueryRow(ctx(t), query, source, reference).Scan(&status); err != nil {
			t.Fatalf("홀드를 읽지 못했다: %v", err)
		}
		switch status {
		case hold.StatusCaptured:
			f.wantBalance(100-price, 0)
		case hold.StatusReleased:
			if !errors.Is(errs[0], hold.ErrAlreadyReleased) {
				t.Errorf("%d 번째: 확정 = %v. 탈퇴가 먼저면 이미 돌려준 홀드다", round, errs[0])
			}
			f.wantBalance(100, 0)
		default:
			t.Fatalf("%d 번째: 홀드 = %s. 끝나 있어야 한다", round, status)
		}
	}
}
