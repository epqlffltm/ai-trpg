// billing-server/internal/usernotice/store_test.go

package usernotice_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
)

// clock 은 테스트가 옮기는 시계다.
type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

// recorder 는 받은 것을 적는 가짜 알림 서버다. answers 의 결과를 차례로 낸다. 다 쓰면 받았다고 답한다.
type recorder struct {
	answers []usernotice.Sent
	sent    []usernotice.Notice
}

func (r *recorder) Send(_ context.Context, notice usernotice.Notice) usernotice.Sent {
	r.sent = append(r.sent, notice)
	if len(r.answers) == 0 {
		return usernotice.Sent{Delivery: usernotice.Delivered}
	}
	answer := r.answers[0]
	r.answers = r.answers[1:]
	return answer
}

// of 는 받은 것 가운데 그 사람의 것만 고른다. 같은 스키마에 다른 테스트의 줄이 있을 수 있다.
func (r *recorder) of(user uuid.UUID) []usernotice.Notice {
	var mine []usernotice.Notice
	for _, notice := range r.sent {
		if notice.UserID == user {
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
	notices  *usernotice.Service
}

// setUp 은 테스트용 스키마에 붙는 서비스들을 만든다. 지금은 2026-04-06 09:00 UTC(한국 18시)다.
// 무료 크레딧은 3일 뒤에 사라진다. 그래서 받자마자 "7일 안에 사라질 크레딧"이 된다.
func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	c := &clock{now: time.Date(2026, 4, 6, 9, 0, 0, 0, time.UTC)}
	rules := config.Rules{FreeCreditTTL: 3 * 24 * time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NewProviders(config.Payment{Provider: config.ProviderFake}), c.Now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	sender := &recorder{}
	return fixture{t: t, pool: pool, clock: c, services: services, sender: sender,
		notices: usernotice.NewService(pool, c.Now, sender)}
}

// user 는 결제할 수 있는(성년인) 사용자를 만든다.
func (f fixture) user() uuid.UUID {
	f.t.Helper()
	user := uuid.New()
	if _, err := f.services.Eligibility.Apply(context.Background(), eligibility.Update{UserID: user, Version: 1}); err != nil {
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

// grant 는 사용자에게 무료 크레딧을 준다. key 가 있으면 그 이름으로 한 번만 준다.
func (f fixture) grant(user uuid.UUID, amount int64, key string) {
	f.t.Helper()
	ctx := context.Background()
	var err error
	if key == "" {
		err = f.services.Wallet.GrantFree(ctx, user, credit.Amount(amount))
	} else {
		_, err = f.services.Wallet.GrantFreeOnce(ctx, user, credit.Amount(amount), key)
	}
	if err != nil {
		f.t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}
}

func (f fixture) round() usernotice.Result {
	f.t.Helper()
	result, err := f.notices.Round(context.Background(), 1000)
	if err != nil {
		f.t.Fatalf("한 바퀴를 돌지 못했다: %v", err)
	}
	return result
}

// rows 는 그 사람의 줄들의 종류와 상태다. 적은 차례다.
func (f fixture) rows(user uuid.UUID) []string {
	f.t.Helper()
	rows, err := f.pool.Query(context.Background(), "SELECT kind, status FROM user_notices WHERE user_id = $1 ORDER BY id", user)
	if err != nil {
		f.t.Fatalf("줄을 읽지 못했다: %v", err)
	}
	defer rows.Close()
	var found []string
	for rows.Next() {
		var kind, status string
		if err := rows.Scan(&kind, &status); err != nil {
			f.t.Fatalf("줄을 읽지 못했다: %v", err)
		}
		found = append(found, kind+"/"+status)
	}
	return found
}

// payload 는 알림의 내용을 읽는다.
func payload(t *testing.T, notice usernotice.Notice) map[string]any {
	t.Helper()
	var values map[string]any
	if err := json.Unmarshal(notice.Payload, &values); err != nil {
		t.Fatalf("내용을 읽지 못했다: %v", err)
	}
	return values
}

func TestAPaymentIsToldOnce(t *testing.T) {
	f := setUp(t)
	user := f.user()
	orderID := f.paid(user)

	f.round()
	f.round()

	got := f.sender.of(user)
	if len(got) != 1 || got[0].Kind != usernotice.KindOrderPaid || got[0].Key != "order.paid:"+orderID.String() {
		t.Fatalf("보낸 것 = %+v", got)
	}
	want := map[string]any{"order_id": orderID.String(), "product_id": "credits-1000", "price": float64(1000), "credits": "1000"}
	for name, value := range want {
		if payload(t, got[0])[name] != value {
			t.Errorf("%s = %v, 기대 = %v", name, payload(t, got[0])[name], value)
		}
	}
	if rows := f.rows(user); len(rows) != 1 || rows[0] != "order.paid/sent" {
		t.Errorf("줄 = %v", rows)
	}
}

func TestARefundIsToldToo(t *testing.T) {
	f := setUp(t)
	user := f.user()
	orderID := f.paid(user)
	f.round()

	if _, err := f.services.Orders.Refund(context.Background(), user, orderID); err != nil {
		t.Fatalf("청약철회를 하지 못했다: %v", err)
	}
	f.round()

	got := f.sender.of(user)
	if len(got) != 2 || got[1].Kind != usernotice.KindOrderRefunded || got[1].Key != "order.refunded:"+orderID.String() {
		t.Errorf("보낸 것 = %+v", got)
	}
}

func TestWelcomeCreditsAreTold(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.grant(user, 300, "welcome")

	f.round()

	var welcome []usernotice.Notice
	for _, notice := range f.sender.of(user) {
		if notice.Kind == usernotice.KindWelcomeCredits {
			welcome = append(welcome, notice)
		}
	}
	// 환영 크레딧도 3일 뒤에 사라지므로 사라질 크레딧의 알림이 함께 간다
	if len(welcome) != 1 || payload(t, welcome[0])["amount"] != "300" ||
		payload(t, welcome[0])["expires_at"] != "2026-04-09T09:00:00Z" {
		t.Errorf("환영 크레딧의 알림 = %+v", welcome)
	}
}

func TestOtherKeyedGrantsAreNotWelcomeCredits(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.grant(user, 50, "attendance-20260406")

	f.round()

	// 출석의 실버는 환영 크레딧이 아니다. 곧 사라질 크레딧으로만 알린다
	if rows := f.rows(user); len(rows) != 1 || rows[0] != "credit.expiring/sent" {
		t.Errorf("줄 = %v", rows)
	}
}

func TestExpiringCreditsAreToldOnceAWeek(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.grant(user, 100, "")
	f.clock.now = f.clock.now.Add(time.Hour)
	f.grant(user, 40, "")

	f.round()
	// 다음 날 또 받아도 7일 안에는 다시 알리지 않는다
	f.clock.now = f.clock.now.Add(24 * time.Hour)
	f.grant(user, 10, "")
	f.round()

	got := f.sender.of(user)
	if len(got) != 1 || got[0].Kind != usernotice.KindCreditsExpiring {
		t.Fatalf("보낸 것 = %+v", got)
	}
	// 남은 것을 모두 더하고, 가장 먼저 사라지는 시각을 싣는다
	if payload(t, got[0])["amount"] != "140" || payload(t, got[0])["first_expires_at"] != "2026-04-09T09:00:00Z" {
		t.Errorf("내용 = %s", got[0].Payload)
	}

	// 7일이 지나 다시 남아 있으면 다시 알린다
	f.clock.now = f.clock.now.Add(7 * 24 * time.Hour)
	f.grant(user, 20, "")
	f.round()
	if got := f.sender.of(user); len(got) != 2 || payload(t, got[1])["amount"] != "20" {
		t.Errorf("다시 알린 것 = %+v", got)
	}
}

func TestCreditsFarFromExpiryAreNotTold(t *testing.T) {
	f := setUp(t)
	f.services, _ = app.NewServices(f.pool, config.Rules{FreeCreditTTL: 30 * 24 * time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour},
		app.NewProviders(config.Payment{Provider: config.ProviderFake}), f.clock.Now)
	user := f.user()
	f.grant(user, 100, "")

	f.round()

	if rows := f.rows(user); len(rows) != 0 {
		t.Errorf("줄 = %v", rows)
	}
}

func TestAnUnavailableServerIsTriedAgainLater(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)
	f.sender.answers = []usernotice.Sent{{Delivery: usernotice.Unavailable, Reason: "status_503"}}

	first := f.round()
	f.clock.now = f.clock.now.Add(4 * time.Second)
	f.round()
	early := len(f.sender.of(user))
	f.clock.now = f.clock.now.Add(time.Second)
	f.round()

	// 처음 실패한 뒤 5초를 기다린다. 4초 뒤에는 보내지 않는다
	if first.Retried < 1 || early != 1 || len(f.sender.of(user)) != 2 {
		t.Errorf("첫 바퀴 = %+v, 4초 뒤까지 보낸 것 = %d, 5초 뒤까지 = %d", first, early, len(f.sender.of(user)))
	}
	if rows := f.rows(user); len(rows) != 1 || rows[0] != "order.paid/sent" {
		t.Errorf("줄 = %v", rows)
	}
}

func TestARejectedNoticeIsFailedAndNotSentAgain(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)
	f.sender.answers = []usernotice.Sent{{Delivery: usernotice.Rejected, Reason: "status_409"}}

	result := f.round()
	f.clock.now = f.clock.now.Add(2 * time.Hour)
	f.round()

	if result.Rejected < 1 || len(f.sender.of(user)) != 1 {
		t.Errorf("결과 = %+v, 보낸 것 = %d", result, len(f.sender.of(user)))
	}
	var lastError string
	_ = f.pool.QueryRow(context.Background(), "SELECT last_error FROM user_notices WHERE user_id = $1", user).Scan(&lastError)
	if rows := f.rows(user); len(rows) != 1 || rows[0] != "order.paid/failed" || lastError != "status_409" {
		t.Errorf("줄 = %v, 마지막 오류 = %q", rows, lastError)
	}
}

func TestWithoutASenderNoticesWaitAndThenExpireAndAreDeleted(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)
	silent := usernotice.NewService(f.pool, f.clock.Now, nil)

	queued, err := silent.Round(context.Background(), 1000)
	if err != nil || queued.Sent != 0 || f.rows(user)[0] != "order.paid/pending" {
		t.Fatalf("결과 = %+v, %v, 줄 = %v", queued, err, f.rows(user))
	}
	// 7일 넘게 보내지 못한 것은 보내지 않는다. 그 사이에 결제는 사흘의 거슬러 보기를 벗어나 다시 적히지 않는다
	f.clock.now = f.clock.now.Add(7*24*time.Hour + time.Minute)
	if _, err := silent.Round(context.Background(), 1000); err != nil || f.rows(user)[0] != "order.paid/expired" {
		t.Fatalf("7일 뒤의 줄 = %v, %v", f.rows(user), err)
	}
	// 30일이 지나면 지운다
	f.clock.now = f.clock.now.Add(23 * 24 * time.Hour)
	if _, err := silent.Round(context.Background(), 1000); err != nil || len(f.rows(user)) != 0 {
		t.Errorf("30일 뒤의 줄 = %v, %v", f.rows(user), err)
	}
}

func TestAnOldPaymentIsNotTold(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)

	// 정리 작업이 사흘 넘게 멈춰 있었다. 그보다 지난 결제는 늦어서 알리지 않는다
	f.clock.now = f.clock.now.Add(usernotice.LookBack + time.Minute)
	f.round()

	if rows := f.rows(user); len(rows) != 0 {
		t.Errorf("줄 = %v", rows)
	}
}

