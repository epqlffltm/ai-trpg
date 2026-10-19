// billing-server/internal/app/app_test.go

package app_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/sweep"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

var now = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

func TestNewServicesFollowsTheRules(t *testing.T) {
	// 규칙마다 다른 값을 줘서, 값이 엉뚱한 서비스로 가면 드러나게 한다
	rules := config.Rules{SpendFreeFirst: false, FreeCreditTTL: 5 * time.Hour, HoldTTL: 2 * time.Hour, OrderTTL: 3 * time.Hour}
	services, err := app.NewServices(testenv.Pool(t), rules, app.NewProviders(config.Payment{Provider: config.ProviderFake}), func() time.Time { return now })
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	ctx := context.Background()
	user := uuid.New()
	if err := services.Wallet.Deposit(ctx, user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	grant, err := services.Wallet.GrantFreeOnce(ctx, user, 30, "app-test")
	if err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}

	placed, _, err := services.Holds.Place(ctx, "game-server", user, "table:"+uuid.NewString()+":round:1", pricing.NarrationStandard)
	if err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	created, _, err := services.Orders.Create(ctx, user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	balance, err := services.Wallet.Balance(ctx, user)
	if err != nil {
		t.Fatalf("잔액을 읽지 못했다: %v", err)
	}

	if !grant.ExpiresAt.Equal(now.Add(5 * time.Hour)) {
		t.Errorf("무료 크레딧의 기한 = %v", grant.ExpiresAt)
	}
	if !placed.ExpiresAt.Equal(now.Add(2 * time.Hour)) {
		t.Errorf("홀드의 만료 시각 = %v", placed.ExpiresAt)
	}
	if !created.ExpiresAt.Equal(now.Add(3 * time.Hour)) {
		t.Errorf("주문의 만료 시각 = %v", created.ExpiresAt)
	}
	// 산 크레딧부터 쓴다
	if balance.Paid != 50 || balance.Free != 30 {
		t.Errorf("잔액 = 산 것 %d, 무료 %d. 산 크레딧에서 빠져야 한다", balance.Paid, balance.Free)
	}
}

// fakeProviders 는 서버가 가짜를 고른 때와 같은 결제 대행사다.
var fakeProviders = app.NewProviders(config.Payment{Provider: config.ProviderFake})

func TestNewServicesRefusesAZeroTTL(t *testing.T) {
	pool := testenv.Pool(t)
	clock := func() time.Time { return now }
	if _, err := app.NewServices(pool, config.Rules{FreeCreditTTL: time.Hour, HoldTTL: 0, OrderTTL: time.Hour}, fakeProviders, clock); !errors.Is(err, hold.ErrInvalidTTL) {
		t.Errorf("홀드의 기한이 0: %v", err)
	}
	if _, err := app.NewServices(pool, config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: 0}, fakeProviders, clock); !errors.Is(err, order.ErrInvalidTTL) {
		t.Errorf("주문의 기한이 0: %v", err)
	}
}

func TestNewLoggerCarriesTheDeployment(t *testing.T) {
	var out bytes.Buffer
	logger := app.NewLogger(&out, config.Logging{AppEnvironment: "staging", AppVersion: "v1.2.3", LogLevel: "warning"})

	logger.Info("남지 않는다")
	logger.Warn("남는다")

	var line map[string]any
	if err := json.Unmarshal(out.Bytes(), &line); err != nil {
		t.Fatalf("한 줄의 JSON 이 아니다: %q", out.String())
	}
	if line["environment"] != "staging" || line["version"] != "v1.2.3" || line["service"] != "billing-server" || line["message"] != "남는다" {
		t.Errorf("줄 = %v", line)
	}
}

// approveAll 은 어떤 결제 번호든 승인하는 결제 대행사다. 가짜(Fake)는 모르는 앞머리를 거절하므로 둘이 구별된다.
type approveAll struct{}

func (approveAll) Confirm(context.Context, payment.Request) (payment.Result, error) {
	return payment.Result{Status: payment.StatusApproved}, nil
}

