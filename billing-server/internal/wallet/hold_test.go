// billing-server/internal/wallet/hold_test.go

package wallet_test

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// newHold 는 이 사용자의 홀드 한 줄을 DB 에 직접 넣고 그 번호를 돌려준다.
// 지갑의 테스트는 홀드 서비스를 쓰지 않는다. 원장이 가리킬 홀드의 줄만 있으면 된다.
func (f fixture) newHold() uuid.UUID {
	f.t.Helper()
	id := uuid.New()
	const insert = `INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at, expires_at)
		VALUES ($1, $2, 'test', $3, 'narration.standard', 50, 'held', $4, $4, $4::TIMESTAMPTZ + interval '1 day')`
	if _, err := f.pool.Exec(ctx(f.t), insert, id, f.user, "ref-"+id.String(), f.clock.Now()); err != nil {
		f.t.Fatalf("홀드를 넣지 못했다: %v", err)
	}
	return id
}

// takeForHold 는 트랜잭션을 열어 홀드로 크레딧을 뺀다. service 가 nil 이면 이 테스트의 기본 서비스를 쓴다.
func (f fixture) takeForHold(service *wallet.Service, holdID uuid.UUID, amount credit.Amount) error {
	f.t.Helper()
	if service == nil {
		service = f.service
	}
	return pgx.BeginFunc(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		return service.TakeForHold(ctx(f.t), tx, f.user, amount, holdID)
	})
}

// returnForHold 는 트랜잭션을 열어 홀드로 뺀 크레딧을 돌려놓는다.
func (f fixture) returnForHold(holdID uuid.UUID) error {
	f.t.Helper()
	return pgx.BeginFunc(ctx(f.t), f.pool, func(tx pgx.Tx) error {
		return f.service.ReturnForHold(ctx(f.t), tx, f.user, holdID)
	})
}

// mustHold 는 홀드를 하나 만들고 그만큼 뺀다.
func (f fixture) mustHold(amount credit.Amount) uuid.UUID {
	f.t.Helper()
	holdID := f.newHold()
	if err := f.takeForHold(nil, holdID, amount); err != nil {
		f.t.Fatalf("홀드로 %d 을 빼지 못했다: %v", amount, err)
	}
	return holdID
}

func TestTakeForHoldTakesFreeCreditsFirstAndNamesTheHold(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)

	holdID := f.mustHold(50)

	f.wantBalance(80, 0)
	rows := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonHold, -30},
		line{wallet.KindPaid, wallet.ReasonHold, -20},
	)
	// 한 홀드의 두 줄은 작업 번호가 같고, 둘 다 그 홀드를 가리킨다
	if rows[2].OperationID != rows[3].OperationID {
		t.Error("한 홀드의 두 줄의 작업 번호가 다르다")
	}
	var named int
	const query = "SELECT COUNT(*) FROM ledger_entries WHERE user_id = $1 AND hold_id = $2"
	if err := f.pool.QueryRow(ctx(t), query, f.user, holdID).Scan(&named); err != nil || named != 2 {
		t.Errorf("그 홀드를 가리키는 줄이 %d 개다. 기대 = 2 개 (%v)", named, err)
	}
}

func TestEntriesNameTheHoldOnHoldAndReleaseLinesOnly(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	holdID := f.mustHold(50)
	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	page, err := f.service.Entries(ctx(t), f.user, wallet.FirstPage, 10)

	if err != nil || len(page.Entries) != 3 {
		t.Fatalf("원장 = %+v, %v", page.Entries, err)
	}
	// 최근 것부터다: 돌아온 줄, 빠진 줄, 넣은 줄. 사용자는 빠진 줄과 돌아온 줄을 홀드 번호로 짝짓는다
	released, held, deposited := page.Entries[0], page.Entries[1], page.Entries[2]
	if released.HoldID == nil || held.HoldID == nil || *released.HoldID != holdID || *held.HoldID != holdID {
		t.Errorf("홀드의 줄들이 그 홀드를 가리키지 않는다: %+v, %+v", released, held)
	}
	if deposited.HoldID != nil {
		t.Errorf("넣은 줄에 홀드 %v 가 적혔다", *deposited.HoldID)
	}
}

func TestTakeForHoldFollowsTheSpendingOrder(t *testing.T) {
	f := setUp(t, paidFirst)
	f.deposit(100)
	f.grant(30)

	f.mustHold(50)

	// 산 크레딧부터 쓰는 설정이면 홀드도 산 크레딧에서 뺀다
	f.wantBalance(50, 30)
}

func TestTakeForHoldRefusesWhenShortAndChangesNothing(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(20)
	f.grant(29)

	err := f.takeForHold(nil, f.newHold(), 50)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
	f.wantBalance(20, 29)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 20},
		line{wallet.KindFree, wallet.ReasonGrant, 29},
	)
}

