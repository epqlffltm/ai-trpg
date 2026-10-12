// billing-server/internal/app/app_test.go

package app_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

var now = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

func TestNewServicesFollowsTheRules(t *testing.T) {
	// 규칙마다 다른 값을 줘서, 값이 엉뚱한 서비스로 가면 드러나게 한다
	rules := config.Rules{SpendFreeFirst: false, FreeCreditTTL: 5 * time.Hour, HoldTTL: 2 * time.Hour, OrderTTL: 3 * time.Hour}
	services, err := app.NewServices(testenv.Pool(t), rules, payment.Fake{}, func() time.Time { return now })
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
	if balance != (wallet.Balance{Paid: 50, Free: 30}) {
		t.Errorf("잔액 = %+v. 산 크레딧에서 빠져야 한다", balance)
	}
}

func TestNewServicesRefusesAZeroTTL(t *testing.T) {
	pool := testenv.Pool(t)
	clock := func() time.Time { return now }
	if _, err := app.NewServices(pool, config.Rules{FreeCreditTTL: time.Hour, HoldTTL: 0, OrderTTL: time.Hour}, payment.Fake{}, clock); !errors.Is(err, hold.ErrInvalidTTL) {
		t.Errorf("홀드의 기한이 0: %v", err)
	}
	if _, err := app.NewServices(pool, config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: 0}, payment.Fake{}, clock); !errors.Is(err, order.ErrInvalidTTL) {
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

func TestNewServicesUsesTheGivenProvider(t *testing.T) {
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(testenv.Pool(t), rules, approveAll{}, func() time.Time { return now })
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
