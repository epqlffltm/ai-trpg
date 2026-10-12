// billing-server/internal/hold/hold_test.go

package hold_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestPlaceTakesThePriceFromTheWallet(t *testing.T) {
	f := setUp(t)
	f.fund(100, 30)
	reference := newReference()

	placed, isNew, err := f.service.Place(ctx(t), source, f.user, reference, priceCode)

	if err != nil || !isNew {
		t.Fatalf("홀드를 걸지 못했다: %v, 새로 걺 = %v", err, isNew)
	}
	// 값은 가격표에서 온다. 부르는 쪽은 금액을 보내지 않았다
	if placed.ID == uuid.Nil || placed.UserID != f.user || placed.Reference != reference ||
		placed.PriceCode != priceCode || placed.Amount != price {
		t.Errorf("홀드 = %+v", placed)
	}
	if placed.Status != hold.StatusHeld || placed.SettledAt != nil || !placed.CreatedAt.Equal(f.clock.Now()) {
		t.Errorf("새 홀드가 held 의 모양이 아니다: %+v", placed)
	}
	// 무료 30 을 먼저 쓰고 산 것에서 20 을 뺐다
	f.wantBalance(80, 0)
	f.wantStatus(reference, hold.StatusHeld)
}

func TestPlaceWithTheSameReferenceTakesOnce(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	first := f.place(reference)

	second, isNew, err := f.service.Place(ctx(t), source, f.user, reference, priceCode)

	// 응답을 못 받아 다시 보낸 요청이다. 새로 빼지 않고 먼저 건 홀드를 돌려준다
	if err != nil || isNew || second.ID != first.ID {
		t.Errorf("다시 보낸 요청 = %v, 새로 걺 = %v, %v. 먼저 건 홀드 %v 이어야 한다", second.ID, isNew, err, first.ID)
	}
	f.wantBalance(50, 0)
	if f.count("holds", "") != 1 {
		t.Errorf("홀드가 %d 개다", f.count("holds", ""))
	}
}

func TestPlaceAfterTheHoldIsSettledStillReturnsIt(t *testing.T) {
	// 확정하거나 돌려준 뒤에 같은 이름표로 다시 와도 새 홀드를 걸지 않는다. 지금의 상태를 돌려준다
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

	again, isNew, err := f.service.Place(ctx(t), source, f.user, captured, priceCode)
	if err != nil || isNew || again.Status != hold.StatusCaptured {
		t.Errorf("확정한 홀드의 다시 걸기 = %+v, 새로 걺 = %v, %v", again, isNew, err)
	}
	again, isNew, err = f.service.Place(ctx(t), source, f.user, released, priceCode)
	if err != nil || isNew || again.Status != hold.StatusReleased {
		t.Errorf("돌려준 홀드의 다시 걸기 = %+v, 새로 걺 = %v, %v", again, isNew, err)
	}
	// 확정한 50 만 빠져 있다. 다시 걸었다고 더 빠지지 않았다
	f.wantBalance(150, 0)
}

func TestPlaceRefusesAReferenceReusedForAnotherUser(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	other := setUp(t)
	other.fund(100, 0)
	reference := newReference()
	f.place(reference)

	_, _, err := other.service.Place(ctx(t), source, other.user, reference, priceCode)

	if !errors.Is(err, hold.ErrReferenceReused) {
		t.Errorf("오류 = %v. ErrReferenceReused 이어야 한다", err)
	}
	// 다른 사용자의 크레딧은 빠지지 않았다
	other.wantBalance(100, 0)
	f.wantBalance(50, 0)
}

func TestPlaceRefusesAReferenceReusedForAnotherPrice(t *testing.T) {
	// 가격표에는 지금 줄이 하나라서, 다른 값으로 건 홀드를 DB 에 직접 넣어 둔다
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	_, err := f.pool.Exec(ctx(t), `INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at, expires_at)
		VALUES ($1, $2, $3, $4, 'narration.premium', 200, 'held', $5, $5, $5::TIMESTAMPTZ + interval '1 day')`, uuid.New(), f.user, source, reference, f.clock.Now())
	if err != nil {
		t.Fatalf("홀드를 넣지 못했다: %v", err)
	}

	_, _, err = f.service.Place(ctx(t), source, f.user, reference, priceCode)

	// 같은 이름표인데 값이 다르다. 다시 보낸 요청이 아니다. 조용히 먼저 것을 돌려주지 않는다
	if !errors.Is(err, hold.ErrReferenceReused) {
		t.Errorf("오류 = %v. ErrReferenceReused 이어야 한다", err)
	}
	f.wantBalance(100, 0)
}