func TestTakeForHoldRejectsAmountsOutOfRange(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	holdID := f.newHold()

	for _, amount := range []credit.Amount{0, -1, wallet.MaxAmount + 1} {
		if err := f.takeForHold(nil, holdID, amount); !errors.Is(err, wallet.ErrInvalidAmount) {
			t.Errorf("양 %d: 오류 = %v. ErrInvalidAmount 이어야 한다", amount, err)
		}
	}
	f.wantBalance(100, 0)
}

func TestReturnForHoldPutsCreditsBackWhereTheyCameFrom(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(10)
	f.clock.Advance(24 * time.Hour)
	f.grant(20)
	holdID := f.mustHold(50)
	f.wantBalance(80, 0)

	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	f.wantBalance(100, 30)
	rows := f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 10},
		line{wallet.KindFree, wallet.ReasonGrant, 20},
		line{wallet.KindFree, wallet.ReasonHold, -10},
		line{wallet.KindFree, wallet.ReasonHold, -20},
		line{wallet.KindPaid, wallet.ReasonHold, -20},
		line{wallet.KindFree, wallet.ReasonRelease, 10},
		line{wallet.KindFree, wallet.ReasonRelease, 20},
		line{wallet.KindPaid, wallet.ReasonRelease, 20},
	)
	// 돌아온 줄은 뺐던 줄과 같은 지급 묶음을 가리킨다. 새 묶음을 만들지 않는다
	if *rows[6].GrantID != *rows[3].GrantID || *rows[7].GrantID != *rows[4].GrantID {
		t.Error("돌아온 크레딧이 뺐던 지급 묶음으로 가지 않았다")
	}
	if f.count("free_grants") != 2 {
		t.Errorf("지급 묶음이 %d 개다. 돌려줄 때 새로 만들면 안 된다", f.count("free_grants"))
	}
	// 돌려준 줄들은 뺀 줄들과 다른 작업이다
	if rows[6].OperationID == rows[3].OperationID || rows[6].OperationID != rows[8].OperationID {
		t.Error("돌려준 줄들의 작업 번호가 맞지 않는다")
	}
}

func TestReturnedFreeCreditsKeepTheirOriginalExpiry(t *testing.T) {
	f := setUp(t, freeFirst)
	f.grant(30)
	f.clock.Advance(3 * 24 * time.Hour)
	holdID := f.mustHold(30)
	f.clock.Advance(3 * 24 * time.Hour)

	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	// 엿새째에 돌아왔다. 기한은 준 날에서 이레째 그대로다. 홀드한 사흘만큼 늘어나지 않는다
	f.wantBalance(0, 30)
	f.clock.Advance(24 * time.Hour)
	f.wantBalance(0, 0)
}

func TestFreeCreditsReturnedAfterTheirExpiryAreGone(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)
	holdID := f.mustHold(50)
	// 홀드한 사이에 무료 크레딧의 기한이 지났다
	f.clock.Advance(week)

	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	// 산 크레딧 20 은 돌아오고, 무료 30 은 돌아오자마자 사라진다. 홀드로 기한을 피할 수 없다
	f.wantBalance(100, 0)
	f.wantLedger(
		line{wallet.KindPaid, wallet.ReasonDeposit, 100},
		line{wallet.KindFree, wallet.ReasonGrant, 30},
		line{wallet.KindFree, wallet.ReasonHold, -30},
		line{wallet.KindPaid, wallet.ReasonHold, -20},
		line{wallet.KindFree, wallet.ReasonRelease, 30},
		line{wallet.KindPaid, wallet.ReasonRelease, 20},
		// 돌아왔다는 줄 바로 뒤에 사라졌다는 줄이 남는다. 원장만 봐도 무슨 일이 있었는지 안다
		line{wallet.KindFree, wallet.ReasonExpire, -30},
	)
}

func TestReturnForHoldRefusesTheSameHoldTwice(t *testing.T) {
	cases := []struct {
		name string
		free credit.Amount
		// code 는 둘째를 거절하는 DB 의 오류다
		code string
	}{
		// 산 크레딧의 묶음도 넣은 양보다 많이 남을 수 없다. 묶음이 가득 차 있으면 그 조건에 먼저 걸린다
		{"산 크레딧만 뺀 홀드", 0, checkViolation},
		// 무료 크레딧도 준 양보다 많이 남을 수 없다는 조건에 걸린다
		{"무료 크레딧도 뺀 홀드", 30, checkViolation},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := setUp(t, freeFirst)
			f.deposit(100)
			if tc.free > 0 {
				f.grant(tc.free)
			}
			holdID := f.mustHold(50)
			if err := f.returnForHold(holdID); err != nil {
				t.Fatalf("돌려놓지 못했다: %v", err)
			}

			err := f.returnForHold(holdID)

			// 부르는 쪽의 실수로 두 번 불러도 DB 가 둘째를 거절하고, 잔액도 함께 되돌려진다
			var pgErr *pgconn.PgError
			if !errors.As(err, &pgErr) || pgErr.Code != tc.code {
				t.Fatalf("오류 = %v. SQLSTATE %s 로 거절해야 한다", err, tc.code)
			}
			f.wantBalance(100, tc.free)
		})
	}
}

