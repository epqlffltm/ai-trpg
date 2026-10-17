// billing-server/internal/httpapi/deadline_test.go

package httpapi_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 요청의 마감(#334)을 본다. 테스트는 마감을 짧게 줄여 쓴다.
const shortDeadline = 100 * time.Millisecond

// waitingWallet 은 잔액을 물으면 ctx 가 끝날 때까지 기다리는 가짜 지갑이다. 연결 풀이 모두 쓰인 것과 같다.
// pgx 처럼 ctx 의 오류를 감싸 돌려준다.
type waitingWallet struct{ fakeWallet }

func (*waitingWallet) Balance(ctx context.Context, _ uuid.UUID) (wallet.Balance, error) {
	<-ctx.Done()
	return wallet.Balance{}, fmt.Errorf("지갑을 읽지 못했다: %w", ctx.Err())
}

// observeWithDeadline 은 서버와 같은 로거를 꽂고 마감을 줄인 라우터를 만든다.
func observeWithDeadline(t *testing.T, reader httpapi.WalletReader, limit time.Duration) observed {
	t.Helper()
	var out bytes.Buffer
	info := obs.ServiceInfo{Service: obs.ServiceName, Environment: "test", Version: "test-version"}
	router := httpapi.NewRouter(httpapi.Dependencies{
		DB:             &fakeDB{},
		Verifier:       &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}},
		Wallet:         reader,
		Logger:         obs.NewLogger(&out, info, slog.LevelDebug),
		RequestTimeout: limit,
	})
	return observed{router: router, out: &out}
}

func TestARequestPastItsDeadlineIsA503ToSendAgain(t *testing.T) {
	server := observeWithDeadline(t, &waitingWallet{}, shortDeadline)

	started := time.Now()
	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	if elapsed := time.Since(started); elapsed > 5*time.Second {
		t.Fatalf("%v 동안 기다렸다. 마감에서 끝나야 한다", elapsed)
	}
	if response.Code != http.StatusServiceUnavailable || !strings.Contains(body(response), "다시 보내 주세요") {
		t.Fatalf("응답 = %d %s. 다시 보내라는 503 이어야 한다", response.Code, body(response))
	}
	// DB 가 끊은 것(database.timeout)과 따로 센다. 이것은 연결 풀이 모자란 것을 먼저 의심한다
	failures := server.errorLines(t)
	if len(failures) != 1 || failures[0]["error_code"] != "request.timeout" {
		t.Fatalf("오류 줄 = %v", failures)
	}
	if line := server.finished(t); line["status_code"] != float64(503) || line["result"] != "server_error" {
		t.Errorf("요청이 끝난 줄 = %v", line)
	}
}

func TestAFastRequestIsNotCutByTheDeadline(t *testing.T) {
	server := observeWithDeadline(t, &fakeWallet{}, shortDeadline)

	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	if response.Code != http.StatusOK || len(server.errorLines(t)) != 0 {
		t.Errorf("응답 = %d %s, 오류 줄 = %v", response.Code, body(response), server.errorLines(t))
	}
}

func TestAClientThatLeftIsNotAServerError(t *testing.T) {
	// 게임 서버가 5초 뒤 포기하고 떠난 요청 같은 것이다. 응답을 받을 쪽이 없다
	server := observeWithDeadline(t, &waitingWallet{}, time.Minute)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	request := httptest.NewRequestWithContext(ctx, http.MethodGet, walletURL, nil)
	request.Header.Set("Authorization", "Bearer the-token")
	response := httptest.NewRecorder()

	server.router.ServeHTTP(response, request)

	if failures := server.errorLines(t); len(failures) != 0 {
		t.Errorf("서버의 오류로 적었다: %v", failures)
	}
	line := server.finished(t)
	if line["status_code"] != float64(499) || line["result"] != "client_error" || line["level"] != "info" {
		t.Errorf("요청이 끝난 줄 = %v. 499, client_error, info 여야 한다", line)
	}
	if response.Body.Len() != 0 {
		t.Errorf("받을 쪽이 없는데 본문을 썼다: %s", body(response))
	}
}

func TestACanceledErrorWhileTheClientIsStillThereIsAServerError(t *testing.T) {
	// 요청은 멀쩡한데 안에서 취소가 올라왔다. 서버 쪽의 문제다. 클라이언트가 떠난 것으로 덮지 않는다
	cause := fmt.Errorf("지갑을 읽지 못했다: %w", context.Canceled)
	server := observeWithDeadline(t, &fakeWallet{err: cause}, time.Minute)

	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	failures := server.errorLines(t)
	if response.Code != http.StatusInternalServerError || len(failures) != 1 || failures[0]["error_code"] != "internal.error" {
		t.Errorf("응답 = %d, 오류 줄 = %v", response.Code, failures)
	}
}