func TestReferencesBelongToEachSource(t *testing.T) {
	// 서로 다른 서버가 우연히 같은 이름표를 써도 서로의 홀드가 되지 않는다
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()

	mine, _, errMine := f.service.Place(ctx(t), source, f.user, reference, priceCode)
	theirs, isNew, errTheirs := f.service.Place(ctx(t), "board-server", f.user, reference, priceCode)

	if errMine != nil || errTheirs != nil || !isNew || mine.ID == theirs.ID {
		t.Errorf("홀드 %v, %v (새로 걺 = %v): %v, %v", mine.ID, theirs.ID, isNew, errMine, errTheirs)
	}
	f.wantBalance(0, 0)
	// 다른 서버의 이름으로는 그 홀드를 확정하지 못한다
	if _, err := f.service.Capture(ctx(t), "auth-server", reference); !errors.Is(err, hold.ErrNotFound) {
		t.Errorf("다른 서버의 확정 = %v. ErrNotFound 이어야 한다", err)
	}
}

func TestAnotherSourceCannotSeeOrSettleAHold(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)
	if _, err := f.service.Capture(ctx(t), source, reference); err != nil {
		t.Fatalf("확정하지 못했다: %v", err)
	}

	// 다른 서버에게 그 이름표는 없는 홀드다. "이미 확정했다"고도 알려 주지 않는다
	_, captureErr := f.service.Capture(ctx(t), "auth-server", reference)
	_, releaseErr := f.service.Release(ctx(t), "auth-server", reference)

	if !errors.Is(captureErr, hold.ErrNotFound) || !errors.Is(releaseErr, hold.ErrNotFound) {
		t.Errorf("다른 서버의 확정 = %v, 반환 = %v. 둘 다 ErrNotFound 이어야 한다", captureErr, releaseErr)
	}
	f.wantStatus(reference, hold.StatusCaptured)
	f.wantBalance(50, 0)
}

func TestPlaceRefusesWhenCreditsAreShortAndLeavesNoHold(t *testing.T) {
	f := setUp(t)
	f.fund(20, 29)
	reference := newReference()

	_, _, err := f.service.Place(ctx(t), source, f.user, reference, priceCode)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. wallet.ErrInsufficient 이어야 한다", err)
	}
	// 크레딧을 빼지 못했으면 홀드도 남지 않는다. 둘은 함께 되거나 함께 안 된다
	f.wantBalance(20, 29)
	if f.count("holds", "") != 0 {
		t.Error("크레딧을 못 뺐는데 홀드가 남았다")
	}

	// 충전한 뒤 같은 이름표로 다시 걸 수 있다. 실패한 시도가 이름표를 차지하지 않는다
	f.fund(1, 0)
	if _, isNew, err := f.service.Place(ctx(t), source, f.user, reference, priceCode); err != nil || !isNew {
		t.Errorf("충전한 뒤의 홀드 = 새로 걺 %v, %v", isNew, err)
	}
	f.wantBalance(0, 0)
}

func TestPlaceRejectsBadInput(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	references := map[string]string{
		"비었다":   "",
		"너무 짧다": "round-3",
		"너무 길다": strings.Repeat("r", 201),
		"빈칸":    "table 1 round 3",
		"줄 바꿈":  "table:1:round:3\n",
		"한글":    "테이블:1:라운드:3",
		"따옴표":   `table:"1":round:3`,
	}
	for name, reference := range references {
		t.Run(name, func(t *testing.T) {
			if _, _, err := f.service.Place(ctx(t), source, f.user, reference, priceCode); !errors.Is(err, hold.ErrInvalidReference) {
				t.Errorf("오류 = %v. ErrInvalidReference 이어야 한다", err)
			}
		})
	}
	for _, code := range []string{"", "narration", "narration.free", "NARRATION.STANDARD"} {
		if _, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code); !errors.Is(err, hold.ErrUnknownPrice) {
			t.Errorf("가격표 이름 %q: 오류 = %v. ErrUnknownPrice 이어야 한다", code, err)
		}
	}
	f.wantBalance(100, 0)
	if f.count("holds", "") != 0 {
		t.Error("거절했는데 홀드가 생겼다")
	}
}

func TestCaptureKeepsTheCreditsAndIsSafeToRepeat(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	placed := f.place(reference)
	f.clock.Advance(40 * 1e9)

	captured, err := f.service.Capture(ctx(t), source, reference)

	if err != nil || captured.ID != placed.ID || captured.Status != hold.StatusCaptured {
		t.Fatalf("확정 = %+v, %v", captured, err)
	}
	if captured.SettledAt == nil || !captured.SettledAt.Equal(f.clock.Now()) {
		t.Errorf("확정한 시각 = %v, 기대 = %v", captured.SettledAt, f.clock.Now())
	}
	// 크레딧은 홀드를 걸 때 이미 빠졌다. 확정은 잔액도 원장도 바꾸지 않는다
	f.wantBalance(50, 0)
	lines := f.count("ledger_entries", "")

	again, err := f.service.Capture(ctx(t), source, reference)
	if err != nil || again.Status != hold.StatusCaptured || !again.SettledAt.Equal(*captured.SettledAt) {
		t.Errorf("다시 확정 = %+v, %v", again, err)
	}
	f.wantBalance(50, 0)
	if f.count("ledger_entries", "") != lines {
		t.Error("확정이 원장에 줄을 남겼다")
	}
	f.wantStatus(reference, hold.StatusCaptured)
}