func (approveAll) Lookup(context.Context, payment.Request) (payment.Result, error) {
	return payment.Result{Status: payment.StatusApproved}, nil
}

func (approveAll) Cancel(context.Context, payment.Request) (payment.Result, error) {
	return payment.Result{Status: payment.StatusCanceled}, nil
}

func TestNewServicesUsesTheGivenProvider(t *testing.T) {
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(testenv.Pool(t), rules, order.Providers{order.ChannelWeb: approveAll{}}, func() time.Time { return now })
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	ctx := context.Background()
	user := uuid.New()
	created, _, err := services.Orders.Create(ctx, user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}

	// 가짜라면 거절했을 번호다. 넘겨준 결제 대행사가 승인했다
	confirmed, err := services.Orders.Confirm(ctx, user, created.ID, "any_key_"+strings.ReplaceAll(uuid.NewString(), "-", ""))

	if err != nil || confirmed.Status != order.StatusPaid {
		t.Errorf("주문 = %s, %v. 넘겨준 결제 대행사가 쓰이지 않았다", confirmed.Status, err)
	}
}

func TestNewServicesRefusesMissingWebProvider(t *testing.T) {
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	clock := func() time.Time { return now }
	for name, providers := range map[string]order.Providers{
		"없다":     nil,
		"웹이 nil": {order.ChannelWeb: nil},
	} {
		if _, err := app.NewServices(testenv.Pool(t), rules, providers, clock); !errors.Is(err, order.ErrNoWebProvider) {
			t.Errorf("%s: %v. ErrNoWebProvider 여야 한다", name, err)
		}
	}
}

func TestNewProvidersPutsTheConfiguredOneOnTheWeb(t *testing.T) {
	providers := app.NewProviders(config.Payment{Provider: config.ProviderFake})
	if len(providers) != 1 || providers[order.ChannelWeb] != (payment.Fake{}) {
		t.Errorf("길마다의 결제 대행사 = %v", providers)
	}
}

func TestNoProvidersPutsTheRefusingOneOnTheWeb(t *testing.T) {
	providers := app.NoProviders()
	if len(providers) != 1 || providers[order.ChannelWeb] != (payment.None{}) {
		t.Errorf("길마다의 결제 대행사 = %v", providers)
	}
}

func TestMeasuredProvidersAreCountedUnderTheConfiguredName(t *testing.T) {
	recorder := metricstest.New(t)
	providers, err := app.MeasureProviders(order.Providers{order.ChannelWeb: approveAll{}}, config.ProviderToss, recorder.Meter())
	if err != nil {
		t.Fatalf("결제 대행사를 감싸지 못했다: %v", err)
	}

	result, err := providers[order.ChannelWeb].Confirm(context.Background(), payment.Request{})

	if err != nil || result.Status != payment.StatusApproved {
		t.Fatalf("감싼 결제 대행사의 답 = %+v, %v", result, err)
	}
	labels := []attribute.KeyValue{
		attribute.String("provider", "toss"), attribute.String("operation", "confirm"), attribute.String("outcome", "approved"),
	}
	if got := recorder.Int64("payment_provider_calls", labels...); got != 1 {
		t.Errorf("부른 수 = %d. 1 이어야 한다", got)
	}
}

func TestMeasuringKeepsAnEmptyWebSeatEmpty(t *testing.T) {
	// 빈 자리를 감싸면 nil 이 아니게 되어 주문 서비스가 거절하지 못한다. 부르는 순간 패닉이다
	providers, err := app.MeasureProviders(order.Providers{order.ChannelWeb: nil}, config.ProviderFake, metricstest.New(t).Meter())
	if err != nil {
		t.Fatalf("결제 대행사를 감싸지 못했다: %v", err)
	}
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	if _, err := app.NewServices(testenv.Pool(t), rules, providers, func() time.Time { return now }); !errors.Is(err, order.ErrNoWebProvider) {
		t.Errorf("오류 = %v. ErrNoWebProvider 여야 한다", err)
	}
}

// countingProvider 는 불린 수를 세는 결제 대행사다. 불리면 payment.None 처럼 오류를 낸다.
type countingProvider struct {
	calls atomic.Int32
}

