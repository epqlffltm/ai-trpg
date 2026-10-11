// billing-server/internal/testenv/testenv.go

// Package testenv 는 DB 를 쓰는 테스트가 접속 주소와 연결 풀을 얻는 곳이다. 테스트만 쓴다.
//
// 접속 주소는 환경 변수 DATABASE_URL 에서 읽고, 없으면 billing-server/.env 에서 읽는다.
// 어디에도 없으면 테스트를 건너뛰지 않고 실패시킨다. 건너뛰면 DB 테스트가 한 번도 돌지 않았는데
// 초록불이 켜진다.
//
// 테이블을 쓰는 테스트는 개발용 스키마(billing)가 아니라 테스트용 스키마(billing_test)에서 돈다.
// 스키마 이름을 설정에서 읽지 않고 여기에 적어 둔다. .env 에 무엇이 적혀 있든 테스트가 개발용 데이터를 건드리지 않는다.
package testenv

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/migrate"
)

// Schema 는 테스트가 테이블을 만들고 쓰는 스키마다.
const Schema = "billing_test"

// migrated 는 이 프로세스에서 테스트용 스키마에 마이그레이션을 적용한 결과를 기억한다.
// 테스트마다 다시 적용하지 않는다.
var migrated struct {
	once sync.Once
	err  error
}

// Pool 은 테스트용 스키마를 쓰는 연결 풀을 돌려준다. 테스트가 끝나면 닫는다.
// 처음 부를 때 마이그레이션을 최신까지 적용한다. 그래서 go test 만 돌리면 되고, 테스트용 스키마를 손으로 맞추지 않는다.
//
// 테스트끼리는 테이블을 비우지 않는다. 테스트마다 새 사용자 번호를 만들어 쓰면 서로의 줄이 섞이지 않는다.
func Pool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	databaseURL := DatabaseURL(t)
	migrated.once.Do(func() {
		_, migrated.err = migrate.Up(context.Background(), databaseURL, Schema)
	})
	if migrated.err != nil {
		t.Fatalf("%s 스키마에 마이그레이션을 적용하지 못했다. 스키마가 있는지 확인한다(README 의 '테스트'): %v", Schema, migrated.err)
	}
	pool, err := database.NewPool(context.Background(), databaseURL, Schema)
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// DatabaseURL 은 테스트가 쓸 접속 주소를 돌려준다. 없으면 테스트를 실패시킨다.
func DatabaseURL(t *testing.T) string {
	t.Helper()
	if value := os.Getenv("DATABASE_URL"); value != "" {
		return value
	}
	values, err := godotenv.Read(filepath.Join(moduleRoot(t), ".env"))
	if err == nil && values["DATABASE_URL"] != "" {
		return values["DATABASE_URL"]
	}
	t.Fatal("DATABASE_URL 이 없다. billing-server/.env 에 적거나 환경 변수로 넘겨야 DB 테스트가 돈다")
	return ""
}

// moduleRoot 는 go.mod 가 있는 폴더(billing-server)를 찾는다.
// go test 는 테스트하는 패키지의 폴더에서 돌기 때문에, 위로 올라가며 찾는다.
func moduleRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("현재 폴더를 알 수 없다: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("go.mod 를 찾지 못했다")
		}
		dir = parent
	}
}
