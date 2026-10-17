// billing-server/internal/reconcile/reconcile_test.go

// 대사를 실제 서비스와 DB 로 시험한다. 장부를 DB 에서 직접 어긋나게 만들어 두고, 대사가 그 줄을 찾는지 본다.
//
// 테스트용 스키마에는 다른 테스트가 남긴 줄이 있다(일부러 어긋나게 만든 것도 있다). 그래서 걸린 줄의 수가 아니라
// 이 테스트가 만든 줄이 걸렸는지, 걸리지 않았는지를 본다. 검사의 limit 은 그 줄들이 다 나올 만큼 크게 준다.
package reconcile_test

import (
	"context"
	"errors"
	"slices"
	"strconv"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/reconcile"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const (
	// everything 는 검사가 스키마의 어긋난 줄을 모두 돌려줄 만큼 큰 limit 이다.
	everything = 10_000_000
	staleAfter = 10 * time.Minute
	source     = "game-server"
)

var rules = config.Rules{SpendFreeFirst: true, FreeCreditTTL: 7 * 24 * time.Hour, HoldTTL: 24 * time.Hour, OrderTTL: 24 * time.Hour}

// fixture 는 테스트 하나가 쓰는 것들이다. 시계는 정리 작업의 시대에 있다(testenv.SweepEra).
type fixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	elapsed  *time.Duration
	services app.Services
	reviews  *pricereview.Service
	user     uuid.UUID
}

// setUp 은 대사의 테스트를 준비한다. 대사도 시각으로 줄을 고르므로 정리 작업의 테스트처럼 잠그고 그 시대의 시계를 쓴다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	testenv.ExclusiveSweep(t, pool)
	elapsed := new(time.Duration)
	now := func() time.Time { return testenv.SweepEra.Add(*elapsed) }
	services, err := app.NewServices(pool, rules, order.Providers{order.ChannelWeb: payment.Fake{}}, now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	return fixture{t: t, pool: pool, elapsed: elapsed, services: services, reviews: pricereview.NewService(pool, now), user: uuid.New()}
}

func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)
	return limited
}

// now 는 이 테스트의 지금 시각이다.
func (f fixture) now() time.Time {
	return testenv.SweepEra.Add(*f.elapsed)
}

// run 은 대사를 한 번 한다.
func (f fixture) run() reconcile.Report {
	f.t.Helper()
	report, err := reconcile.New(f.pool, f.services.Orders, f.reviews, f.now).Run(ctx(f.t), reconcile.Options{StaleAfter: staleAfter, Limit: everything})
	if err != nil {
		f.t.Fatalf("대사가 실패했다: %v", err)
	}
	return report
}

// exec 는 서비스를 거치지 않고 DB 를 바꾼다. 장부를 일부러 어긋나게 만들 때 쓴다.
func (f fixture) exec(sql string, args ...any) {
	f.t.Helper()
	if _, err := f.pool.Exec(ctx(f.t), sql, args...); err != nil {
		f.t.Fatalf("DB 를 바꾸지 못했다: %v", err)
	}
}

// buy 는 주문을 만들고 치른다. 치른 주문을 돌려준다.
func (f fixture) buy() order.Order {
	f.t.Helper()
	return f.buyWith("")
}