func TestAnUnsentNoticeLeavesOneLineWithoutThePerson(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)
	var logs bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&logs, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })
	f.sender.answers = []usernotice.Sent{{Delivery: usernotice.Rejected, Reason: "status_422"}}

	f.round()

	var line map[string]any
	for _, raw := range strings.Split(strings.TrimSpace(logs.String()), "\n") {
		var candidate map[string]any
		if json.Unmarshal([]byte(raw), &candidate) == nil && candidate["error_code"] == usernotice.ErrorCodeRejected {
			line = candidate
		}
	}
	if line == nil || line["level"] != "ERROR" || line["operation"] != usernotice.SendOperation || line["reason"] != "status_422" {
		t.Fatalf("로그 = %s", logs.String())
	}
	// 받는 사람과 알림의 내용은 남기지 않는다
	if strings.Contains(logs.String(), user.String()) || strings.Contains(logs.String(), "credits-1000") {
		t.Errorf("로그에 사람이나 내용이 있다: %s", logs.String())
	}
}

func TestARefusedSignatureIsLoggedAsAnError(t *testing.T) {
	f := setUp(t)
	user := f.user()
	f.paid(user)
	var logs bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&logs, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })
	f.sender.answers = []usernotice.Sent{
		{Delivery: usernotice.Unavailable, Reason: "unauthorized"},
		{Delivery: usernotice.Unavailable, Reason: "status_503"},
	}

	f.round()

	// 서명이 거절된 것은 설정을 고쳐야 낫는다. 사람이 보도록 error 다. 그 밖의 다시 보낼 일은 warning 이다
	levels := map[string]string{}
	for _, raw := range strings.Split(strings.TrimSpace(logs.String()), "\n") {
		var line map[string]any
		if json.Unmarshal([]byte(raw), &line) == nil && line["error_code"] == usernotice.ErrorCodeUnavailable {
			levels[line["reason"].(string)] = line["level"].(string)
		}
	}
	if levels["unauthorized"] != "ERROR" {
		t.Errorf("로그 = %s", logs.String())
	}
	if level, ok := levels["status_503"]; ok && level != "WARN" {
		t.Errorf("503 의 수준 = %s", level)
	}
}
