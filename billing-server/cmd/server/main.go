// billing-server/cmd/server/main.go

// 결제 서버의 시작점. 설정을 읽고, DB 연결 풀과 토큰 검증기, 지갑, 주문을 만들고, HTTP 서버를 띄운다.
//
//	go run ./cmd/server
//
// 테이블은 만들지 않는다. 서버를 처음 띄우기 전에 마이그레이션을 적용한다(go run ./cmd/migrate up).
//
// 종료 신호(Ctrl+C, SIGTERM)를 받으면 새 요청을 받지 않고, 처리 중인 요청이 끝나기를 기다린 뒤 끈다.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/revocations"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

const (
	// 요청의 머리말을 다 받을 때까지 기다리는 시간. 머리말을 아주 천천히 보내 연결을 붙잡는 공격을 막는다
	readHeaderTimeout = 5 * time.Second
	// 끌 때 처리 중인 요청을 기다리는 가장 긴 시간. 넘으면 남은 연결을 끊고 끈다
	shutdownTimeout = 10 * time.Second
	// 메트릭의 label instance 앞에 붙는 이 프로세스의 이름
	metricsProcess = "server"
)

func main() {
	// 설정을 읽기 전의 로그(.env 를 읽지 못했다, 설정이 틀렸다)도 같은 모양으로 나가게 한다.
	// 환경과 버전은 아직 모른다. 설정을 읽은 뒤에 그 값을 실은 로거로 바꾼다
	slog.SetDefault(obs.NewLogger(os.Stderr, obs.ServiceInfo{Service: obs.ServiceName}, slog.LevelInfo))
	if err := run(); err != nil {
		slog.Error("결제 서버를 띄우지 못했습니다",
			slog.String(obs.FieldOperation, "server.start"),
			slog.String(obs.FieldErrorCode, "server.start_failed"),
			slog.String(obs.FieldErrorMessage, err.Error()),
		)
		os.Exit(1)
	}
}

// run 은 서버를 띄우고, 종료 신호가 올 때까지 돈다. main 과 나눈 이유는 defer 다.
// os.Exit 은 프로세스를 바로 끝내서 defer 가 돌지 않는다. 오류를 돌려주면 풀을 닫고 나서 끝난다.
func run() error {
	loadDotEnv()
	settings, err := config.Load(os.LookupEnv)
	if err != nil {
		return err
	}
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging()))

	// 종료 신호가 오면 이 context 가 끝난다
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 메트릭을 수집기에 민다(OTEL_EXPORTER_OTLP_ENDPOINT 가 있을 때). 끌 때 남은 것을 보낸다
	meters, err := app.StartMetrics(ctx, os.LookupEnv, settings.Logging(), metricsProcess)
	if err != nil {
		return err
	}
	defer app.CloseMetrics(meters)
	// 요청, 다른 서버를 부르는 것, 쿼리를 span 으로 수집기에 민다(같은 주소가 있을 때). 끌 때 남은 것을 보낸다
	tracer, err := app.StartTracing(ctx, os.LookupEnv, settings.Logging(), metricsProcess)
	if err != nil {
		return err
	}
	defer app.CloseTracing(tracer)

	pool, err := database.NewMeteredPool(ctx, settings.DatabaseURL, settings.DBSchema, database.ServerLimits, meters.Meter())
	if err != nil {
		return err
	}
	defer pool.Close()

	httpapi.SetMode(settings.Debug)
	// 결제 대행사를 부른 수와 주문의 상태를 센다
	providers, err := app.MeasureProviders(app.NewProviders(settings.Payment), settings.Payment.Provider, meters.Meter())
	if err != nil {
		return err
	}
	services, err := app.NewServices(pool, settings.Rules(), providers, time.Now)
	if err != nil {
		return err
	}
	if err := app.MeasureServices(services, meters.Meter()); err != nil {
		return err
	}
	// 출석(#339). 하루 양이나 보물 상자의 확률표가 틀렸으면 서버가 뜨지 않는다
	attendances, err := attendance.NewService(pool, time.Now, services.Wallet, services.Eligibility,
		attendance.Options{Schedule: settings.AttendanceSilver})
	if err != nil {
		return err
	}
	router := httpapi.NewRouter(httpapi.Dependencies{
		DB:                pool,
		Verifier:          newVerifier(ctx, settings),
		Wallet:            services.Wallet,
		Welcome:           services.Wallet,
		WelcomeCredits:    settings.WelcomeCredits,
		Eligibility:       services.Eligibility,
		Withdrawals:       services.Withdrawals,
		Attendance:        attendances,
		Orders:            eligibility.Guard(services.Orders, services.Eligibility),
		Notifier:          services.Orders,
		WebhookSecret:     settings.WebhookSecret,
		TossWebhook:       settings.ReceivesTossNotifications(),
		Holds:             services.Holds,
		Prices:            services.Prices,
		GameServerSecret:  settings.GameServerSecret,
		AuthServerSecret:  settings.AuthServerSecret,
		ChatServerSecret:  settings.ChatServerSecret,
		CheckoutClientKey: settings.CheckoutClientKey(),
		Now:               time.Now,
		Meter:             meters.Meter(),
	})
	return serve(ctx, newServer(settings, router))
}

