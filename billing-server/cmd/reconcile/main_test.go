// billing-server/cmd/reconcile/main_test.go

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/reconcile"
)

// fakeRunner 는 정해 둔 결과로 답하는 가짜 대사다. 받은 옵션을 적는다.
type fakeRunner struct {
	report reconcile.Report
	err    error
	got    reconcile.Options
}

func (f *fakeRunner) Run(_ context.Context, options reconcile.Options) (reconcile.Report, error) {
	f.got = options
	return f.report, f.err
}

// captureLogs 는 테스트 동안 기본 로거를 버퍼에 적는 것으로 바꾸고, 남긴 줄들을 읽는 함수를 돌려준다.
func captureLogs(t *testing.T) func() []map[string]any {
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

func TestParseOptions(t *testing.T) {
	opts, err := parseOptions(nil)
	if err != nil || opts != (options{staleAfter: 10 * time.Minute, limit: reconcile.DefaultLimit}) {
		t.Errorf("기본 옵션 = %+v, %v", opts, err)
	}
	opts, err = parseOptions([]string{"-stale-after", "1h", "-limit", "5"})
	if err != nil || opts != (options{staleAfter: time.Hour, limit: 5}) {
		t.Errorf("옵션 = %+v, %v", opts, err)
	}
	for _, bad := range [][]string{{"-stale-after", "30s"}, {"-limit", "0"}, {"-what"}, {"now"}} {
		if _, err := parseOptions(bad); err == nil {
			t.Errorf("%v: 오류가 나야 한다", bad)
		}
	}
}

func TestExitCodes(t *testing.T) {
	dirty := reconcile.Report{Mismatches: []reconcile.Mismatch{{Check: reconcile.CheckPaidBalance, ID: "x"}}}
	cases := map[string]struct {
		report reconcile.Report
		err    error
		want   int
	}{
		"맞다":          {reconcile.Report{}, nil, 0},
		"밀린 것만 있다":    {reconcile.Report{Overdue: reconcile.Overdue{Holds: 3}}, nil, 0},
		"맞지 않는 줄이 있다": {dirty, nil, 1},
		"끝내지 못했다":     {reconcile.Report{}, errors.New("db"), 2},
		"끝내지 못했지만 어긋난 것은 찾았다": {dirty, errors.New("provider"), 1},
	}
	for name, tc := range cases {
		if got := exitCode(tc.report, tc.err); got != tc.want {
			t.Errorf("%s: 끝 코드 = %d, 기대 = %d", name, got, tc.want)
		}
	}
}

func TestOnceLogsEachMismatchUnderOneJob(t *testing.T) {
	lines := captureLogs(t)
	fake := &fakeRunner{report: reconcile.Report{
		Stale: order.StaleReport{Found: 2, Paid: 1, Unknown: 1},
		Mismatches: []reconcile.Mismatch{
			{Check: reconcile.CheckPaidBalance, ID: "8c1f0000-0000-4000-8000-000000000001"},
			{Check: reconcile.CheckHoldLines, ID: "8c1f0000-0000-4000-8000-000000000002"},
		},
		Overdue: reconcile.Overdue{Orders: 4},
	}}

	_, err := once(context.Background(), fake, options{staleAfter: 15 * time.Minute, limit: 7})

	if err != nil || fake.got != (reconcile.Options{StaleAfter: 15 * time.Minute, Limit: 7}) {
		t.Fatalf("오류 = %v, 넘긴 옵션 = %+v", err, fake.got)
	}
	got := lines()
	// 주문 끝냄(info), 어긋남 둘(error), 밀림(warning), 작업이 끝났다(debug)
	if len(got) != 5 {
		t.Fatalf("줄이 %d 개다: %v", len(got), got)
	}
	jobID := got[0]["job_id"]
	for _, line := range got {
		if line["job_id"] != jobID || jobID == nil || line["operation"] != "reconcile.run" {
			t.Errorf("줄 = %v", line)
		}
	}
	if got[1]["level"] != "error" || got[1]["error_code"] != "ledger.mismatch" || got[1]["check"] != "paid_balance" ||
		got[1]["record_id"] != "8c1f0000-0000-4000-8000-000000000001" {
		t.Errorf("어긋난 줄 = %v", got[1])
	}
	if got[3]["level"] != "warning" || got[3]["error_code"] != "sweep.behind" || got[3]["overdue_orders"] != float64(4) {
		t.Errorf("밀린 줄 = %v", got[3])
	}
}

func TestOnceWithACleanReportLogsOnlyTheEnd(t *testing.T) {
	lines := captureLogs(t)

	_, err := once(context.Background(), &fakeRunner{}, options{staleAfter: time.Minute, limit: 1})

	got := lines()
	if err != nil || len(got) != 1 || got[0]["result"] != "success" {
		t.Errorf("오류 = %v, 줄 = %v", err, got)
	}
}

func TestPrintReportShowsCountsButNoIDs(t *testing.T) {
	var out bytes.Buffer
	report := reconcile.Report{
		Stale:      order.StaleReport{Found: 1, Paid: 1},
		Mismatches: []reconcile.Mismatch{{Check: reconcile.CheckDepositOrder, ID: "424242"}},
		Overdue:    reconcile.Overdue{Holds: 2},
	}

	printReport(&out, report, errors.New("x"))

	text := out.String()
	for _, want := range []string{"오래된 주문: 1", "환불 0", "맞지 않는 줄: 1", "홀드 2", "끝내지 못했습니다"} {
		if !strings.Contains(text, want) {
			t.Errorf("화면에 %q 가 없다: %s", want, text)
		}
	}
	if strings.Contains(text, "424242") {
		t.Errorf("화면에 번호가 찍혔다: %s", text)
	}
}