func TestReturnForHoldGivesBackOnlyThatHold(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	first := f.mustHold(30)
	f.mustHold(40)

	if err := f.returnForHold(first); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	// 첫 홀드의 30 만 돌아온다. 둘째 홀드의 40 은 빠진 채다
	f.wantBalance(60, 0)
}

func TestReturnForHoldOfAnotherUsersHoldGivesNothing(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	holdID := f.mustHold(50)
	other := setUp(t, freeFirst)

	// 다른 사용자의 지갑으로 그 홀드를 돌려 달라고 한다
	err := pgx.BeginFunc(ctx(t), other.pool, func(tx pgx.Tx) error {
		return other.service.ReturnForHold(ctx(t), tx, other.user, holdID)
	})

	if err != nil {
		t.Fatalf("오류 = %v", err)
	}
	other.wantBalance(0, 0)
	f.wantBalance(50, 0)
}

func TestConcurrentHoldsNeverTakeMoreThanHeld(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(60)
	f.grant(40)
	holds := make([]uuid.UUID, 20)
	for index := range holds {
		holds[index] = f.newHold()
	}

	// 10 씩 스무 번을 한꺼번에 건다. 가진 것은 열 번어치다
	var next atomicCounter
	errs := together(20, func() error {
		return f.takeForHold(nil, holds[next.take()], 10)
	})

	succeeded, refused := tally(t, errs)
	if succeeded != 10 || refused != 10 {
		t.Errorf("성공 %d, 거절 %d. 기대 = 성공 10, 거절 10", succeeded, refused)
	}
	f.wantBalance(0, 0)
}

func TestReturnForHoldRefusesTheSameHoldTwiceEvenWithRoomInTheLot(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.spend(60)
	// 묶음에 40 이 남았다. 홀드가 30 을 빼고 돌려주면 다시 40 이다. 한 번 더 돌려줘도 넣은 양(100)을 넘지 않는다
	holdID := f.mustHold(30)
	if err := f.returnForHold(holdID); err != nil {
		t.Fatalf("돌려놓지 못했다: %v", err)
	}

	err := f.returnForHold(holdID)

	// 묶음의 조건에 걸리지 않아도, 같은 홀드의 줄을 두 번 적지 못하게 하는 색인이 막는다
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) || pgErr.Code != "23505" {
		t.Fatalf("오류 = %v. SQLSTATE 23505 로 거절해야 한다", err)
	}
	f.wantBalance(40, 0)
}

func TestTheDatabaseKeepsHoldLinesInStep(t *testing.T) {
	f := setUp(t, freeFirst)
	f.deposit(100)
	f.grant(30)
	holdID := f.mustHold(50)
	grantID := *f.ledger()[1].GrantID
	lotID := f.lots()[0].ID

	const insert = `INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, grant_id, lot_id, hold_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`
	now := f.clock.Now()
	cases := []struct {
		name    string
		code    string
		kind    string
		reason  string
		amount  int64
		grantID *int64
		lotID   *int64
		holdID  *uuid.UUID
	}{
		{"홀드인데 늘었다", checkViolation, "paid", "hold", 10, nil, &lotID, &holdID},
		{"돌아왔는데 줄었다", checkViolation, "paid", "release", -10, nil, &lotID, &holdID},
		{"홀드의 줄인데 홀드가 없다", checkViolation, "paid", "hold", -10, nil, &lotID, nil},
		{"홀드의 줄이 아닌데 홀드가 있다", checkViolation, "paid", "spend", -10, nil, &lotID, &holdID},
		{"같은 묶음에서 두 번 뺐다", "23505", "paid", "hold", -10, nil, &lotID, &holdID},
		{"같은 지급 묶음에서 두 번 뺐다", "23505", "free", "hold", -1, &grantID, nil, &holdID},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f.wantRefused(tc.code, insert, f.user, uuid.New(), tc.kind, tc.reason, tc.amount, tc.grantID, tc.lotID, tc.holdID, now)
		})
	}
	// 없는 홀드를 가리킬 수 없다
	missing := uuid.New()
	f.wantRefused(foreignKeyViolation, insert, f.user, uuid.New(), "paid", "hold", -10, nil, &lotID, &missing, now)
	f.wantBalance(80, 0)
}
