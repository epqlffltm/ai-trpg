// billing-server/internal/database/limits_test.go

package database_test

import (
	"context"
	"errors"
	"fmt"
	"math/rand/v2"
	"os"
	"os/exec"
	"strconv"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// DB 가 스스로 쿼리를 끊는 시간(#296)을 시험한다. 잠금은 테이블 대신 advisory lock 으로 건다.
// lock_timeout 은 advisory lock 의 기다림에도 걸리고, 테이블을 만들지 않아도 된다.

// poolWith 는 한도를 준 풀을 만들고, 테스트가 끝나면 닫는다.
func poolWith(t *testing.T, limits database.Limits) *pgxpool.Pool {
	t.Helper()
	pool, err := database.NewPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema, limits)
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// holdAdvisoryLock 은 다른 연결에서 advisory lock 을 쥔다. 돌려준 함수를 부르면 놓는다.
// 열쇠는 테스트마다 다르다. 마이그레이션(goose)이 쓰는 잠금과 겹치지 않는다.
func holdAdvisoryLock(t *testing.T) (int64, func()) {
	t.Helper()
	key := rand.Int64()
	conn, err := openPool(t).Acquire(within(t, 10*time.Second))
	if err != nil {
		t.Fatalf("연결을 얻지 못했다: %v", err)
	}
	if _, err := conn.Exec(within(t, 10*time.Second), "SELECT pg_advisory_lock($1)", key); err != nil {
		t.Fatalf("잠그지 못했다: %v", err)
	}
	released := false
	release := func() {
		if !released {
			released = true
			_, _ = conn.Exec(context.Background(), "SELECT pg_advisory_unlock($1)", key)
			conn.Release()
		}
	}
	t.Cleanup(release)
	return key, release
}

func TestTheLimitsAreSentWhenConnecting(t *testing.T) {
	limits := database.Limits{LockTimeout: 5 * time.Second, StatementTimeout: 10 * time.Second, ClientCheckInterval: time.Second}
	poolConfig, err := database.NewPoolConfig(unreachableURL, "billing", limits)
	if err != nil {
		t.Fatalf("설정을 만들지 못했다: %v", err)
	}

	for name, want := range map[string]string{
		"lock_timeout": "5000ms", "statement_timeout": "10000ms", "client_connection_check_interval": "1000ms",
	} {
		if got := poolConfig.ConnConfig.RuntimeParams[name]; got != want {
			t.Errorf("%s = %q, 기대 = %q", name, got, want)
		}
	}
}

func TestZeroLimitsAreNotSent(t *testing.T) {
	// 0 은 "PostgreSQL 의 기본(끊지 않음)" 이다. 1밀리초보다 짧은 값도 0ms 가 되므로 보내지 않는다
	poolConfig, err := database.NewPoolConfig(unreachableURL, "billing", database.Limits{StatementTimeout: time.Microsecond})
	if err != nil {
		t.Fatalf("설정을 만들지 못했다: %v", err)
	}

	for _, name := range []string{"lock_timeout", "statement_timeout", "client_connection_check_interval"} {
		if value, ok := poolConfig.ConnConfig.RuntimeParams[name]; ok {
			t.Errorf("%s = %q 를 보냈다", name, value)
		}
	}
}

func TestTheLimitsOverrideTheURL(t *testing.T) {
	poolConfig, err := database.NewPoolConfig(unreachableURL+"?statement_timeout=0", "billing", database.ServerLimits)
	if err != nil {
		t.Fatalf("설정을 만들지 못했다: %v", err)
	}

	if got := poolConfig.ConnConfig.RuntimeParams["statement_timeout"]; got != "10000ms" {
		t.Errorf("statement_timeout = %q. 코드의 한도가 앞서야 한다", got)
	}
}

func TestEachProcessHasLimitsShorterThanItsWork(t *testing.T) {
	// 서버의 한도는 결제 작업의 마감(30초)보다 짧아야 DB 가 먼저 끊는다. order 를 가져오지 않으려고 값을 적는다
	const operationTimeout = 30 * time.Second
	if database.ServerLimits.LockTimeout >= operationTimeout || database.ServerLimits.StatementTimeout >= operationTimeout {
		t.Errorf("서버의 한도 %+v 가 결제 작업의 마감 %v 보다 짧지 않다", database.ServerLimits, operationTimeout)
	}
	// 작업 명령은 대사의 긴 검사를 끊지 않게 쿼리 하나를 더 길게 둔다
	if database.JobLimits.StatementTimeout <= database.ServerLimits.StatementTimeout {
		t.Errorf("작업 명령의 쿼리 한도 %v 가 서버의 것 %v 보다 길지 않다", database.JobLimits.StatementTimeout, database.ServerLimits.StatementTimeout)
	}
	for name, limits := range map[string]database.Limits{"server": database.ServerLimits, "job": database.JobLimits} {
		if limits.LockTimeout <= 0 || limits.StatementTimeout <= 0 || limits.ClientCheckInterval <= 0 {
			t.Errorf("%s 의 한도에 빈 것이 있다: %+v", name, limits)
		}
	}
}

func TestTheServerLimitsReachTheDatabase(t *testing.T) {
	pool := poolWith(t, database.ServerLimits)

	for name, want := range map[string]string{"lock_timeout": "5s", "statement_timeout": "10s", "client_connection_check_interval": "1s"} {
		var got string
		if err := pool.QueryRow(within(t, 10*time.Second), "SHOW "+name).Scan(&got); err != nil {
			t.Fatalf("%s 를 읽지 못했다: %v", name, err)
		}
		if got != want {
			t.Errorf("%s = %q, 기대 = %q", name, got, want)
		}
	}
}

func TestALockWaitEndsAtTheLockTimeout(t *testing.T) {
	key, _ := holdAdvisoryLock(t)
	pool := poolWith(t, database.Limits{LockTimeout: 200 * time.Millisecond})

	started := time.Now()
	_, err := pool.Exec(within(t, 10*time.Second), "SELECT pg_advisory_lock($1)", key)
	elapsed := time.Since(started)

	if !database.IsTimeout(err) {
		t.Fatalf("오류 = %v. lock_timeout 이어야 한다", err)
	}
	if elapsed > 3*time.Second {
		t.Errorf("잠금을 %v 기다렸다", elapsed)
	}
}

func TestAStatementEndsAtTheStatementTimeout(t *testing.T) {
	pool := poolWith(t, database.Limits{StatementTimeout: 200 * time.Millisecond})

	started := time.Now()
	_, err := pool.Exec(within(t, 10*time.Second), "SELECT pg_sleep(5)")
	elapsed := time.Since(started)

	if !database.IsTimeout(err) {
		t.Fatalf("오류 = %v. statement_timeout 이어야 한다", err)
	}
	if elapsed > 3*time.Second {
		t.Errorf("쿼리가 %v 돌았다", elapsed)
	}
}

// waitingBackends 는 그 이름(application_name)으로 붙어 잠금을 기다리는 연결의 수다.
func waitingBackends(t *testing.T, name string) int {
	t.Helper()
	var count int
	query := "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1 AND wait_event_type = 'Lock'"
	if err := openPool(t).QueryRow(within(t, 10*time.Second), query, name).Scan(&count); err != nil {
		t.Fatalf("pg_stat_activity 를 읽지 못했다: %v", err)
	}
	return count
}

// 죽는 프로세스(helper)가 받는 값. 부모 테스트가 환경 변수로 넘긴다.
const (
	helperKeyEnv      = "BILLING_TEST_DYING_KEY"
	helperNameEnv     = "BILLING_TEST_DYING_NAME"
	helperIntervalEnv = "BILLING_TEST_DYING_CHECK_MS"
)

// TestHelperWaitsOnTheLockUntilKilled 는 시험이 아니다. dieWhileWaiting 이 띄우는 자식 프로세스가 이것만 돈다.
// 잠금을 기다리는 쿼리를 보내 놓고, 부모가 SIGKILL 로 죽일 때까지 기다린다.
func TestHelperWaitsOnTheLockUntilKilled(t *testing.T) {
	key, err := strconv.ParseInt(os.Getenv(helperKeyEnv), 10, 64)
	if err != nil {
		t.Skip("dieWhileWaiting 이 띄울 때만 돈다")
	}
	interval, _ := strconv.Atoi(os.Getenv(helperIntervalEnv))
	poolConfig, err := database.NewPoolConfig(testenv.DatabaseURL(t), config.DefaultSchema,
		database.Limits{ClientCheckInterval: time.Duration(interval) * time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	poolConfig.ConnConfig.RuntimeParams["application_name"] = os.Getenv(helperNameEnv)
	conn, err := pgx.ConnectConfig(context.Background(), poolConfig.ConnConfig)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = conn.Exec(context.Background(), "SELECT pg_advisory_lock($1)", key)
}

// dieWhileWaiting 은 잠금을 기다리는 쿼리를 보낸 자식 프로세스를 SIGKILL 로 죽인다. 앱이 kill -9 나 OOM 으로 죽은 것과 같다.
// 죽는 프로세스는 취소 요청도 Terminate 도 보내지 못한다. 같은 프로세스 안에서 소켓만 닫으면 pgx 가 취소 요청을 보내 버려 이렇게 한다.
// 이름(application_name)을 돌려준다. 그 이름으로 DB 쪽에 연결이 남았는지 본다.
func dieWhileWaiting(t *testing.T, key int64, checkInterval time.Duration) string {
	t.Helper()
	name := fmt.Sprintf("dies-%d", rand.Int64())
	helper := exec.Command(os.Args[0], "-test.run=^TestHelperWaitsOnTheLockUntilKilled$")
	helper.Env = append(os.Environ(),
		"DATABASE_URL="+testenv.DatabaseURL(t),
		helperKeyEnv+"="+strconv.FormatInt(key, 10),
		helperNameEnv+"="+name,
		helperIntervalEnv+"="+strconv.FormatInt(checkInterval.Milliseconds(), 10),
	)
	if err := helper.Start(); err != nil {
		t.Fatalf("자식 프로세스를 띄우지 못했다: %v", err)
	}
	deadline := time.Now().Add(10 * time.Second)
	for waitingBackends(t, name) == 0 {
		if time.Now().After(deadline) {
			_ = helper.Process.Kill()
			t.Fatal("자식 프로세스의 쿼리가 잠금을 기다리기 시작하지 않았다")
		}
		time.Sleep(20 * time.Millisecond)
	}
	if err := helper.Process.Kill(); err != nil {
		t.Fatalf("자식 프로세스를 죽이지 못했다: %v", err)
	}
	_ = helper.Wait()
	return name
}

func TestTheDatabaseDropsTheWaitOfAClientThatDied(t *testing.T) {
	key, _ := holdAdvisoryLock(t)
	name := dieWhileWaiting(t, key, 100*time.Millisecond)

	deadline := time.Now().Add(5 * time.Second)
	for waitingBackends(t, name) != 0 {
		if time.Now().After(deadline) {
			t.Fatal("죽은 클라이언트의 쿼리가 5초가 지나도 잠금을 기다린다")
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func TestWithoutTheCheckTheWaitOfAClientThatDiedStays(t *testing.T) {
	// 대조군이다. 이 설정이 없으면 DB 는 죽은 클라이언트의 쿼리를 잠금이 풀릴 때까지 쥐고 있다(그 뒤 끝까지 적는다)
	key, release := holdAdvisoryLock(t)
	name := dieWhileWaiting(t, key, 0)

	time.Sleep(time.Second)
	if waitingBackends(t, name) != 1 {
		t.Fatal("설정이 없는데 죽은 클라이언트의 쿼리가 사라졌다. 대조군이 맞지 않는다")
	}
	release()
}

func TestIsTimeoutKnowsTheDatabaseTimeouts(t *testing.T) {
	for code, want := range map[string]bool{"55P03": true, "57014": true, "23505": false, "40001": false} {
		err := fmt.Errorf("감싼 오류: %w", &pgconn.PgError{Code: code})
		if got := database.IsTimeout(err); got != want {
			t.Errorf("%s: IsTimeout = %v, 기대 = %v", code, got, want)
		}
	}
	if database.IsTimeout(errors.New("그냥 오류")) || database.IsTimeout(context.DeadlineExceeded) || database.IsTimeout(nil) {
		t.Error("DB 의 오류가 아닌 것을 시간 제한으로 봤다")
	}
}

func TestThePoolSizeComesFromTheProcess(t *testing.T) {
	for name, limits := range map[string]database.Limits{"server": database.ServerLimits, "job": database.JobLimits} {
		poolConfig, err := database.NewPoolConfig(unreachableURL, "billing", limits)
		if err != nil {
			t.Fatalf("%s: 설정을 만들지 못했다: %v", name, err)
		}
		if poolConfig.MaxConns != limits.MaxConns {
			t.Errorf("%s: 연결 %d, 기대 = %d", name, poolConfig.MaxConns, limits.MaxConns)
		}
	}
	// 재 본 값이다(README 의 "연결 풀의 크기"). 작업 명령은 서버보다 적게 쥔다
	if database.ServerLimits.MaxConns != 8 || database.JobLimits.MaxConns != 2 {
		t.Errorf("서버 %d, 작업 명령 %d. 8 과 2 여야 한다", database.ServerLimits.MaxConns, database.JobLimits.MaxConns)
	}
}

func TestThePoolSizeInTheURLWins(t *testing.T) {
	// 운영에서 DB 의 코어가 더 많으면 접속 주소에서 올린다. 코드의 값이 덮어쓰지 않는다
	for _, databaseURL := range []string{
		unreachableURL + "?pool_max_conns=16",
		"host=127.0.0.1 port=1 user=billing dbname=trpg pool_max_conns=16",
	} {
		poolConfig, err := database.NewPoolConfig(databaseURL, "billing", database.ServerLimits)
		if err != nil {
			t.Fatalf("%q: 설정을 만들지 못했다: %v", databaseURL, err)
		}
		if poolConfig.MaxConns != 16 {
			t.Errorf("%q: 연결 %d. 주소의 16 이어야 한다", databaseURL, poolConfig.MaxConns)
		}
	}
}

func TestNoPoolSizeKeepsTheDriverDefault(t *testing.T) {
	// 마이그레이션처럼 한도가 없는(Limits{}) 쪽은 pgx 의 기본 그대로다
	defaults, err := pgxpool.ParseConfig(unreachableURL)
	if err != nil {
		t.Fatal(err)
	}
	poolConfig, err := database.NewPoolConfig(unreachableURL, "billing", database.Limits{})
	if err != nil {
		t.Fatal(err)
	}

	if poolConfig.MaxConns != defaults.MaxConns {
		t.Errorf("연결 %d, pgx 의 기본 = %d", poolConfig.MaxConns, defaults.MaxConns)
	}
}