func TestReleaseGivesTheCreditsBackOnce(t *testing.T) {
	f := setUp(t)
	f.fund(100, 30)
	reference := newReference()
	f.place(reference)
	f.wantBalance(80, 0)

	released, err := f.service.Release(ctx(t), source, reference)

	if err != nil || released.Status != hold.StatusReleased || released.SettledAt == nil {
		t.Fatalf("반환 = %+v, %v", released, err)
	}
	// 뺐던 곳으로 돌아간다. 무료 30, 산 것 20
	f.wantBalance(100, 30)
	f.wantStatus(reference, hold.StatusReleased)

	// 몇 번을 불러도 크레딧은 한 번만 돌아간다
	for range 3 {
		again, err := f.service.Release(ctx(t), source, reference)
		if err != nil || again.Status != hold.StatusReleased {
			t.Errorf("다시 반환 = %+v, %v", again, err)
		}
	}
	f.wantBalance(100, 30)
	if got := f.count("ledger_entries", "reason = 'release'"); got != 2 {
		t.Errorf("돌아온 줄이 %d 개다. 기대 = 2 개", got)
	}
}

func TestACapturedHoldCannotBeReleasedAndTheReverse(t *testing.T) {
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

	// 확정한 것을 돌려 달라고 한다. 서술의 값을 받고 크레딧도 돌려주는 일이 된다
	if _, err := f.service.Release(ctx(t), source, captured); !errors.Is(err, hold.ErrAlreadyCaptured) {
		t.Errorf("확정한 홀드의 반환 = %v. ErrAlreadyCaptured 이어야 한다", err)
	}
	// 돌려준 것을 확정한다. 크레딧을 받지 않고 값을 받은 것으로 적는 일이 된다
	if _, err := f.service.Capture(ctx(t), source, released); !errors.Is(err, hold.ErrAlreadyReleased) {
		t.Errorf("돌려준 홀드의 확정 = %v. ErrAlreadyReleased 이어야 한다", err)
	}
	f.wantStatus(captured, hold.StatusCaptured)
	f.wantStatus(released, hold.StatusReleased)
	f.wantBalance(150, 0)
}

func TestSettlingAHoldThatDoesNotExist(t *testing.T) {
	f := setUp(t)

	_, captureErr := f.service.Capture(ctx(t), source, newReference())
	_, releaseErr := f.service.Release(ctx(t), source, newReference())

	if !errors.Is(captureErr, hold.ErrNotFound) || !errors.Is(releaseErr, hold.ErrNotFound) {
		t.Errorf("확정 = %v, 반환 = %v. 둘 다 ErrNotFound 이어야 한다", captureErr, releaseErr)
	}
}

func TestReleasedFreeCreditsExpireOnTheirOriginalSchedule(t *testing.T) {
	f := setUp(t)
	f.fund(100, 30)
	reference := newReference()
	f.place(reference)
	// 홀드한 사이에 무료 크레딧의 기한이 지났다
	f.clock.Advance(week)

	if _, err := f.service.Release(ctx(t), source, reference); err != nil {
		t.Fatalf("돌려주지 못했다: %v", err)
	}

	// 산 크레딧 20 은 돌아오고, 무료 30 은 돌아오자마자 사라진다
	f.wantBalance(100, 0)
	if got := f.count("ledger_entries", "reason = 'expire' AND amount = -30"); got != 1 {
		t.Errorf("사라졌다는 줄이 %d 개다. 기대 = 1 개", got)
	}
}

func TestConcurrentPlacesWithOneReferenceTakeOnce(t *testing.T) {
	f := setUp(t)
	f.fund(1000, 0)
	reference := newReference()
	ids := make([]uuid.UUID, 20)
	fresh := make([]bool, 20)

	errs := together(20, func(index int) error {
		placed, isNew, err := f.service.Place(ctx(t), source, f.user, reference, priceCode)
		ids[index], fresh[index] = placed.ID, isNew
		return err
	})

	made := 0
	for index, err := range errs {
		if err != nil || ids[index] != ids[0] {
			t.Errorf("%d 번째: 홀드 %v, %v. 모두 같은 홀드여야 한다", index, ids[index], err)
		}
		if fresh[index] {
			made++
		}
	}
	// 같은 요청 스무 개가 함께 왔어도 한 번만 뺐다
	if made != 1 {
		t.Errorf("새로 걸었다는 답이 %d 번이다", made)
	}
	f.wantBalance(950, 0)
}