// buyWith 는 결제 번호에 marker 를 넣어 주문을 만들고 치른다. 가짜 결제 대행사가 취소에 어떻게 답할지 정한다.
func (f fixture) buyWith(marker string) order.Order {
	f.t.Helper()
	created, _, err := f.services.Orders.Create(ctx(f.t), f.user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		f.t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	paid, err := f.services.Orders.Confirm(ctx(f.t), f.user, created.ID, payment.FakeApproved+marker+uuid.NewString())
	if err != nil || paid.Status != order.StatusPaid {
		f.t.Fatalf("주문을 치르지 못했다: %+v, %v", paid, err)
	}
	return paid
}

// place 는 홀드를 건다.
func (f fixture) place() hold.Hold {
	f.t.Helper()
	placed, _, err := f.services.Holds.Place(ctx(f.t), source, f.user, "table:"+uuid.NewString()+":round:1", pricing.NarrationStandard)
	if err != nil {
		f.t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	return placed
}

// grantIDs 는 이 사용자의 지급 묶음 번호들이다.
func (f fixture) grantIDs() []string {
	f.t.Helper()
	rows, err := f.pool.Query(ctx(f.t), "SELECT id FROM free_grants WHERE user_id = $1", f.user)
	if err != nil {
		f.t.Fatalf("지급 묶음을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			f.t.Fatalf("지급 묶음을 읽지 못했다: %v", err)
		}
		ids = append(ids, strconv.FormatInt(id, 10))
	}
	return ids
}

// lotIDs 는 이 사용자의 산 크레딧 묶음 번호들이다.
func (f fixture) lotIDs() []string {
	f.t.Helper()
	rows, err := f.pool.Query(ctx(f.t), "SELECT id FROM paid_lots WHERE user_id = $1 ORDER BY id", f.user)
	if err != nil {
		f.t.Fatalf("묶음을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			f.t.Fatalf("묶음을 읽지 못했다: %v", err)
		}
		ids = append(ids, strconv.FormatInt(id, 10))
	}
	return ids
}

// flagged 는 그 검사에서 걸린 번호들이다.
func flagged(report reconcile.Report, check string) []string {
	var ids []string
	for _, m := range report.Mismatches {
		if m.Check == check {
			ids = append(ids, m.ID)
		}
	}
	return ids
}

// wantFlagged 는 그 검사가 id 를 찾았는지 본다.
func wantFlagged(t *testing.T, report reconcile.Report, check string, id string) {
	t.Helper()
	if !slices.Contains(flagged(report, check), id) {
		t.Errorf("%s 검사가 %s 를 찾지 못했다", check, id)
	}
}

// lotChecks 와 grantChecks 는 번호가 산 크레딧의 묶음, 지급 묶음의 번호인 검사들이다.
// 숫자 번호는 표마다 따로 매겨져서, 다른 검사(원장의 줄 번호)의 번호와 같을 수 있다. 그래서 그 검사들에서만 찾는다.
var (
	lotChecks   = []string{reconcile.CheckPaidLotRemaining, reconcile.CheckLotRefund}
	grantChecks = []string{reconcile.CheckGrantRemaining}
)

// wantNotFlaggedIn 은 그 검사들이 ids 를 찾지 않았는지 본다. 숫자 번호(묶음)를 볼 때 쓴다.
func wantNotFlaggedIn(t *testing.T, report reconcile.Report, checks []string, ids ...string) {
	t.Helper()
	for _, m := range report.Mismatches {
		if slices.Contains(checks, m.Check) && slices.Contains(ids, m.ID) {
			t.Errorf("맞는 줄이 %s 검사에 걸렸다: %s", m.Check, m.ID)
		}
	}
}

// wantNotFlagged 는 이 테스트의 줄들이 어느 검사에도 걸리지 않았는지 본다. UUID 번호(사용자, 주문, 홀드)를 볼 때 쓴다.
func wantNotFlagged(t *testing.T, report reconcile.Report, ids ...string) {
	t.Helper()
	for _, m := range report.Mismatches {
		if slices.Contains(ids, m.ID) {
			t.Errorf("맞는 줄이 %s 검사에 걸렸다: %s", m.Check, m.ID)
		}
	}
}

func TestBooksKeptByTheServicesAreClean(t *testing.T) {
	f := setUp(t)
	ctx := ctx(t)
	paid := f.buy()
	if err := f.services.Wallet.GrantFree(ctx, f.user, 30); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}
	if err := f.services.Wallet.Spend(ctx, f.user, 40); err != nil {
		t.Fatalf("크레딧을 쓰지 못했다: %v", err)
	}
	captured, released, expired := f.place(), f.place(), f.place()
	if _, err := f.services.Holds.Capture(ctx, source, captured.Reference); err != nil {
		t.Fatalf("확정하지 못했다: %v", err)
	}
	if _, err := f.services.Holds.Release(ctx, source, released.Reference); err != nil {
		t.Fatalf("돌려주지 못했다: %v", err)
	}
	*f.elapsed = 8 * 24 * time.Hour
	if _, err := f.services.Holds.ExpireDue(ctx, everything); err != nil {
		t.Fatalf("정리 작업이 실패했다: %v", err)
	}
	if _, err := f.services.Wallet.ExpireIdle(ctx, everything); err != nil {
		t.Fatalf("정리 작업이 실패했다: %v", err)
	}

	report := f.run()

	wantNotFlagged(t, report, f.user.String(), paid.ID.String(), captured.ID.String(), released.ID.String(), expired.ID.String())
	wantNotFlaggedIn(t, report, grantChecks, f.grantIDs()...)
	wantNotFlaggedIn(t, report, lotChecks, f.lotIDs()...)
}

func TestRefundsKeptByTheServicesAreClean(t *testing.T) {
	f := setUp(t)
	ctx := ctx(t)
	// 환불됨, 거절되어 되돌림, 결과를 모름(환불 중), 손대지 않음
	refunded, refused, unsure, kept := f.buy(), f.buyWith(payment.FakeCancelRefused), f.buyWith(payment.FakeCancelLost), f.buy()
	if got, err := f.services.Orders.Refund(ctx, f.user, refunded.ID); err != nil || got.Status != order.StatusRefunded {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	if _, err := f.services.Orders.Refund(ctx, f.user, refused.ID); !errors.Is(err, order.ErrRefundRefused) {
		t.Fatalf("오류 = %v. ErrRefundRefused 여야 한다", err)
	}
	if got, err := f.services.Orders.Refund(ctx, f.user, unsure.ID); err != nil || got.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v", got, err)
	}

	report := f.run()

	ids := []string{f.user.String(), refunded.ID.String(), refused.ID.String(), unsure.ID.String(), kept.ID.String()}
	wantNotFlagged(t, report, ids...)
	wantNotFlaggedIn(t, report, lotChecks, f.lotIDs()...)
}

func TestRefundLinesThatDoNotMatchTheOrderAreFound(t *testing.T) {
	f := setUp(t)
	ctx := ctx(t)
	refunded, paid := f.buy(), f.buy()
	if got, err := f.services.Orders.Refund(ctx, f.user, refunded.ID); err != nil || got.Status != order.StatusRefunded {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	// 환불했는데 주문은 치른 채로 적혔다. 돈은 돌아갔는데 화면에는 산 것으로 보인다
	f.exec("UPDATE orders SET status = 'paid', refunded_at = NULL WHERE id = $1", refunded.ID)
	// 환불되었다고 적혔는데 크레딧을 빼지 않았다. refunding 으로 만들지 않는다. 다른 테스트의 대사가 그 주문에 취소를 보낸다
	f.exec("UPDATE orders SET status = 'refunded', refunded_at = $2 WHERE id = $1", paid.ID, f.now())
	var refundedLot, paidLot string
	if err := f.pool.QueryRow(ctx, "SELECT id::TEXT FROM paid_lots WHERE order_id = $1", refunded.ID).Scan(&refundedLot); err != nil {
		t.Fatalf("묶음을 읽지 못했다: %v", err)
	}
	if err := f.pool.QueryRow(ctx, "SELECT id::TEXT FROM paid_lots WHERE order_id = $1", paid.ID).Scan(&paidLot); err != nil {
		t.Fatalf("묶음을 읽지 못했다: %v", err)
	}

	report := f.run()

	wantFlagged(t, report, reconcile.CheckLotRefund, refundedLot)
	wantFlagged(t, report, reconcile.CheckLotRefund, paidLot)
	// 원장과 묶음과 지갑은 서로 맞는다. 어긋난 것은 주문의 상태뿐이다
	for _, check := range []string{reconcile.CheckPaidBalance, reconcile.CheckPaidLotRemaining, reconcile.CheckPaidLotTotal} {
		for _, id := range []string{f.user.String(), refundedLot, paidLot} {
			if slices.Contains(flagged(report, check), id) {
				t.Errorf("%s 가 %s 검사에 걸렸다", id, check)
			}
		}
	}
}

func TestAPaidLotThatDisagreesIsFound(t *testing.T) {
	f := setUp(t)
	paid := f.buy()
	// 원장에 적지 않고 묶음의 남은 양만 바꾼다. 묶음의 원장도, 지갑의 합도 맞지 않는다
	f.exec("UPDATE paid_lots SET remaining = remaining - 1 WHERE order_id = $1", paid.ID)

	report := f.run()

	for _, id := range f.lotIDs() {
		wantFlagged(t, report, reconcile.CheckPaidLotRemaining, id)
	}
	wantFlagged(t, report, reconcile.CheckPaidLotTotal, f.user.String())
	// 원장과 지갑은 서로 맞는다. 어긋난 것은 묶음뿐이다
	if slices.Contains(flagged(report, reconcile.CheckPaidBalance), f.user.String()) {
		t.Error("원장과 지갑이 맞는데 paid_balance 검사에 걸렸다")
	}
}

func TestAWalletThatDisagreesWithTheLedgerIsFound(t *testing.T) {
	f := setUp(t)
	f.buy()
	if err := f.services.Wallet.GrantFree(ctx(t), f.user, 30); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}
	// 원장에 적지 않고 잔액만 바꾼다. 코드가 틀렸거나 누가 DB 를 손으로 고친 것이다
	f.exec("UPDATE wallets SET paid_balance = paid_balance + 7 WHERE user_id = $1", f.user)
	f.exec("UPDATE free_grants SET remaining = remaining - 1 WHERE user_id = $1", f.user)

	report := f.run()

	wantFlagged(t, report, reconcile.CheckPaidBalance, f.user.String())
	for _, id := range f.grantIDs() {
		wantFlagged(t, report, reconcile.CheckGrantRemaining, id)
	}
	if report.Clean() {
		t.Error("어긋난 줄이 있는데 깨끗하다고 한다")
	}
}

func TestOrdersAndDepositsThatDoNotMatchAreFound(t *testing.T) {
	f := setUp(t)
	// 치렀다고 적혔는데 크레딧이 들어오지 않은 주문
	unpaid := uuid.New()
	f.exec(`INSERT INTO wallets (user_id, created_at, updated_at) VALUES ($1, $2, $2) ON CONFLICT DO NOTHING`, f.user, f.now())
	f.exec(`INSERT INTO orders (id, user_id, product_id, price, credits, status, idempotency_key, payment_key, paid_at,
			created_at, updated_at, expires_at)
		VALUES ($1, $2, 'credits-1000', 1000, 1000, 'paid', $3, $4, $5, $5, $5, $5::TIMESTAMPTZ + interval '1 day')`,
		unpaid, f.user, "key-"+uuid.NewString(), "pay_"+uuid.NewString(), f.now())
	// 크레딧이 들어왔는데 주문은 실패로 적힌 것
	refunded := f.buy()
	f.exec("UPDATE orders SET status = 'failed', failure_code = 'manual', paid_at = NULL WHERE id = $1", refunded.ID)
	var depositLine int64
	if err := f.pool.QueryRow(ctx(t), "SELECT id FROM ledger_entries WHERE order_id = $1", refunded.ID).Scan(&depositLine); err != nil {
		t.Fatalf("원장을 읽지 못했다: %v", err)
	}

	report := f.run()

	wantFlagged(t, report, reconcile.CheckPaidOrderDeposit, unpaid.String())
	// 그 주문의 묶음도 없다. 청약철회가 볼 것이 없다
	wantFlagged(t, report, reconcile.CheckPaidOrderLot, unpaid.String())
	wantFlagged(t, report, reconcile.CheckDepositOrder, strconv.FormatInt(depositLine, 10))
}

func TestAnOrderLotThatDoesNotMatchTheOrderIsFound(t *testing.T) {
	f := setUp(t)
	paid := f.buy()
	// 묶음의 양이 주문의 크레딧과 다르다. 남은 양은 그대로라 다른 검사에는 걸리지 않는다
	f.exec("UPDATE paid_lots SET amount = amount + 1 WHERE order_id = $1", paid.ID)

	report := f.run()

	wantFlagged(t, report, reconcile.CheckPaidOrderLot, paid.ID.String())
}

func TestAHoldWhoseLinesDoNotMatchItsStatusIsFound(t *testing.T) {
	f := setUp(t)
	if err := f.services.Wallet.Deposit(ctx(t), f.user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	// 돌려줬다고 적혔는데 크레딧이 돌아오지 않은 홀드
	notReturned := f.place()
	f.exec(`UPDATE holds SET status = 'released', release_reason = 'requested', settled_at = $2 WHERE id = $1`, notReturned.ID, f.now())
	// 크레딧을 빼지 않은 홀드
	notTaken := uuid.New()
	f.exec(`INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at, expires_at)
		VALUES ($1, $2, $3, $4, 'narration.standard', 50, 'held', $5, $5, $5::TIMESTAMPTZ + interval '1 day')`,
		notTaken, f.user, source, "table:"+uuid.NewString()+":round:9", f.now())

	report := f.run()

	wantFlagged(t, report, reconcile.CheckHoldLines, notReturned.ID.String())
	wantFlagged(t, report, reconcile.CheckHoldLines, notTaken.String())
}

func TestStaleConfirmingOrdersAreResolved(t *testing.T) {
	f := setUp(t)
	created, _, err := f.services.Orders.Create(ctx(t), f.user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	// 승인을 요청했지만 답을 받지 못했다. 결제 대행사에서는 승인되었다
	unsure, err := f.services.Orders.Confirm(ctx(t), f.user, created.ID, payment.FakeTimeoutApproved+uuid.NewString())
	if err != nil || unsure.Status != order.StatusConfirming {
		t.Fatalf("주문 = %+v, %v", unsure, err)
	}
	*f.elapsed = staleAfter

	report := f.run()

	if report.Stale.Found < 1 || report.Stale.Paid < 1 {
		t.Errorf("대사 = %+v", report.Stale)
	}
	got, err := f.services.Orders.Get(ctx(t), f.user, created.ID)
	if err != nil || got.Status != order.StatusPaid {
		t.Errorf("주문 = %+v, %v. paid 여야 한다", got, err)
	}
	wantNotFlagged(t, report, created.ID.String(), f.user.String())
}

func TestCreditsBackInARefundedLotAreFound(t *testing.T) {
	f := setUp(t)
	ctx := ctx(t)
	refunded := f.buy()
	if got, err := f.services.Orders.Refund(ctx, f.user, refunded.ID); err != nil || got.Status != order.StatusRefunded {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	var lot int64
	if err := f.pool.QueryRow(ctx, "SELECT id FROM paid_lots WHERE order_id = $1", refunded.ID).Scan(&lot); err != nil {
		t.Fatalf("묶음을 읽지 못했다: %v", err)
	}
	// 환불된 주문의 묶음에 크레딧이 다시 들어왔다. 원장과 묶음과 지갑은 서로 맞게 적었다. 맞지 않는 것은 "환불된 묶음은 비어 있다"뿐이다
	f.exec(`INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, lot_id, created_at)
		VALUES ($1, gen_random_uuid(), 'paid', 'regroup', 5, $2, $3)`, f.user, lot, f.now())
	f.exec("UPDATE paid_lots SET remaining = 5 WHERE id = $1", lot)
	f.exec("UPDATE wallets SET paid_balance = paid_balance + 5 WHERE user_id = $1", f.user)

	report := f.run()

	wantFlagged(t, report, reconcile.CheckLotRefund, strconv.FormatInt(lot, 10))
	wantNotFlagged(t, report, f.user.String())
}

func TestAMismatchedLotOfARefundedOrderIsFound(t *testing.T) {
	f := setUp(t)
	refunded := f.buy()
	if got, err := f.services.Orders.Refund(ctx(t), f.user, refunded.ID); err != nil || got.Status != order.StatusRefunded {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	// 환불된 주문도 그 주문의 묶음이 같은 양으로 있어야 한다
	f.exec("UPDATE paid_lots SET amount = amount + 1 WHERE order_id = $1", refunded.ID)

	report := f.run()

	wantFlagged(t, report, reconcile.CheckPaidOrderLot, refunded.ID.String())
}

func TestStaleRefundsAreResolved(t *testing.T) {
	f := setUp(t)
	// 취소는 되지만 첫 요청의 답을 받지 못한 주문을 흉내 낸다. 가짜는 기억이 없어서, 환불 중으로 두고 결제 번호를 바꾼다
	paid := f.buyWith(payment.FakeCancelLost)
	if got, err := f.services.Orders.Refund(ctx(t), f.user, paid.ID); err != nil || got.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v", got, err)
	}
	f.exec("UPDATE orders SET payment_key = $2 WHERE id = $1", paid.ID, payment.FakeApproved+uuid.NewString())
	*f.elapsed = staleAfter

	report := f.run()

	if report.Stale.Found < 1 || report.Stale.Refunded < 1 {
		t.Errorf("대사 = %+v", report.Stale)
	}
	got, err := f.services.Orders.Get(ctx(t), f.user, paid.ID)
	if err != nil || got.Status != order.StatusRefunded {
		t.Errorf("주문 = %+v, %v. refunded 여야 한다", got, err)
	}
	wantNotFlagged(t, report, paid.ID.String(), f.user.String())
	wantNotFlaggedIn(t, report, lotChecks, f.lotIDs()...)
}

func TestOrdersStillUnknownAfterADayAreForAPerson(t *testing.T) {
	f := setUp(t)
	// 결제 대행사도 결과를 모르는 승인, 답이 오지 않는 취소
	created, _, err := f.services.Orders.Create(ctx(t), f.user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	confirming, err := f.services.Orders.Confirm(ctx(t), f.user, created.ID, payment.FakeLost+uuid.NewString())
	if err != nil || confirming.Status != order.StatusConfirming {
		t.Fatalf("주문 = %+v, %v", confirming, err)
	}
	paid := f.buyWith(payment.FakeCancelLost)
	if refunding, err := f.services.Orders.Refund(ctx(t), f.user, paid.ID); err != nil || refunding.Status != order.StatusRefunding {
		t.Fatalf("주문 = %+v, %v", refunding, err)
	}

	*f.elapsed = order.StuckAfter - time.Minute
	early := f.run()
	*f.elapsed = order.StuckAfter
	late := f.run()

	if stuckIn(early, created.ID) || stuckIn(early, paid.ID) {
		t.Error("하루가 되기 전인데 사람이 볼 주문으로 셌다")
	}
	if !stuckIn(late, created.ID) || !stuckIn(late, paid.ID) || !late.NeedsPerson() {
		t.Errorf("하루가 지났는데 사람이 볼 주문으로 세지 않았다: %d 개", len(late.Stuck))
	}
	// 장부는 맞다. 결과를 모르는 것은 장부가 틀린 것이 아니다
	wantNotFlagged(t, late, f.user.String(), created.ID.String(), paid.ID.String())
	wantNotFlaggedIn(t, late, lotChecks, f.lotIDs()...)
}

func TestAnOrderTheReconcileFinishesIsNotForAPerson(t *testing.T) {
	f := setUp(t)
	// 하루 동안 아무도 묻지 않았다. 결제 대행사는 승인했다. 대사가 먼저 조회해 끝내므로 사람이 볼 주문이 아니다
	created, _, err := f.services.Orders.Create(ctx(t), f.user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	unsure, err := f.services.Orders.Confirm(ctx(t), f.user, created.ID, payment.FakeTimeoutApproved+uuid.NewString())
	if err != nil || unsure.Status != order.StatusConfirming {
		t.Fatalf("주문 = %+v, %v", unsure, err)
	}
	*f.elapsed = order.StuckAfter

	report := f.run()

	if stuckIn(report, created.ID) {
		t.Error("대사가 끝낸 주문을 사람이 볼 주문으로 셌다")
	}
	got, err := f.services.Orders.Get(ctx(t), f.user, created.ID)
	if err != nil || got.Status != order.StatusPaid {
		t.Errorf("주문 = %+v, %v. paid 여야 한다", got, err)
	}
}

// stuckIn 은 대사가 그 주문을 사람이 볼 주문으로 셌는지 본다.
func stuckIn(report reconcile.Report, id uuid.UUID) bool {
	for _, o := range report.Stuck {
		if o.ID == id {
			return true
		}
	}
	return false
}

func TestOverdueWorkIsCountedOnlyAfterTheGrace(t *testing.T) {
	f := setUp(t)
	if err := f.services.Wallet.Deposit(ctx(t), f.user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	// 다른 테스트가 남긴 홀드와 만료 시각이 겹치지 않게, 어중간한 때에 건다. 그 순간을 넘을 때 하나만 늘어야 한다
	placedAt := time.Hour + 7*time.Minute + 13*time.Second
	*f.elapsed = placedAt
	f.place()
	*f.elapsed = placedAt + rules.HoldTTL + staleAfter - time.Second
	before := f.run().Overdue
	*f.elapsed = placedAt + rules.HoldTTL + staleAfter

	after := f.run().Overdue

	// 만료된 지 얼마 안 된 것은 정리 작업이 곧 한다. 밀렸다고 하지 않는다
	if after.Holds != before.Holds+1 || !after.Any() {
		t.Errorf("밀린 홀드: 직전 %d, 지금 %d. 하나 늘어야 한다", before.Holds, after.Holds)
	}
}

// failingResolver 는 늘 실패하는 주문 대사다.
type failingResolver struct{}

func (failingResolver) ListStuck(context.Context, time.Duration, int) ([]order.Order, error) {
	return nil, nil
}

func (failingResolver) ResolveStale(context.Context, time.Duration, int) (order.StaleReport, error) {
	return order.StaleReport{}, errors.New("provider unreachable")
}

// stuckFailing 은 주문을 끝내는 것은 진짜로 하고, 사람이 볼 주문을 찾을 때만 실패한다.
type stuckFailing struct {
	reconcile.OrderResolver
}

func (stuckFailing) ListStuck(context.Context, time.Duration, int) ([]order.Order, error) {
	return nil, errors.New("결과를 모르는 주문을 읽지 못했다")
}

func TestChecksRunEvenWhenListingStuckOrdersFails(t *testing.T) {
	f := setUp(t)
	f.exec(`INSERT INTO wallets (user_id, paid_balance, created_at, updated_at) VALUES ($1, 5, $2, $2)`, f.user, f.now())

	report, err := reconcile.New(f.pool, stuckFailing{f.services.Orders}, f.reviews, f.now).Run(ctx(t), reconcile.Options{StaleAfter: staleAfter, Limit: everything})

	if err == nil {
		t.Error("사람이 볼 주문을 찾지 못한 것을 알려야 한다")
	}
	wantFlagged(t, report, reconcile.CheckPaidBalance, f.user.String())
}

func TestChecksRunEvenWhenResolvingFails(t *testing.T) {
	f := setUp(t)
	f.exec(`INSERT INTO wallets (user_id, paid_balance, created_at, updated_at) VALUES ($1, 5, $2, $2)`, f.user, f.now())

	report, err := reconcile.New(f.pool, failingResolver{}, f.reviews, f.now).Run(ctx(t), reconcile.Options{StaleAfter: staleAfter, Limit: everything})

	if err == nil {
		t.Error("주문을 끝내지 못한 것을 알려야 한다")
	}
	wantFlagged(t, report, reconcile.CheckPaidBalance, f.user.String())
}

// failingReviews 는 때가 된 할 일을 찾지 못한다.
type failingReviews struct{}

func (failingReviews) Due(context.Context) ([]pricereview.Due, error) {
	return nil, errors.New("할 일을 읽지 못했다")
}

func TestChecksRunEvenWhenListingReviewsFails(t *testing.T) {
	f := setUp(t)
	f.exec(`INSERT INTO wallets (user_id, paid_balance, created_at, updated_at) VALUES ($1, 5, $2, $2)`, f.user, f.now())

	report, err := reconcile.New(f.pool, f.services.Orders, failingReviews{}, f.now).Run(ctx(t), reconcile.Options{StaleAfter: staleAfter, Limit: everything})

	if err == nil {
		t.Error("할 일을 찾지 못한 것을 알려야 한다")
	}
	wantFlagged(t, report, reconcile.CheckPaidBalance, f.user.String())
}

// reviewDue 는 대사의 결과에 그 할 일이 있는지다.
func reviewDue(report reconcile.Report, id int64, step pricereview.Step) bool {
	return slices.ContainsFunc(report.Reviews, func(d pricereview.Due) bool { return d.ReviewID == id && d.Step == step })
}

func TestPriceReviewsThatAreDueAreForAPerson(t *testing.T) {
	f := setUp(t)
	added, err := f.reviews.Add(ctx(t), pricereview.Draft{Subject: "대사 테스트", ChangesAt: f.now().Add(20 * 24 * time.Hour), CreatedBy: "test"})
	if err != nil {
		t.Fatalf("할 일을 적지 못했다: %v", err)
	}

	report := f.run()

	if !reviewDue(report, added.ID, pricereview.StepAnnounce) || reviewDue(report, added.ID, pricereview.StepNotice) || !report.NeedsPerson() {
		t.Errorf("20일 전에는 첫 공지만 할 일이어야 한다: %+v", report.Reviews)
	}
	if _, err := f.reviews.Done(ctx(t), added.ID, pricereview.StepAnnounce, "test", ""); err != nil {
		t.Fatalf("끝냈다고 적지 못했다: %v", err)
	}
	if reviewDue(f.run(), added.ID, pricereview.StepAnnounce) {
		t.Error("끝낸 할 일이 다시 나왔다")
	}
}

func TestReconcileWritesNothingWhileChecking(t *testing.T) {
	// 검사는 읽기만 하는 트랜잭션에서 한다. 실수로 쓰는 문장이 끼어도 DB 가 막는다
	f := setUp(t)
	_, err := f.pool.Exec(ctx(t), "BEGIN READ ONLY; INSERT INTO wallets (user_id, created_at, updated_at) VALUES (gen_random_uuid(), now(), now()); COMMIT")
	if err == nil {
		t.Error("읽기만 하는 트랜잭션에서 쓰기가 되었다")
	}
}
