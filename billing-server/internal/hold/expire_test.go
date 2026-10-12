// billing-server/internal/hold/expire_test.go

// 홀드의 만료, 연장, 정리 작업을 시험한다.
// ExpireDue 를 부르는 테스트는 setUpSweep 을 쓴다. 정리 작업은 사용자를 가리지 않아서 다른 테스트의 홀드에 닿을 수 있다.
package hold_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// expiry 는 DB 에 적힌 홀드의 만료 시각과 돌려준 이유를 읽는다. 돌려주지 않았으면 이유는 빈 글자다.
func (f fixture) expiry(reference string) (time.Time, hold.ReleaseReason) {
	f.t.Helper()
	var expiresAt time.Time
	var reason *string
	const query = "SELECT expires_at, release_reason FROM holds WHERE source = $1 AND reference = $2"
	if err := f.pool.QueryRow(ctx(f.t), query, source, reference).Scan(&expiresAt, &reason); err != nil {
		f.t.Fatalf("홀드를 읽지 못했다: %v", err)
	}
	if reason == nil {
		return expiresAt, ""
	}
	return expiresAt, hold.ReleaseReason(*reason)
}

// expireDue 는 정리 작업을 한 번 돌린다.
func (f fixture) expireDue() {
	f.t.Helper()
	if _, err := f.service.ExpireDue(ctx(f.t), 1000); err != nil {
		f.t.Fatalf("정리 작업이 실패했다: %v", err)
	}
}

func TestPlaceSetsTheExpiryOneTTLAhead(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()

	placed := f.place(reference)

	want := f.clock.Now().Add(ttl)
	if !placed.ExpiresAt.Equal(want) || placed.ReleaseReason != "" {
		t.Errorf("홀드 = %+v. 만료 시각의 기대 = %v", placed, want)
	}
	if stored, _ := f.expiry(reference); !stored.Equal(want) {
		t.Errorf("DB 의 만료 시각 = %v, 기대 = %v", stored, want)
	}
}

func TestPlacingAgainDoesNotExtend(t *testing.T) {
	// 같은 요청을 다시 보낸 것이다. 홀드를 새로 거는 것이 아니므로 만료 시각도 그대로다. 연장은 Extend 로만 한다
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	first := f.place(reference)
	f.clock.Advance(10 * time.Hour)

	again := f.place(reference)

	if again.ID != first.ID || !again.ExpiresAt.Equal(first.ExpiresAt) {
		t.Errorf("다시 건 홀드 = %+v, 처음 = %+v", again, first)
	}
}

func TestExtendMovesTheExpiryFromNow(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)
	f.clock.Advance(20 * time.Hour)

	extended, err := f.service.Extend(ctx(t), source, reference)

	want := f.clock.Now().Add(ttl)
	if err != nil || extended.Status != hold.StatusHeld || !extended.ExpiresAt.Equal(want) {
		t.Fatalf("연장 = %+v, %v. 만료 시각의 기대 = %v", extended, err, want)
	}
	if stored, _ := f.expiry(reference); !stored.Equal(want) {
		t.Errorf("DB 의 만료 시각 = %v, 기대 = %v", stored, want)
	}
	// 연장은 크레딧을 건드리지 않는다
	f.wantBalance(50, 0)
	f.wantStatus(reference, hold.StatusHeld)
}

func TestExtendNeverShortensTheExpiry(t *testing.T) {
	// 운영 중에 HOLD_TTL 을 줄였다. 이미 하루를 받은 홀드를 연장해도 그보다 앞당기지 않는다
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	placed := f.place(reference)
	shorter, err := hold.NewService(f.pool, f.clock.Now, f.wallet, pricing.NewService(f.pool, f.clock.Now), time.Hour)
	if err != nil {
		t.Fatalf("홀드 서비스를 만들지 못했다: %v", err)
	}

	extended, err := shorter.Extend(ctx(t), source, reference)

	if err != nil || !extended.ExpiresAt.Equal(placed.ExpiresAt) {
		t.Errorf("연장 = %+v, %v. 만료 시각은 %v 그대로여야 한다", extended, err, placed.ExpiresAt)
	}
}

