// billing-server/internal/receiptnotice/store_test.go

package receiptnotice_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/receiptnotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// clock 은 테스트가 옮기는 시계다.
type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

// recorder 는 받은 것을 적는 가짜 인증 서버다. err 가 있으면 받지 않는다.
type recorder struct {
	err  error
	sent []receiptnotice.Notice
}

func (r *recorder) Send(_ context.Context, notice receiptnotice.Notice) error {
	if r.err != nil {
		return r.err
	}
	r.sent = append(r.sent, notice)
	return nil
}

// of 는 받은 것 가운데 그 주문의 것만 고른다. 같은 스키마에 다른 테스트의 줄이 있을 수 있다.
func (r *recorder) of(orderID uuid.UUID) []receiptnotice.Notice {
	var mine []receiptnotice.Notice
	for _, notice := range r.sent {
		if notice.OrderID == orderID {
			mine = append(mine, notice)
		}
	}
	return mine
}

type fixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	clock    *clock
	services app.Services
	sender   *recorder
	notices  *receiptnotice.Service
}

// setUp 은 테스트용 스키마에 붙는 서비스들을 만든다. 지금은 2026-03-02 09:00 UTC(한국 18시)다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	c := &clock{now: time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)}
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NewProviders(config.Payment{Provider: config.ProviderFake}), c.Now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	sender := &recorder{}
	return fixture{t: t, pool: pool, clock: c, services: services, sender: sender,
		notices: receiptnotice.NewService(pool, c.Now, sender)}
}

// user 는 결제할 수 있는 사용자를 만든다. adultFrom 이 nil 이면 이미 성년이다.
func (f fixture) user(adultFrom *time.Time) uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	update := eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: adultFrom, GuardianConsent: adultFrom != nil}
	if _, err := f.services.Eligibility.Apply(context.Background(), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return user
}