func TestTheDeadlineIsTheGameServersBudget(t *testing.T) {
	// 게임 서버가 결제 서버에 주는 예산(BILLING_BUDGET_SECONDS, 10초), 서버의 쿼리 한도와 같다
	if httpapi.RequestTimeout != 10*time.Second || httpapi.RequestTimeout != database.ServerLimits.StatementTimeout {
		t.Errorf("마감 = %v, 쿼리 한도 = %v", httpapi.RequestTimeout, database.ServerLimits.StatementTimeout)
	}
}

// exhaustedPool 은 연결을 모두 쥔 작은 풀이다. 돌려주는 함수를 부르면 연결을 놓는다.
func exhaustedPool(t *testing.T) (*pgxpool.Pool, func()) {
	t.Helper()
	testenv.Pool(t) // 테스트용 스키마에 마이그레이션을 적용한다
	poolConfig, err := database.NewPoolConfig(testenv.DatabaseURL(t), testenv.Schema, database.Limits{MaxConns: 2})
	if err != nil {
		t.Fatal(err)
	}
	pool, err := pgxpool.NewWithConfig(context.Background(), poolConfig)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)

	var held []*pgxpool.Conn
	for range poolConfig.MaxConns {
		conn, err := pool.Acquire(context.Background())
		if err != nil {
			t.Fatalf("연결을 쥐지 못했다: %v", err)
		}
		held = append(held, conn)
	}
	return pool, func() {
		for _, conn := range held {
			conn.Release()
		}
	}
}

func TestAnExhaustedPoolAnswers503AndTheHoldIsPlacedOnceAfter(t *testing.T) {
	// 실제 서비스와 DB 로 본다. 연결이 모두 쓰인 동안의 요청은 마감에서 503 이고, 아무것도 적히지 않는다.
	// 같은 이름표로 다시 보내면 한 번만 걸린다
	pool, release := exhaustedPool(t)
	now := func() time.Time { return webhookNow }
	services := realServices(t, pool, now)
	deps := httpapi.Dependencies{
		Wallet: services.Wallet, Holds: services.Holds, GameServerSecret: gameSecret, Now: now, RequestTimeout: shortDeadline,
	}
	user := uuid.New()
	reference := "table:" + uuid.NewString() + ":round:1"
	placeText := `{"user_id":"` + user.String() + `","reference":"` + reference + `","price_code":"narration.standard"}`
	balance := func() *httptest.ResponseRecorder {
		return sendAs(t, deps, user.String(), request{method: http.MethodGet, path: walletURL})
	}

	if response := asGame(t, deps, holdsURL, placeText); response.Code != http.StatusServiceUnavailable {
		t.Fatalf("풀이 모두 쓰인 동안의 홀드 = %d %s. 503 이어야 한다", response.Code, body(response))
	}
	if response := balance(); response.Code != http.StatusServiceUnavailable {
		t.Fatalf("풀이 모두 쓰인 동안의 잔액 = %d %s. 503 이어야 한다", response.Code, body(response))
	}

	release()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := services.Wallet.Deposit(ctx, user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	if again := asGame(t, deps, holdsURL, placeText); again.Code != http.StatusCreated {
		t.Fatalf("연결이 빈 뒤의 홀드 = %d %s. 201 이어야 한다", again.Code, body(again))
	}
	if repeated := asGame(t, deps, holdsURL, placeText); repeated.Code != http.StatusOK {
		t.Fatalf("같은 이름표의 홀드 = %d %s. 200 이어야 한다", repeated.Code, body(repeated))
	}
	if got := body(balance()); !strings.Contains(got, `"paid":"50"`) {
		t.Errorf("잔액 = %s. 한 번만 빠져 50 이어야 한다", got)
	}
}

func TestAnErrorIsNotAPastDeadlineByItsText(t *testing.T) {
	// 글이 비슷해도 감싼 오류가 아니면 마감으로 보지 않는다
	server := observeWithDeadline(t, &fakeWallet{err: errors.New("context deadline exceeded")}, time.Minute)

	response := server.send(http.MethodGet, walletURL, "Authorization", "Bearer the-token")

	if response.Code != http.StatusInternalServerError {
		t.Errorf("상태 코드 = %d. 500 이어야 한다", response.Code)
	}
}
