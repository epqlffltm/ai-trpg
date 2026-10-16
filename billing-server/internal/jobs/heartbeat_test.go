// billing-server/internal/jobs/heartbeat_test.go

package jobs_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
)

func TestBeatCreatesTheFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "heartbeat")

	if err := jobs.Beat(path); err != nil {
		t.Fatalf("심장박동을 남기지 못했다: %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Errorf("파일이 없다: %v", err)
	}
}

func TestBeatMovesTheTimeForward(t *testing.T) {
	path := filepath.Join(t.TempDir(), "heartbeat")
	if err := os.WriteFile(path, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	old := time.Unix(0, 0)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}

	if err := jobs.Beat(path); err != nil {
		t.Fatalf("심장박동을 남기지 못했다: %v", err)
	}
	info, err := os.Stat(path)
	if err != nil || !info.ModTime().After(old) {
		t.Errorf("시각이 바뀌지 않았다: %v, %v", info.ModTime(), err)
	}
}

func TestBeatWithoutAPathDoesNothing(t *testing.T) {
	// PC 에서 돌릴 때. 아무 파일도 만들지 않는다
	if err := jobs.Beat(""); err != nil {
		t.Errorf("오류 = %v", err)
	}
}

func TestBeatReportsAFileItCannotWrite(t *testing.T) {
	path := filepath.Join(t.TempDir(), "no-such-folder", "heartbeat")

	if err := jobs.Beat(path); !errors.Is(err, os.ErrNotExist) {
		t.Errorf("오류 = %v. 폴더가 없다는 오류여야 한다", err)
	}
}