func (p *countingProvider) Confirm(ctx context.Context, request payment.Request) (payment.Result, error) {
	p.calls.Add(1)
	return payment.None{}.Confirm(ctx, request)
}

func (p *countingProvider) Cancel(ctx context.Context, request payment.Request) (payment.Result, error) {
	p.calls.Add(1)
	return payment.None{}.Cancel(ctx, request)
}

func (p *countingProvider) Lookup(ctx context.Context, request payment.Request) (payment.Result, error) {
	p.calls.Add(1)
	return payment.None{}.Lookup(ctx, request)
}

func TestASweepRoundNeverCallsTheProvider(t *testing.T) {
	// 정리 작업에 결제 대행사의 키를 주지 않는 까닭이다(cmd/sweeper 가 app.NoProviders 를 끼운다).
	// 셋 모두(홀드, 무료 크레딧, 주문)를 실제로 정리하게 해서, 어느 길에서도 부르지 않는지 본다
	pool := testenv.Pool(t)
	testenv.ExclusiveSweep(t, pool)
	current := testenv.SweepEnd
	clock := func() time.Time { return current }
	provider := &countingProvider{}
	rules := config.Rules{SpendFreeFirst: false, FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, order.Providers{order.ChannelWeb: provider}, clock)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	sweeper := sweep.New(services.Holds, services.Wallet, services.Orders, 100_000)
	ctx := context.Background()
	// 앞서 돈 정리 작업의 테스트가 그 시대에 남긴 것을 치운다. 그다음 시계를 시대의 처음으로 돌린다
	if _, err := sweeper.Round(ctx); err != nil {
		t.Fatalf("남은 것을 치우지 못했다: %v", err)
	}
	current = testenv.SweepEra

	user := uuid.New()
	if err := services.Wallet.Deposit(ctx, user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	// 무료 크레딧은 다른 사용자에게 준다. 같은 사용자면 홀드를 돌려줄 때 지갑을 잠그며 함께 정리되어 무료 크레딧의 길을 지나지 않는다
	if _, err := services.Wallet.GrantFreeOnce(ctx, uuid.New(), 30, "sweep-test"); err != nil {
		t.Fatalf("무료 크레딧을 주지 못했다: %v", err)
	}
	if _, _, err := services.Holds.Place(ctx, "game-server", user, "table:"+uuid.NewString()+":round:1", pricing.NarrationStandard); err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	created, _, err := services.Orders.Create(ctx, user, "credits-1000", "key-"+uuid.NewString())
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	current = testenv.SweepEra.Add(2 * time.Hour)

	result, err := sweeper.Round(ctx)

	if err != nil || result.Holds < 1 || result.FreeCreditUsers < 1 || result.Orders < 1 {
		t.Fatalf("정리 = %+v, %v. 셋 모두 정리해야 한다", result, err)
	}
	if expired, err := services.Orders.Get(ctx, user, created.ID); err != nil || expired.Status != order.StatusExpired {
		t.Errorf("주문 = %s, %v. 만료되어야 한다", expired.Status, err)
	}
	if calls := provider.calls.Load(); calls != 0 {
		t.Errorf("결제 대행사를 %d번 불렀다. 정리 작업은 부르지 않아야 한다", calls)
	}
}

func TestNewProviderPicksTheConfiguredOne(t *testing.T) {
	if got := app.NewProvider(config.Payment{Provider: config.ProviderFake}); got != (payment.Fake{}) {
		t.Errorf("fake: %T", got)
	}
	got := app.NewProvider(config.Payment{Provider: config.ProviderToss, TossSecretKey: "test_gsk_x", TossClientKey: "test_gck_x"})
	toss, ok := got.(*payment.Toss)
	if !ok {
		t.Fatalf("toss: %T", got)
	}
	// 토스페이먼츠의 실제 주소를 부른다(테스트 키라 테스트 모드다)
	if !strings.Contains(toss.String(), payment.TossAPIURL) {
		t.Errorf("toss: %s", toss)
	}
}