func TestConcurrentPlacesNeverTakeMoreThanHeld(t *testing.T) {
	f := setUp(t)
	// 값이 50 이다. 다섯 번어치를 갖고 스무 번을 한꺼번에 건다
	f.fund(150, 100)

	errs := together(20, func(int) error {
		_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), priceCode)
		return err
	})

	placed, refused := 0, 0
	for _, err := range errs {
		switch {
		case err == nil:
			placed++
		case errors.Is(err, wallet.ErrInsufficient):
			refused++
		default:
			t.Errorf("뜻밖의 오류: %v", err)
		}
	}
	if placed != 5 || refused != 15 {
		t.Errorf("성공 %d, 거절 %d. 기대 = 성공 5, 거절 15", placed, refused)
	}
	f.wantBalance(0, 0)
	if f.count("holds", "") != 5 {
		t.Errorf("홀드가 %d 개다. 거절된 것은 남지 않아야 한다", f.count("holds", ""))
	}
}

func TestConcurrentCaptureAndReleaseSettleOnce(t *testing.T) {
	// 확정과 반환이 한꺼번에 온다. 어느 쪽이 이기든 하나만 된다. 크레딧이 사라지지도 두 번 돌아오지도 않는다
	for round := range 10 {
		f := setUp(t)
		f.fund(100, 0)
		reference := newReference()
		f.place(reference)

		errs := together(8, func(index int) error {
			if index%2 == 0 {
				_, err := f.service.Capture(ctx(t), source, reference)
				return err
			}
			_, err := f.service.Release(ctx(t), source, reference)
			return err
		})

		var status hold.Status
		if err := f.pool.QueryRow(ctx(t), "SELECT status FROM holds WHERE reference = $1", reference).Scan(&status); err != nil {
			t.Fatalf("홀드를 읽지 못했다: %v", err)
		}
		for index, err := range errs {
			won := (index%2 == 0) == (status == hold.StatusCaptured)
			if won && err != nil {
				t.Errorf("%d 회 %d 번째: 이긴 쪽인데 오류다: %v", round, index, err)
			}
			if !won && !errors.Is(err, hold.ErrAlreadyCaptured) && !errors.Is(err, hold.ErrAlreadyReleased) {
				t.Errorf("%d 회 %d 번째: 진 쪽의 오류 = %v", round, index, err)
			}
		}
		if status == hold.StatusCaptured {
			f.wantBalance(50, 0)
		} else {
			f.wantBalance(100, 0)
		}
	}
}

func TestTheDatabaseKeepsHoldStatusAndColumnsInStep(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	placed := f.place(reference)

	cases := map[string]string{
		"모르는 상태":             "UPDATE holds SET status = 'expired', settled_at = created_at WHERE id = $1",
		"끝난 시각이 있는 held":     "UPDATE holds SET settled_at = created_at WHERE id = $1",
		"끝난 시각이 없는 captured": "UPDATE holds SET status = 'captured' WHERE id = $1",
		"값이 0":               "UPDATE holds SET amount = 0 WHERE id = $1",
		"이유가 없는 released":    "UPDATE holds SET status = 'released', settled_at = created_at WHERE id = $1",
		"이유가 있는 held":        "UPDATE holds SET release_reason = 'requested' WHERE id = $1",
		"이유가 있는 captured":    "UPDATE holds SET status = 'captured', settled_at = created_at, release_reason = 'expired' WHERE id = $1",
		"모르는 이유":             "UPDATE holds SET status = 'released', settled_at = created_at, release_reason = 'forgot' WHERE id = $1",
		"만든 때에 만료":           "UPDATE holds SET expires_at = created_at WHERE id = $1",
	}
	for name, sql := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := f.pool.Exec(ctx(t), sql, placed.ID)
			if err == nil || !strings.Contains(err.Error(), "23514") {
				t.Errorf("오류 = %v. CHECK(23514)로 거절해야 한다", err)
			}
		})
	}
	// 같은 서버의 같은 이름표로 줄을 하나 더 넣을 수 없다
	_, err := f.pool.Exec(ctx(t), `INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at, expires_at)
		VALUES ($1, $2, $3, $4, 'narration.standard', 50, 'held', $5, $5, $5::TIMESTAMPTZ + interval '1 day')`, uuid.New(), f.user, source, reference, f.clock.Now())
	if err == nil || !strings.Contains(err.Error(), "23505") {
		t.Errorf("오류 = %v. 중복(23505)으로 거절해야 한다", err)
	}
}
