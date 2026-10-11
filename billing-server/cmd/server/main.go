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
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	// 요청의 머리말을 다 받을 때까지 기다리는 시간. 머리말을 아주 천천히 보내 연결을 붙잡는 공격을 막는다
	readHeaderTimeout = 5 * time.Second
	// 끌 때 처리 중인 요청을 기다리는 가장 긴 시간. 넘으면 남은 연결을 끊고 끈다
	shutdownTimeout = 10 * time.Second
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("결제 서버를 띄우지 못했습니다: %v", err)
	}
}

// run 은 서버를 띄우고, 종료 신호가 올 때까지 돈다. main 과 나눈 이유는 defer 다.
// log.Fatal 은 프로세스를 바로 끝내서 defer 가 돌지 않는다. 오류를 돌려주면 풀을 닫고 나서 끝난다.
func run() error {
	loadDotEnv()
	settings, err := config.Load(os.LookupEnv)
	if err != nil {
		return err
	}

	// 종료 신호가 오면 이 context 가 끝난다
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := database.NewPool(ctx, settings.DatabaseURL, settings.DBSchema)
	if err != nil {
		return err
	}
	defer pool.Close()

	httpapi.SetMode(settings.Debug)
	wallets := newWallet(pool, settings)
	orders := newOrders(pool, wallets)
	router := httpapi.NewRouter(httpapi.Dependencies{
		DB:             pool,
		Verifier:       newVerifier(settings),
		Wallet:         wallets,
		Welcome:        wallets,
		WelcomeCredits: settings.WelcomeCredits,
		Orders:         orders,
		Notifier:       orders,
		WebhookSecret:  settings.WebhookSecret,
		Now:            time.Now,
	})
	return serve(ctx, newServer(settings, router))
}

// newOrders 는 주문을 만들고 치르는 것을 만든다. 결제 대행사의 자리에는 가짜를 꽂는다.
// 이 서버는 연습용이라 실제 돈을 받지 않는다. 실제 결제 대행사를 붙일 때 여기에서 바꿔 꽂는다.
func newOrders(pool *pgxpool.Pool, wallets *wallet.Service) *order.Service {
	return order.NewService(pool, time.Now, payment.Fake{}, wallets)
}

// newWallet 은 크레딧을 다루는 것을 만든다. 설정에서 읽은 규칙(쓰는 순서, 무료 크레딧의 기한)을 넘긴다.
func newWallet(pool *pgxpool.Pool, settings config.Settings) *wallet.Service {
	policy := wallet.Policy{FreeFirst: settings.SpendFreeFirst, FreeTTL: settings.FreeCreditTTL}
	return wallet.NewService(pool, time.Now, policy)
}

// newVerifier 는 access 토큰을 검증하는 것을 만든다. 만드는 것만으로는 인증 서버를 부르지 않는다.
// 처음 토큰을 검증할 때 공개키를 가져온다. 그래서 인증 서버가 죽어 있어도 이 서버는 뜬다.
func newVerifier(settings config.Settings) *auth.Verifier {
	// 다른 서버에 요청을 보내는 클라이언트. 시간 제한은 요청마다 부르는 쪽이 건다(jwks.FetchTimeout)
	fetcher := jwks.HTTPFetcher{Client: &http.Client{}, URL: settings.AuthJWKSURL}
	keys := jwks.NewCache(fetcher, time.Now)
	return auth.NewVerifier(keys, settings.JWTIssuer, settings.JWTAudience, time.Now)
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
// 이미 있는 환경 변수는 덮어쓰지 않는다. 운영과 CI 는 .env 없이 환경 변수만으로 돈다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		log.Printf(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
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
		log.Printf("결제 서버가 %s 에서 요청을 받습니다", server.Addr)
		failed <- server.ListenAndServe()
	}()

	select {
	case err := <-failed:
		return err
	case <-ctx.Done():
		log.Printf("종료 신호를 받았습니다. 처리 중인 요청을 기다립니다")
		return shutDown(server)
	}
}

// shutDown 은 새 요청을 받지 않고, 처리 중인 요청이 끝나기를 정해 둔 시간까지 기다린다.
func shutDown(server *http.Server) error {
	ctx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	return server.Shutdown(ctx)
}