// newVerifier 는 access 토큰을 검증하는 것을 만든다. 만드는 것만으로는 인증 서버를 부르지 않는다.
// 처음 토큰을 검증할 때 공개키를 가져온다. 그래서 인증 서버가 죽어 있어도 이 서버는 뜬다.
// 끊긴 세션의 목록은 ctx 가 끝날 때까지 따로 30초마다 받는다(#274). 요청이 그것을 기다리지 않는다.
func newVerifier(ctx context.Context, settings config.Settings) *auth.Verifier {
	// 다른 서버에 요청을 보내는 클라이언트. 시간 제한은 요청마다 부르는 쪽이 건다(jwks.FetchTimeout).
	// 요청 안에서 부르면 span 을 걸고 traceparent 를 그 span 으로 붙인다(인증 서버는 우리 서버다)
	client := &http.Client{Transport: tracing.Transport(nil, true)}
	keys := jwks.NewCache(jwks.HTTPFetcher{Client: client, URL: settings.AuthJWKSURL}, time.Now)
	sessions := revocations.NewCache(revocations.HTTPFetcher{Client: client, URL: settings.AuthRevocationsURL})
	go sessions.Run(ctx, revocations.RefreshInterval)
	return auth.NewVerifier(keys, sessions, settings.JWTIssuer, settings.JWTAudience, time.Now)
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
// 이미 있는 환경 변수는 덮어쓰지 않는다. 운영과 CI 는 .env 없이 환경 변수만으로 돈다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		slog.Warn(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}

// newServer 는 HTTP 서버를 만든다. 아직 요청을 받지 않는다.
func newServer(settings config.Settings, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              settings.Addr(),
		Handler:           handler,
		ReadHeaderTimeout: readHeaderTimeout,
	}
}

// serve 는 요청을 받기 시작하고, ctx 가 끝나면(종료 신호) 서버를 차례로 끈다.
// 포트를 열지 못한 것처럼 서버가 먼저 죽으면 그 오류를 돌려준다.
func serve(ctx context.Context, server *http.Server) error {
	failed := make(chan error, 1)
	go func() {
		slog.Info("결제 서버가 요청을 받습니다", slog.String("addr", server.Addr))
		failed <- server.ListenAndServe()
	}()

	select {
	case err := <-failed:
		return err
	case <-ctx.Done():
		slog.Info("종료 신호를 받았습니다. 처리 중인 요청을 기다립니다")
		return shutDown(server)
	}
}

// shutDown 은 새 요청을 받지 않고, 처리 중인 요청이 끝나기를 정해 둔 시간까지 기다린다.
func shutDown(server *http.Server) error {
	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	return server.Shutdown(ctx)
}
