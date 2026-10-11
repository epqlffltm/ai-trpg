// billing-server/internal/testenv/testenv.go

// Package testenv 는 DB 를 쓰는 테스트가 접속 주소를 얻는 곳이다. 테스트만 쓴다.
//
// 접속 주소는 환경 변수 DATABASE_URL 에서 읽고, 없으면 billing-server/.env 에서 읽는다.
// 어디에도 없으면 테스트를 건너뛰지 않고 실패시킨다. 건너뛰면 DB 테스트가 한 번도 돌지 않았는데
// 초록불이 켜진다.
package testenv

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/joho/godotenv"
)

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
