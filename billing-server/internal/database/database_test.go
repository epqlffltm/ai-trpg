// billing-server/internal/database/database_test.go

package database_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// 아무도 듣지 않는 포트. 연결이 바로 거절된다.
const unreachableURL = "postgres://billing:unused@127.0.0.1:1/trpg"

// openPool 은 실제 DB 에 붙는 풀을 만들고, 테스트가 끝나면 닫는다.
func openPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	pool, err := database.NewPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema)
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// within 은 시간 제한이 걸린 context 를 만든다. DB 가 답하지 않아도 테스트가 멈추지 않는다.
func within(t *testing.T, limit time.Duration) context.Context {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), limit)
	t.Cleanup(cancel)
	return ctx
}

func TestNewPoolConfigSetsSearchPathAndTimeout(t *testing.T) {
	poolConfig, err := database.NewPoolConfig(unreachableURL, "billing")
	if err != nil {
		t.Fatalf("설정을 만들지 못했다: %v", err)
	}

	if got := poolConfig.ConnConfig.RuntimeParams["search_path"]; got != "billing" {
		t.Errorf("search_path = %q, 기대 = %q", got, "billing")
	}
	if poolConfig.ConnConfig.ConnectTimeout != database.ConnectTimeout {
		t.Errorf("접속 제한 = %v, 기대 = %v", poolConfig.ConnConfig.ConnectTimeout, database.ConnectTimeout)
	}
}

func TestNewPoolConfigHidesTheURLInErrors(t *testing.T) {
	const secret = "do-not-print-me"
	_, err := database.NewPoolConfig("postgres://billing:"+secret+"@127.0.0.1:not-a-port/trpg", "billing")

	if !errors.Is(err, database.ErrInvalidURL) {
		t.Fatalf("오류 = %v, 기대 = ErrInvalidURL", err)
	}
	if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), "127.0.0.1") {
		t.Errorf("오류에 접속 주소가 실렸다: %v", err)
	}
}

func TestNewPoolDoesNotConnectUntilUsed(t *testing.T) {
	// DB 가 죽어 있어도 서버는 떠야 한다. 풀을 만드는 것은 성공하고, 쓸 때 실패한다
	pool, err := database.NewPool(context.Background(), unreachableURL, "billing")
	if err != nil {
		t.Fatalf("풀을 만드는 데서 실패했다: %v", err)
	}
	defer pool.Close()

	if err := pool.Ping(within(t, 10*time.Second)); err == nil {
		t.Error("아무도 듣지 않는 주소인데 Ping 이 성공했다")
	}
}

func TestPingReachesTheDatabase(t *testing.T) {
	pool := openPool(t)

	if err := pool.Ping(within(t, 10*time.Second)); err != nil {
		t.Fatalf("DB 가 답하지 않는다: %v", err)
	}
}

func TestConnectsAsTheBillingRole(t *testing.T) {
	pool := openPool(t)

	var user string
	if err := pool.QueryRow(within(t, 10*time.Second), "SELECT current_user").Scan(&user); err != nil {
		t.Fatalf("조회하지 못했다: %v", err)
	}

	// 슈퍼유저로 테스트하면 권한 때문에 실패할 코드가 통과한다
	if user != "billing" {
		t.Errorf("접속한 계정 = %q, 기대 = %q", user, "billing")
	}
}

func TestSearchPathIsTheBillingSchemaOnly(t *testing.T) {
	pool := openPool(t)

	var path string
	if err := pool.QueryRow(within(t, 10*time.Second), "SHOW search_path").Scan(&path); err != nil {
		t.Fatalf("조회하지 못했다: %v", err)
	}

	if path != "billing" {
		t.Errorf("search_path = %q, 기대 = %q", path, "billing")
	}
}

func TestOwnsItsSchemas(t *testing.T) {
	pool := openPool(t)

	// 개발용과 테스트용 둘 다다. 마이그레이션이 이 계정으로 테이블을 만든다
	for _, schema := range []string{config.DefaultSchema, testenv.Schema} {
		var canCreate bool
		query := "SELECT has_schema_privilege(current_user, $1, 'CREATE')"
		if err := pool.QueryRow(within(t, 10*time.Second), query, schema).Scan(&canCreate); err != nil {
			t.Fatalf("%s 스키마를 조회하지 못했다: %v", schema, err)
		}
		if !canCreate {
			t.Errorf("billing 계정이 %s 스키마에 테이블을 만들 수 없다", schema)
		}
	}
}

func TestCannotUseOtherServicesSchemas(t *testing.T) {
	pool := openPool(t)

	// 다른 서비스의 테이블을 직접 읽지 않는다는 것을 약속이 아니라 DB 권한으로 지킨다.
	// 스키마에 들어갈 권한(USAGE)이 없으면 그 안의 어떤 테이블도 읽거나 고칠 수 없다
	for _, schema := range []string{"auth", "game", "game_test"} {
		t.Run(schema, func(t *testing.T) {
			var canUse bool
			query := "SELECT has_schema_privilege(current_user, $1, 'USAGE')"
			if err := pool.QueryRow(within(t, 10*time.Second), query, schema).Scan(&canUse); err != nil {
				t.Fatalf("조회하지 못했다: %v", err)
			}
			if canUse {
				t.Errorf("billing 계정이 %s 스키마에 들어갈 수 있다", schema)
			}
		})
	}
}

func TestCannotCreateDatabases(t *testing.T) {
	pool := openPool(t)

	var canCreateDB bool
	query := "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"
	if err := pool.QueryRow(within(t, 10*time.Second), query).Scan(&canCreateDB); err != nil {
		t.Fatalf("조회하지 못했다: %v", err)
	}

	if canCreateDB {
		t.Error("billing 계정이 DB 를 새로 만들 수 있다. 필요 없는 권한이다")
	}
}

func TestTimesAreReadInUTCWhateverTheMachineZone(t *testing.T) {
	// 서버를 띄운 PC 가 한국 시간이다. 그래도 DB 에서 읽은 시각은 UTC 다. 응답의 표기가 PC 에 따라 바뀌지 않는다
	previous := time.Local
	time.Local = time.FixedZone("KST", 9*60*60)
	t.Cleanup(func() { time.Local = previous })
	pool := openPool(t)
	const query = "SELECT TIMESTAMPTZ '2026-03-02 09:00:00+00', TIMESTAMPTZ '2026-03-02 18:00:00+09'"

	var plain time.Time
	var nullable pgtype.Timestamptz
	if err := pool.QueryRow(within(t, 10*time.Second), query).Scan(&plain, &nullable); err != nil {
		t.Fatalf("조회하지 못했다: %v", err)
	}

	want := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	if plain.Location() != time.UTC || !plain.Equal(want) {
		t.Errorf("시각 = %v (%v), 기대 = %v (UTC)", plain, plain.Location(), want)
	}
	if !nullable.Valid || nullable.Time.Location() != time.UTC || !nullable.Time.Equal(want) {
		t.Errorf("NULL 일 수 있는 칸의 시각 = %v (%v)", nullable.Time, nullable.Time.Location())
	}
}
