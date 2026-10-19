// billing-server/internal/app/app.go

// Package app 은 서버와 작업 명령(cmd/sweeper, cmd/reconcile)이 같은 방법으로 서비스와 로거를 만들게 한다.
//
// 지갑, 주문, 홀드를 만드는 방법이 명령마다 다르면 규칙(무료 크레딧의 기한, 홀드의 기한, 결제 대행사)이 어긋난다.
// 그래서 만드는 곳을 하나로 둔다. 이 패키지는 만들기만 하고 일은 하지 않는다.
package app

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// Services 는 크레딧을 다루는 서비스들이다. 가격표(Prices)는 홀드가 쓰고, 값을 바꾸는 명령(cmd/prices)도 쓴다.
type Services struct {
	Wallet      *wallet.Service
	Orders      *order.Service
	Holds       *hold.Service
	Prices      *pricing.Service
	Eligibility *eligibility.Service
}

// NewServices 는 규칙에 따라 서비스들을 만든다. providers 는 주문이 길마다 부를 결제 대행사(NewProviders),
// now 는 지금 시각을 돌려주는 함수다.
func NewServices(pool *pgxpool.Pool, rules config.Rules, providers order.Providers, now func() time.Time) (Services, error) {
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: rules.SpendFreeFirst, FreeTTL: rules.FreeCreditTTL})
	orders, err := order.NewService(pool, now, providers, wallets, rules.OrderTTL)
	if err != nil {
		return Services{}, err
	}
	prices := pricing.NewService(pool, now)
	holds, err := hold.NewService(pool, now, wallets, prices, rules.HoldTTL)
	if err != nil {
		return Services{}, err
	}
	return Services{Wallet: wallets, Orders: orders, Holds: holds, Prices: prices, Eligibility: eligibility.NewService(pool, now)}, nil
}

// NewProviders 는 주문의 길마다 부를 결제 대행사를 만든다. 서버와 작업 명령이 이것으로 만들어 같은 결제 대행사에 묻는다.
// 지금은 웹 하나다.
func NewProviders(settings config.Payment) order.Providers {
	return order.Providers{order.ChannelWeb: NewProvider(settings)}
}

// MeasureProviders 는 길마다의 결제 대행사를 부를 때마다 meter 로 세게 감싼다. name 은 label provider 다(PAYMENT_PROVIDER).
// 결제 대행사를 부르는 프로세스(서버, 대사)가 쓴다. 빈 자리(nil)는 감싸지 않는다. 주문 서비스가 빈 웹 자리를 거절하게 둔다.
func MeasureProviders(providers order.Providers, name string, meter metric.Meter) (order.Providers, error) {
	measured := order.Providers{}
	for channel, provider := range providers {
		if provider == nil {
			measured[channel] = nil
			continue
		}
		wrapped, err := payment.Measured(provider, name, meter)
		if err != nil {
			return nil, err
		}
		measured[channel] = wrapped
	}
	return measured, nil
}

// MeasureServices 는 서비스들이 바꾼 것(주문의 상태)을 meter 로 세게 한다. 서비스를 쓰기 전에 한 번 부른다.
func MeasureServices(services Services, meter metric.Meter) error {
	return services.Orders.Measure(meter)
}

// NoProviders 는 결제 대행사를 부르지 않는 정리 작업의 것이다. 웹 자리에 부르면 오류를 내는 것(payment.None)을 둔다.
func NoProviders() order.Providers {
	return order.Providers{order.ChannelWeb: payment.None{}}
}

// NewProvider 는 설정이 고른 웹의 결제 대행사를 만든다.
// 설정이 값을 이미 검사했다. toss 가 아니면 가짜다.
func NewProvider(settings config.Payment) payment.Provider {
	if settings.Provider == config.ProviderToss {
		return payment.NewToss(settings.TossSecretKey, payment.TossAPIURL, nil)
	}
	return payment.Fake{}
}

// NewMetrics 는 메트릭을 수집기에 미는 것을 만든다. process 는 이 서버의 어느 프로세스인지다(server, sweeper, reconcile).
// 보낼 곳이 없으면 아무것도 보내지 않는 것이다. 끌 때 Shutdown 을 불러 남은 것을 보낸다.
func NewMetrics(ctx context.Context, settings config.Metrics, logging config.Logging, process string) (*metrics.Provider, error) {
	return metrics.NewProvider(ctx,
		metrics.Exporting{Endpoint: settings.Endpoint, Interval: settings.Interval},
		metrics.Identity{
			Service:     obs.ServiceName,
			Version:     logging.AppVersion,
			Environment: logging.AppEnvironment,
			Process:     process,
		},
	)
}

// StartMetrics 는 메트릭의 설정을 읽고(config.LoadMetrics) 미는 것을 만든다. 설정이 틀렸으면 프로세스가 뜨지 않는다.
func StartMetrics(ctx context.Context, lookup config.Lookup, logging config.Logging, process string) (*metrics.Provider, error) {
	settings, err := config.LoadMetrics(lookup)
	if err != nil {
		return nil, err
	}
	return NewMetrics(ctx, settings, logging, process)
}

// CloseMetrics 는 남은 메트릭을 보내고 끈다. 보내지 못해도 끄는 일은 멈추지 않는다. 까닭은 경고로 남긴다.
// 오류의 글은 싣지 않고 종류만 남긴다. 다른 서버에 닿지 못한 줄과 같은 모양이다.
func CloseMetrics(provider *metrics.Provider) {
	if err := provider.Shutdown(); err != nil {
		slog.Warn("남은 메트릭을 수집기에 보내지 못했습니다",
			slog.String(obs.FieldOperation, "metrics.shutdown"),
			slog.String(obs.FieldErrorType, fmt.Sprintf("%T", err)),
		)
	}
}

// NewLogger 는 공통 규격(docs/observability.md)의 JSON 으로 out 에 적는 로거를 만든다.
func NewLogger(out io.Writer, logging config.Logging) *slog.Logger {
	info := obs.ServiceInfo{
		Service:     obs.ServiceName,
		Environment: logging.AppEnvironment,
		Version:     logging.AppVersion,
	}
	// 설정이 이미 값을 검사했다. 모르는 값이면 info 다
	level, _ := obs.ParseLevel(logging.LogLevel)
	return obs.NewLogger(out, info, level)
}
