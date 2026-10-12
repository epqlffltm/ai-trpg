// billing-server/internal/jobs/jobs_test.go

package jobs_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// capture 는 테스트 동안 기본 로거를 버퍼에 적는 것으로 바꾸고, 남긴 줄들을 읽는 함수를 돌려준다.
func capture(t *testing.T) func() []map[string]any {
	t.Helper()
	var out bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(obs.NewLogger(&out, obs.ServiceInfo{Service: obs.ServiceName}, slog.LevelDebug))
	t.Cleanup(func() { slog.SetDefault(previous) })
	return func() []map[string]any {
		var lines []map[string]any
		for _, text := range strings.Split(strings.TrimSpace(out.String()), "\n") {
			var line map[string]any
			if err := json.Unmarshal([]byte(text), &line); err != nil {
				t.Fatalf("JSON 이 아닌 줄: %q", text)
			}
			lines = append(lines, line)
		}
		return lines
	}
}

func TestRunGivesTheWorkAJobIDAndLogsTheEnd(t *testing.T) {
	lines := capture(t)
	var seen obs.IDs

	err := jobs.Run(context.Background(), "sweep.run", func(ctx context.Context) error {
		seen = obs.CurrentIDs(ctx)
		slog.InfoContext(ctx, "정리했다")
		return nil
	})

	if err != nil || seen.JobID == "" || seen.Trace.ID == "" || seen.RequestID != "" {
		t.Fatalf("오류 = %v, 식별자 = %+v", err, seen)
	}
	got := lines()
	if len(got) != 2 {
		t.Fatalf("줄이 %d 개다: %v", len(got), got)
	}
	// 일 안의 줄과 끝난 줄이 같은 작업 번호로 묶인다
	for _, line := range got {
		if line["job_id"] != seen.JobID || line["trace_id"] != seen.Trace.ID {
			t.Errorf("줄 = %v", line)
		}
	}
	end := got[1]
	if end["level"] != "debug" || end["operation"] != "sweep.run" || end["result"] != "success" || end["duration_ms"] == nil {
		t.Errorf("끝난 줄 = %v", end)
	}
}

func TestEachRunIsANewJob(t *testing.T) {
	capture(t)
	var first, second string
	_ = jobs.Run(context.Background(), "sweep.run", func(ctx context.Context) error { first = obs.CurrentIDs(ctx).JobID; return nil })
	_ = jobs.Run(context.Background(), "sweep.run", func(ctx context.Context) error { second = obs.CurrentIDs(ctx).JobID; return nil })
	if first == "" || first == second {
		t.Errorf("작업 번호 = %q, %q. 바퀴마다 달라야 한다", first, second)
	}
}

func TestAFailedRunIsAnErrorWithItsCode(t *testing.T) {
	lines := capture(t)
	broken := errors.New("connection refused")

	err := jobs.Run(context.Background(), "reconcile.run", func(context.Context) error { return broken })

	if !errors.Is(err, broken) {
		t.Fatalf("오류 = %v. do 의 오류를 그대로 돌려줘야 한다", err)
	}
	end := lines()[0]
	if end["level"] != "error" || end["result"] != "server_error" || end["error_code"] != "job.failed" ||
		end["error_message"] != "connection refused" {
		t.Errorf("끝난 줄 = %v", end)
	}
}

func TestACancelledRunIsAWarning(t *testing.T) {
	lines := capture(t)
	ctx, cancel := context.WithCancel(context.Background())

	err := jobs.Run(ctx, "sweep.run", func(ctx context.Context) error {
		cancel()
		return ctx.Err()
	})

	end := lines()[0]
	if !errors.Is(err, context.Canceled) || end["level"] != "warning" || end["result"] != "cancelled" {
		t.Errorf("오류 = %v, 끝난 줄 = %v", err, end)
	}
}
