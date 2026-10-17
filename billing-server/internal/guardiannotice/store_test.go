// billing-server/internal/guardiannotice/store_test.go

package guardiannotice_test

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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/guardiannotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// clock 은 테스트가 옮기는 시계다.
type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

// recorder 는 받은 것을 적는 가짜 인증 서버다. err 가 있으면 받지 않는다.
type recorder struct {
	err  error
	sent []guardiannotice.Notice
}

func (r *recorder) Send(_ context.Context, notice guardiannotice.Notice) error {
	if r.err != nil {
		return r.err
	}
	r.sent = append(r.sent, notice)
	return nil
}

// of 는 받은 것 가운데 그 주문의 것만 고른다. 같은 스키마에 다른 테스트의 줄이 있을 수 있다.
func (r *recorder) of(orderID uuid.UUID) []guardiannotice.Notice {
	var mine []guardiannotice.Notice
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
	notices  *guardiannotice.Service
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
		notices: guardiannotice.NewService(pool, c.Now, sender)}
}

// user 는 성년이 되는 날이 adultFrom 인 사용자를 만든다. nil 이면 이미 성년이다.
func (f fixture) user(adultFrom *time.Time) uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	update := eligibility.Update{UserID: user, Version: 1, LegalAdultFrom: adultFrom, GuardianConsent: adultFrom != nil}
	if _, err := f.services.Eligibility.Apply(context.Background(), update); err != nil {
		f.t.Fatalf("결제 자격을 적지 못했다: %v", err)
	}
	return user
}

func (f fixture) minor() uuid.UUID {
	adultFrom := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	return f.user(&adultFrom)
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

func (f fixture) round() guardiannotice.Result {
	f.t.Helper()
	result, err := f.notices.Round(context.Background(), 1000)
	if err != nil {
		f.t.Fatalf("한 바퀴를 돌지 못했다: %v", err)
	}
	return result
}

// status 는 그 주문의 그 종류의 줄의 상태와 시도 횟수다. 없으면 빈 글자다.
func (f fixture) status(orderID uuid.UUID, kind guardiannotice.Kind) (string, int) {
	f.t.Helper()
	var status string
	var attempts int
	err := f.pool.QueryRow(context.Background(),
		"SELECT status, attempts FROM guardian_notices WHERE order_id = $1 AND kind = $2", orderID, string(kind)).Scan(&status, &attempts)
	if err != nil {
		return "", 0
	}
	return status, attempts
}

func TestAMinorsPaymentIsSentOnce(t *testing.T) {
	f := setUp(t)
	user := f.minor()
	orderID := f.paid(user)

	f.round()
	f.round()

	got := f.sender.of(orderID)
	if len(got) != 1 {
		t.Fatalf("보낸 것 = %+v. 한 번이어야 한다", got)
	}
	notice := got[0]
	if notice.Kind != guardiannotice.KindPaid || notice.UserID != user || notice.ProductID != "credits-1000" ||
		notice.Price != 1000 || notice.Credits != 1000 || !notice.OccurredAt.Equal(f.clock.now) {
		t.Errorf("알린 것 = %+v", notice)
	}
	if status, _ := f.status(orderID, guardiannotice.KindPaid); status != "sent" {
		t.Errorf("상태 = %q", status)
	}
}

func TestAnAdultsPaymentIsNotSent(t *testing.T) {
	f := setUp(t)
	orderID := f.paid(f.user(nil))

	f.round()

	if len(f.sender.of(orderID)) != 0 {
		t.Errorf("성년의 결제를 알렸다")
	}
}

func TestAPaymentOnTheDayOfAdulthoodIsNotSent(t *testing.T) {
	// 지금은 한국 날짜로 3월 2일이다. 그날 성년이 되었다
	f := setUp(t)
	today := time.Date(2026, 3, 2, 0, 0, 0, 0, time.UTC)
	orderID := f.paid(f.user(&today))

	f.round()

	if len(f.sender.of(orderID)) != 0 {
		t.Errorf("성년이 된 날의 결제를 알렸다")
	}
}

func TestAPaymentTheDayBeforeAdulthoodIsSent(t *testing.T) {
	// 한국 날짜로 내일 성년이 된다. 오늘의 결제는 미성년자의 것이다
	f := setUp(t)
	tomorrow := time.Date(2026, 3, 3, 0, 0, 0, 0, time.UTC)
	orderID := f.paid(f.user(&tomorrow))

	f.round()

	if len(f.sender.of(orderID)) != 1 {
		t.Errorf("미성년자의 마지막 날의 결제를 알리지 않았다")
	}
}

func TestTheDayOfPaymentIsTheKoreanDay(t *testing.T) {
	// UTC 3월 2일 15시 30분은 한국 3월 3일 0시 30분이다. 3월 3일에 성년이 되었으니 알리지 않는다.
	// UTC 날짜로 자르면 3월 2일이라 미성년자의 결제로 잘못 본다
	f := setUp(t)
	f.clock.now = time.Date(2026, 3, 2, 15, 30, 0, 0, time.UTC)
	adultDay := time.Date(2026, 3, 3, 0, 0, 0, 0, time.UTC)
	orderID := f.paid(f.user(&adultDay))

	f.round()

	if len(f.sender.of(orderID)) != 0 {
		t.Errorf("한국 날짜로 성년이 된 날의 결제를 알렸다")
	}
}

func TestARefundIsSentToo(t *testing.T) {
	f := setUp(t)
	user := f.minor()
	orderID := f.paid(user)
	f.round()

	if _, err := f.services.Orders.Refund(context.Background(), user, orderID); err != nil {
		t.Fatalf("청약철회하지 못했다: %v", err)
	}
	f.round()

	got := f.sender.of(orderID)
	if len(got) != 2 || got[1].Kind != guardiannotice.KindRefunded {
		t.Errorf("보낸 것 = %+v. 결제와 철회여야 한다", got)
	}
}

func TestAFailedSendIsTriedAgainLater(t *testing.T) {
	f := setUp(t)
	orderID := f.paid(f.minor())
	f.sender.err = errors.New("인증 서버가 503 로 답했다")

	failed := f.round()
	status, attempts := f.status(orderID, guardiannotice.KindPaid)
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

func TestWithoutASenderNoticesWaitToBeSent(t *testing.T) {
	// 인증 서버의 비밀이 없는 동안에도 적어 둔다. 설정하면 나간다
	f := setUp(t)
	orderID := f.paid(f.minor())

	queueOnly := guardiannotice.NewService(f.pool, f.clock.Now, nil)
	result, err := queueOnly.Round(context.Background(), 1000)
	status, _ := f.status(orderID, guardiannotice.KindPaid)
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
	orderID := f.paid(f.minor())

	f.clock.now = f.clock.now.Add(guardiannotice.LookBack + time.Second)
	f.round()

	if status, _ := f.status(orderID, guardiannotice.KindPaid); status != "" {
		t.Errorf("오래된 결제를 적었다: %q", status)
	}
}