func TestExtendRefusesASettledOrMissingHold(t *testing.T) {
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

	_, capturedErr := f.service.Extend(ctx(t), source, captured)
	_, releasedErr := f.service.Extend(ctx(t), source, released)
	_, missingErr := f.service.Extend(ctx(t), source, newReference())
	_, otherSourceErr := f.service.Extend(ctx(t), "board-server", captured)

	if !errors.Is(capturedErr, hold.ErrAlreadyCaptured) || !errors.Is(releasedErr, hold.ErrAlreadyReleased) {
		t.Errorf("확정한 것 = %v, 돌려준 것 = %v", capturedErr, releasedErr)
	}
	if !errors.Is(missingErr, hold.ErrNotFound) || !errors.Is(otherSourceErr, hold.ErrNotFound) {
		t.Errorf("없는 것 = %v, 다른 서버 = %v. 둘 다 ErrNotFound 이어야 한다", missingErr, otherSourceErr)
	}
}

func TestReleaseRecordsThatItWasRequested(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)

	released, err := f.service.Release(ctx(t), source, reference)

	if _, stored := f.expiry(reference); err != nil || released.ReleaseReason != hold.ReleaseRequested || stored != hold.ReleaseRequested {
		t.Errorf("반환 = %+v, %v, DB 의 이유 = %q", released, err, stored)
	}
}

func TestExpireDueGivesBackOnlyExpiredHolds(t *testing.T) {
	f := setUpSweep(t)
	f.fund(100, 30)
	early, late := newReference(), newReference()
	f.place(early)
	f.clock.Advance(time.Hour)
	f.place(late)
	f.wantBalance(30, 0)

	// 첫 홀드의 만료 시각이 꼭 지금이다. 지금과 같으면 만료된 것이다
	f.clock.Advance(ttl - time.Hour)
	f.expireDue()

	f.wantStatus(early, hold.StatusReleased)
	f.wantStatus(late, hold.StatusHeld)
	if _, reason := f.expiry(early); reason != hold.ReleaseExpired {
		t.Errorf("돌려준 이유 = %q, 기대 = expired", reason)
	}
	// 뺐던 곳으로 돌아간다. 첫 홀드는 무료 30 과 산 것 20 이었다. 무료 크레딧의 기한(1주일)은 아직이다
	f.wantBalance(50, 30)
	if got := f.count("ledger_entries", "reason = 'release'"); got != 2 {
		t.Errorf("돌아온 줄이 %d 개다. 기대 = 2 개", got)
	}
}

func TestExpireDueLeavesAnExtendedHold(t *testing.T) {
	f := setUpSweep(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)
	f.clock.Advance(ttl - time.Minute)
	if _, err := f.service.Extend(ctx(t), source, reference); err != nil {
		t.Fatalf("연장하지 못했다: %v", err)
	}

	f.clock.Advance(time.Hour)
	f.expireDue()

	f.wantStatus(reference, hold.StatusHeld)
	f.wantBalance(50, 0)
}

func TestAnExpiredHoldCanStillBeSettledUntilTheSweep(t *testing.T) {
	// 만료 시각이 지났어도 정리 작업이 아직 돌려주지 않았으면 확정, 연장할 수 있다. 시각 하나로 두 쪽이 다투지 않는다
	f := setUp(t)
	f.fund(200, 0)
	captured, extended := newReference(), newReference()
	f.place(captured)
	f.place(extended)
	f.clock.Advance(ttl + time.Hour)

	done, captureErr := f.service.Capture(ctx(t), source, captured)
	later, extendErr := f.service.Extend(ctx(t), source, extended)

	if captureErr != nil || done.Status != hold.StatusCaptured {
		t.Errorf("만료 시각이 지난 홀드의 확정 = %+v, %v", done, captureErr)
	}
	if extendErr != nil || !later.ExpiresAt.Equal(f.clock.Now().Add(ttl)) {
		t.Errorf("만료 시각이 지난 홀드의 연장 = %+v, %v", later, extendErr)
	}
}