// paid 는 사용자의 주문을 만들고 치른다.
func (f fixture) paid(user uuid.UUID) uuid.UUID {
	f.t.Helper()
	ctx := context.Background()
	created, _, err := f.services.Orders.Create(ctx, user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		f.t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	if _, err := f.services.Orders.Confirm(ctx, user, created.ID, payment.FakeApproved+strings.ReplaceAll(uuid.NewString(), "-", "")); err != nil {
		f.t.Fatalf("주문을 치르지 못했다: %v", err)
	}
	return created.ID
}

func (f fixture) round() receiptnotice.Result {
	f.t.Helper()
	result, err := f.notices.Round(context.Background(), 1000)
	if err != nil {
		f.t.Fatalf("한 바퀴를 돌지 못했다: %v", err)
	}
	return result
}

// status 는 그 주문의 그 종류의 줄의 상태와 시도 횟수다. 없으면 빈 글자다.
func (f fixture) status(orderID uuid.UUID, kind receiptnotice.Kind) (string, int) {
	f.t.Helper()
	var status string
	var attempts int
	err := f.pool.QueryRow(context.Background(),
		"SELECT status, attempts FROM receipt_notices WHERE order_id = $1 AND kind = $2", orderID, string(kind)).Scan(&status, &attempts)
	if err != nil {
		return "", 0
	}
	return status, attempts
}

func TestAPaymentIsSentOnceToTheBuyer(t *testing.T) {
	f := setUp(t)
	user := f.user(nil)
	orderID := f.paid(user)

	f.round()
	f.round()

	got := f.sender.of(orderID)
	if len(got) != 1 {
		t.Fatalf("보낸 것 = %+v. 한 번이어야 한다", got)
	}
	notice := got[0]
	if notice.Kind != receiptnotice.KindPaid || notice.UserID != user || notice.ProductID != "credits-1000" ||
		notice.Price != 1000 || notice.Credits != 1000 || !notice.OccurredAt.Equal(f.clock.now) || !notice.PaidAt.Equal(f.clock.now) {
		t.Errorf("알린 것 = %+v", notice)
	}
	if !notice.RefundableUntil().Equal(f.clock.now.Add(order.RefundWindow)) {
		t.Errorf("청약철회 기한 = %v", notice.RefundableUntil())
	}
	if status, _ := f.status(orderID, receiptnotice.KindPaid); status != "sent" {
		t.Errorf("상태 = %q", status)
	}
}

func TestAMinorsPaymentIsSentToTheMinorToo(t *testing.T) {
	// 보호자에게 가는 알림(guardiannotice)과 따로, 결제한 본인에게도 간다
	f := setUp(t)
	adultFrom := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	orderID := f.paid(f.user(&adultFrom))

	f.round()

	if len(f.sender.of(orderID)) != 1 {
		t.Errorf("미성년자 본인에게 알리지 않았다")
	}
}

func TestARefundIsSentWithThePaymentTime(t *testing.T) {
	f := setUp(t)
	user := f.user(nil)
	orderID := f.paid(user)
	paidAt := f.clock.now
	f.round()

	f.clock.now = f.clock.now.Add(time.Hour)
	if _, err := f.services.Orders.Refund(context.Background(), user, orderID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}
	f.round()

	got := f.sender.of(orderID)
	if len(got) != 2 || got[1].Kind != receiptnotice.KindRefunded {
		t.Fatalf("보낸 것 = %+v. 결제와 철회여야 한다", got)
	}
	if !got[1].PaidAt.Equal(paidAt) || !got[1].OccurredAt.Equal(f.clock.now) {
		t.Errorf("철회의 시각 = %+v", got[1])
	}
}

func TestAFailedSendIsTriedAgainLater(t *testing.T) {
	f := setUp(t)
	orderID := f.paid(f.user(nil))
	f.sender.err = errors.New("인증 서버가 503 로 답했다")

	failed := f.round()
	status, attempts := f.status(orderID, receiptnotice.KindPaid)
	f.sender.err = nil
	early := len(f.sender.of(orderID))
	f.round()
	stillWaiting := len(f.sender.of(orderID))
	f.clock.now = f.clock.now.Add(5 * time.Second)
	f.round()

	if failed.Retried < 1 || status != "pending" || attempts != 1 {
		t.Errorf("실패한 바퀴 = %+v, 상태 = %q, 시도 = %d", failed, status, attempts)
	}
	if early != 0 || stillWaiting != 0 || len(f.sender.of(orderID)) != 1 {
		t.Errorf("5초를 기다리지 않았거나 끝내 보내지 않았다: %d %d %d", early, stillWaiting, len(f.sender.of(orderID)))
	}
}

func TestWithoutASenderReceiptsWaitToBeSent(t *testing.T) {
	// 인증 서버의 비밀이 없는 동안에도 적어 둔다. 설정하면 나간다
	f := setUp(t)
	orderID := f.paid(f.user(nil))

	queueOnly := receiptnotice.NewService(f.pool, f.clock.Now, nil)
	result, err := queueOnly.Round(context.Background(), 1000)
	status, _ := f.status(orderID, receiptnotice.KindPaid)
	f.round()

	if err != nil || result.Queued < 1 || result.Sent != 0 || status != "pending" {
		t.Errorf("결과 = %+v, %v, 상태 = %q", result, err, status)
	}
	if len(f.sender.of(orderID)) != 1 {
		t.Errorf("설정한 뒤에 나가지 않았다")
	}
}

func TestOldPaymentsAreNotLookedAt(t *testing.T) {
	// 정리 작업이 거슬러 보는 기간(30일)이 지난 결제는 적지 않는다
	f := setUp(t)
	orderID := f.paid(f.user(nil))

	f.clock.now = f.clock.now.Add(receiptnotice.LookBack + time.Second)
	f.round()

	if status, _ := f.status(orderID, receiptnotice.KindPaid); status != "" {
		t.Errorf("오래된 결제를 적었다: %q", status)
	}
}

func TestASkippedReceiptIsNeverSent(t *testing.T) {
	// 표가 생기기 전의 결제는 마이그레이션이 skipped 로 적어 둔다. 정리 작업은 그것을 다시 적거나 보내지 않는다
	f := setUp(t)
	orderID := f.paid(f.user(nil))
	_, err := f.pool.Exec(context.Background(), `
		INSERT INTO receipt_notices (order_id, kind, user_id, product_id, price, credits, paid_at, occurred_at, status, next_attempt_at, created_at)
		SELECT id, 'paid', user_id, product_id, price, credits, paid_at, paid_at, 'skipped', $2, $2 FROM orders WHERE id = $1`,
		orderID, f.clock.now)
	if err != nil {
		t.Fatalf("건너뛸 줄을 적지 못했다: %v", err)
	}

	f.round()

	status, _ := f.status(orderID, receiptnotice.KindPaid)
	if status != "skipped" || len(f.sender.of(orderID)) != 0 {
		t.Errorf("상태 = %q, 보낸 것 = %d", status, len(f.sender.of(orderID)))
	}
}
