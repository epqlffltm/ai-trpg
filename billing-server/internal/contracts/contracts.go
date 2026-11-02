// billing-server/internal/contracts/contracts.go

// Package contracts 는 서버들이 함께 지키는 공통 규격의 시험 파일(shared/contracts/, #786)을 테스트에서 읽는다.
//
// 같은 파일을 공용 코드(shared/server-core)와 인증 서버(Django)의 테스트도 읽는다.
// 셋 중 하나라도 어긋나면 그 쪽의 CI 가 떨어진다. 규칙은 shared/contracts/README.md 에 있다.
package contracts

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// Load 는 시험 파일 하나를 읽어 into 에 넣는다.
// go test 는 테스트하는 패키지의 폴더에서 돌기 때문에, 위로 올라가며 shared/contracts 를 찾는다.
func Load(t testing.TB, name string, into any) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(folder(t), name))
	if err != nil {
		t.Fatalf("시험 파일 %s 를 읽지 못했다: %v", name, err)
	}
	if err := json.Unmarshal(data, into); err != nil {
		t.Fatalf("시험 파일 %s 의 모양이 다르다: %v", name, err)
	}
}

// folder 는 저장소의 shared/contracts 폴더다.
func folder(t testing.TB) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("현재 폴더를 알 수 없다: %v", err)
	}
	for {
		candidate := filepath.Join(dir, "shared", "contracts")
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("shared/contracts 를 찾지 못했다")
		}
		dir = parent
	}
}