func TestAfterTheSweepAnExpiredHoldIsReleased(t *testing.T) {
	// 게임 서버가 늦게 왔다. 확정과 연장은 거절하고, 반환은 이미 돌려줬으므로 그대로 돌려준다(두 번 돌려주지 않는다)
	f := setUpSweep(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)
	f.clock.Advance(ttl)
	f.expireDue()

	_, captureErr := f.service.Capture(ctx(t), source, reference)
	_, extendErr := f.service.Extend(ctx(t), source, reference)
	released, releaseErr := f.service.Release(ctx(t), source, reference)

	if !errors.Is(captureErr, hold.ErrAlreadyReleased) || !errors.Is(extendErr, hold.ErrAlreadyReleased) {
		t.Errorf("확정 = %v, 연장 = %v. 둘 다 ErrAlreadyReleased 이어야 한다", captureErr, extendErr)
	}
	if releaseErr != nil || released.Status != hold.StatusReleased || released.ReleaseReason != hold.ReleaseExpired {
		t.Errorf("반환 = %+v, %v", released, releaseErr)
	}
	f.wantBalance(100, 0)
	if got := f.count("ledger_entries", "reason = 'release'"); got != 1 {
		t.Errorf("돌아온 줄이 %d 개다. 기대 = 1 개", got)
	}
}

func TestExpireDueTakesTheOldestFirstUpToTheLimit(t *testing.T) {
	f := setUpSweep(t)
	f.fund(150, 0)
	references := []string{newReference(), newReference(), newReference()}
	for _, reference := range references {
		f.place(reference)
		f.clock.Advance(time.Minute)
	}
	f.clock.Advance(ttl)

	expired, err := f.service.ExpireDue(ctx(t), 2)

	if err != nil || expired != 2 {
		t.Fatalf("돌려준 수 = %d, %v. 기대 = 2", expired, err)
	}
	f.wantStatus(references[0], hold.StatusReleased)
	f.wantStatus(references[1], hold.StatusReleased)
	f.wantStatus(references[2], hold.StatusHeld)
}

func TestConcurrentSweepsAndCaptureSettleOnce(t *testing.T) {
	// 정리 작업 둘과 늦게 온 확정이 한꺼번에 온다. 하나만 이기고, 크레딧은 많아야 한 번 돌아온다
	sweep := setUpSweep(t)
	for round := range 10 {
		// 판마다 새 사용자다. 잠금은 테스트에 하나라서 setUpSweep 을 다시 부르지 않는다
		f := sweep
		f.user = uuid.New()
		f.fund(100, 0)
		reference := newReference()
		f.place(reference)
		f.clock.Advance(ttl)

		errs := together(6, func(index int) error {
			if index == 0 {
				_, err := f.service.Capture(ctx(t), source, reference)
				return err
			}
			_, err := f.service.ExpireDue(ctx(t), 1000)
			return err
		})

		var status hold.Status
		if err := f.pool.QueryRow(ctx(t), "SELECT status FROM holds WHERE reference = $1", reference).Scan(&status); err != nil {
			t.Fatalf("홀드를 읽지 못했다: %v", err)
		}
		for index, err := range errs[1:] {
			if err != nil {
				t.Errorf("%d 회 정리 작업 %d: %v", round, index, err)
			}
		}
		switch status {
		case hold.StatusCaptured:
			if errs[0] != nil {
				t.Errorf("%d 회: 확정이 이겼는데 오류다: %v", round, errs[0])
			}
			f.wantBalance(50, 0)
		case hold.StatusReleased:
			if !errors.Is(errs[0], hold.ErrAlreadyReleased) {
				t.Errorf("%d 회: 정리 작업이 이겼는데 확정의 오류 = %v", round, errs[0])
			}
			f.wantBalance(100, 0)
		default:
			t.Errorf("%d 회: 상태 = %s", round, status)
		}
		if got := f.count("ledger_entries", "reason = 'release'"); got > 1 {
			t.Errorf("%d 회: 돌아온 줄이 %d 개다", round, got)
		}
	}
}

func TestNewServiceRejectsANonPositiveTTL(t *testing.T) {
	f := setUp(t)
	for _, bad := range []time.Duration{0, -time.Hour} {
		if _, err := hold.NewService(f.pool, f.clock.Now, f.wallet, pricing.NewService(f.pool, f.clock.Now), bad); !errors.Is(err, hold.ErrInvalidTTL) {
			t.Errorf("ttl %v: %v. ErrInvalidTTL 이어야 한다", bad, err)
		}
	}
}
