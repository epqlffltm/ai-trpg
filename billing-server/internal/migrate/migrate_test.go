// billing-server/internal/migrate/migrate_test.go

// 테스트용 스키마(billing_test)에서 돈다. 다른 패키지의 테스트가 같은 스키마의 테이블을 함께 쓰므로
// 여기서는 되돌리기(Down)를 돌리지 않는다. 적용했다 되돌렸다 다시 적용하는 확인은 CI 가 개발용 스키마에서 한다.
package migrate_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/migrate"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/migrations"
)

// within 은 시간 제한이 걸린 context 를 만든다.
func within(t *testing.T) context.Context {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	t.Cleanup(cancel)
	return ctx
}

// files 는 실행 파일에 담긴 마이그레이션 파일의 이름들이다.
func files(t *testing.T) []string {
	t.Helper()
	entries, err := migrations.Files.ReadDir(".")
	if err != nil {
		t.Fatalf("마이그레이션 파일을 읽지 못했다: %v", err)
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		names = append(names, entry.Name())
	}
	return names
}

func TestUpAppliesEveryFileAndIsSafeToRepeat(t *testing.T) {
	// testenv.Pool 이 이미 최신까지 적용했다
	pool := testenv.Pool(t)

	applied, err := migrate.Up(within(t), testenv.DatabaseURL(t), testenv.Schema)
	if err != nil || len(applied) != 0 {
		t.Fatalf("다시 적용 = %v, %v. 적용할 것이 없어야 한다", applied, err)
	}

	steps, err := migrate.Status(within(t), testenv.DatabaseURL(t), testenv.Schema)
	if err != nil {
		t.Fatalf("상태를 읽지 못했다: %v", err)
	}
	names := files(t)
	if len(steps) != len(names) || len(steps) == 0 {
		t.Fatalf("상태가 %d 줄이다. 파일은 %d 개다", len(steps), len(names))
	}
	for index, step := range steps {
		if step.Name != names[index] || !step.Applied {
			t.Errorf("%d 번째 = %+v, 기대 = {%s 적용됨}", index+1, step, names[index])
		}
	}

	// 테이블과 goose 의 기록표가 테스트용 스키마 안에 놓였다
	for _, table := range []string{"wallets", "free_grants", "ledger_entries", "goose_db_version"} {
		var schema string
		query := "SELECT table_schema FROM information_schema.tables WHERE table_name = $1 AND table_schema = $2"
		if err := pool.QueryRow(within(t), query, table, testenv.Schema).Scan(&schema); err != nil {
			t.Errorf("%s 가 %s 스키마에 없다: %v", table, testenv.Schema, err)
		}
	}
}

func TestConcurrentUpsDoNotCollide(t *testing.T) {
	// 서버를 여러 대 배포할 때처럼 한꺼번에 적용해도 서로 부딪치지 않는다
	testenv.Pool(t)
	errs := make(chan error, 4)
	for range 4 {
		go func() {
			_, err := migrate.Up(within(t), testenv.DatabaseURL(t), testenv.Schema)
			errs <- err
		}()
	}
	for range 4 {
		if err := <-errs; err != nil {
			t.Errorf("함께 적용하다 실패했다: %v", err)
		}
	}
}

func TestABadURLIsReportedWithoutTheURL(t *testing.T) {
	const secret = "do-not-print-me"
	badURL := "postgres://billing:" + secret + "@127.0.0.1:not-a-port/trpg"

	_, upErr := migrate.Up(within(t), badURL, testenv.Schema)
	_, downErr := migrate.Down(within(t), badURL, testenv.Schema)
	_, statusErr := migrate.Status(within(t), badURL, testenv.Schema)

	for name, err := range map[string]error{"Up": upErr, "Down": downErr, "Status": statusErr} {
		if !errors.Is(err, database.ErrInvalidURL) {
			t.Errorf("%s 의 오류 = %v. ErrInvalidURL 이어야 한다", name, err)
		}
		if err != nil && strings.Contains(err.Error(), secret) {
			t.Errorf("%s 의 오류에 비밀번호가 실렸다", name)
		}
	}
}

func TestAnUnreachableDatabaseIsAnError(t *testing.T) {
	// 아무도 듣지 않는 포트. 연결이 바로 거절된다
	const unreachable = "postgres://billing:do-not-print-me@127.0.0.1:1/trpg"

	_, err := migrate.Up(within(t), unreachable, testenv.Schema)

	if err == nil {
		t.Fatal("DB 에 닿지 못했는데 오류가 없다")
	}
	if strings.Contains(err.Error(), "do-not-print-me") {
		t.Errorf("오류에 비밀번호가 실렸다: %v", err)
	}
}
