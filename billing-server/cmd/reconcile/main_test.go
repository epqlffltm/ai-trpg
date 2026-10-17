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

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview"
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
	if err != nil || opts != (options{staleAfter: 10 * time.Minute, stuckAfter: 24 * time.Hour, limit: reconcile.DefaultLimit}) {
		t.Errorf("기본 옵션 = %+v, %v", opts, err)
	}
	opts, err = parseOptions([]string{"-stale-after", "1h", "-stuck-after", "72h", "-limit", "5"})
	if err != nil || opts != (options{staleAfter: time.Hour, stuckAfter: 72 * time.Hour, limit: 5}) {
		t.Errorf("옵션 = %+v, %v", opts, err)
	}
	bads := [][]string{
		{"-stale-after", "30s"}, {"-limit", "0"}, {"-what"}, {"now"},
		// 결제 대행사에 한 번도 묻지 않은 주문을 사람에게 넘기지 않는다
		{"-stale-after", "2h", "-stuck-after", "2h"}, {"-stuck-after", "5m"},
	}
	for _, bad := range bads {
		if _, err := parseOptions(bad); err == nil {
			t.Errorf("%v: 오류가 나야 한다", bad)
		}
	}
}

func TestExitCodes(t *testing.T) {
	dirty := reconcile.Report{Mismatches: []reconcile.Mismatch{{Check: reconcile.CheckPaidBalance, ID: "x"}}}
	stuck := reconcile.Report{Stuck: []order.Order{{Status: order.StatusConfirming}}}
	dirtyAndStuck := reconcile.Report{Mismatches: dirty.Mismatches, Stuck: stuck.Stuck}
	review := reconcile.Report{Reviews: []pricereview.Due{{ReviewID: 1, Step: pricereview.StepNotice}}}
	dirtyAndReview := reconcile.Report{Mismatches: dirty.Mismatches, Reviews: review.Reviews}
	cases := map[string]struct {
		report reconcile.Report
		err    error
		want   int
	}{
		"맞다":          {reconcile.Report{}, nil, 0},
		"밀린 것만 있다":    {reconcile.Report{Overdue: reconcile.Overdue{Holds: 3}}, nil, 0},
		"맞지 않는 줄이 있다": {dirty, nil, 1},
		"끝내지 못했다":     {reconcile.Report{}, errors.New("db"), 2},
		"끝내지 못했지만 어긋난 것은 찾았다":   {dirty, errors.New("provider"), 1},
		"사람이 볼 주문이 있다":          {stuck, nil, 3},
		"어긋난 줄도 사람이 볼 주문도 있다":   {dirtyAndStuck, nil, 1},
		"끝내지 못했고 사람이 볼 주문이 있다":  {stuck, errors.New("db"), 2},
		"가격 변경 할 일이 있다":         {review, nil, 3},
		"어긋난 줄도 가격 변경 할 일도 있다":  {dirtyAndReview, nil, 1},
		"끝내지 못했고 가격 변경 할 일이 있다": {review, errors.New("db"), 2},
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

func TestOnceLogsEachStuckOrder(t *testing.T) {
	lines := captureLogs(t)
	since := time.Date(2026, 3, 1, 9, 0, 0, 0, time.UTC)
	stuckID := uuid.MustParse("8c1f0000-0000-4000-8000-0000000000aa")
	fake := &fakeRunner{report: reconcile.Report{Stuck: []order.Order{
		{ID: stuckID, Status: order.StatusRefunding, UpdatedAt: since, PaymentKey: "tgen_secret_key"},
	}}}

	if _, err := once(context.Background(), fake, options{staleAfter: time.Minute, stuckAfter: time.Hour, limit: 1}); err != nil {
		t.Fatalf("오류 = %v", err)
	}

	if fake.got.StuckAfter != time.Hour {
		t.Errorf("넘긴 옵션 = %+v", fake.got)
	}
	got := lines()
	// 사람이 볼 주문(warning), 작업이 끝났다(debug)
	if len(got) != 2 || got[0]["level"] != "warning" || got[0]["error_code"] != "order.stuck" ||
		got[0]["order_id"] != stuckID.String() || got[0]["status"] != "refunding" || got[0]["since"] != "2026-03-01T09:00:00.000Z" {
		t.Fatalf("줄 = %v", got)
	}
	// 결제 번호는 남기지 않는다
	for _, line := range got {
		for _, value := range line {
			if text, ok := value.(string); ok && strings.Contains(text, "tgen_secret_key") {
				t.Errorf("로그에 결제 번호가 실렸다: %v", line)
			}
		}
	}
}

func TestPrintReportCountsStuckOrdersByKind(t *testing.T) {
	var out bytes.Buffer
	report := reconcile.Report{Stuck: []order.Order{
		{ID: uuid.New(), Status: order.StatusConfirming},
		{ID: uuid.New(), Status: order.StatusConfirming},
		{ID: uuid.New(), Status: order.StatusRefunding},
	}}

	printReport(&out, report, nil)

	text := out.String()
	if !strings.Contains(text, "사람이 볼 주문: 3 (승인 확인 2, 환불 확인 1)") || !strings.Contains(text, "cmd/orders") {
		t.Errorf("화면 = %s", text)
	}
	if strings.Contains(text, report.Stuck[0].ID.String()) {
		t.Errorf("화면에 번호가 찍혔다: %s", text)
	}

	out.Reset()
	printReport(&out, reconcile.Report{}, nil)
	if !strings.Contains(out.String(), "사람이 볼 주문: 0") || strings.Contains(out.String(), "cmd/orders") {
		t.Errorf("없을 때의 화면 = %s", out.String())
	}
}

func TestOnceLogsEachDueReview(t *testing.T) {
	lines := captureLogs(t)
	changesAt := time.Date(2026, 11, 20, 15, 0, 0, 0, time.UTC)
	fake := &fakeRunner{report: reconcile.Report{Reviews: []pricereview.Due{
		{ReviewID: 3, Subject: "GPT-5.6 Sol", ChangesAt: changesAt, Step: pricereview.StepAnnounce, Stage: pricereview.StageD14, DaysLeft: 12},
		{ReviewID: 3, Subject: "GPT-5.6 Sol", ChangesAt: changesAt, Step: pricereview.StepNotice, Stage: pricereview.StageD14, DaysLeft: 12},
	}}}

	if _, err := once(context.Background(), fake, options{staleAfter: time.Minute, limit: 1}); err != nil {
		t.Fatalf("오류 = %v", err)
	}

	got := lines()
	// 할 일 둘(warning), 작업이 끝났다(debug)
	if len(got) != 3 {
		t.Fatalf("줄이 %d 개다: %v", len(got), got)
	}
	first := got[0]
	if first["level"] != "warning" || first["error_code"] != "pricing.review_due" || first["review_id"] != float64(3) ||
		first["subject"] != "GPT-5.6 Sol" || first["step"] != "announce" || first["stage"] != "d14" ||
		first["days_left"] != float64(12) || first["changes_at"] != "2026-11-20T15:00:00.000Z" {
		t.Errorf("첫 줄 = %v", first)
	}
	if got[1]["step"] != "notice" {
		t.Errorf("둘째 줄 = %v", got[1])
	}
}

func TestPrintReportListsDueReviews(t *testing.T) {
	var out bytes.Buffer
	report := reconcile.Report{Reviews: []pricereview.Due{
		{ReviewID: 3, Subject: "GPT-5.6 Sol", Step: pricereview.StepNotice, DaysLeft: 12},
		{ReviewID: 4, Subject: "Gemini 4 Argon", Step: pricereview.StepFinal, DaysLeft: -2},
	}}

	printReport(&out, report, nil)

	text := out.String()
	for _, want := range []string{"가격 변경 할 일: 2", "#3 GPT-5.6 Sol: 자세한 공지와 새 값 예약 (D-12)", "#4 Gemini 4 Argon: 마지막 알림 (값이 바뀐 뒤 2일)", "cmd/pricereviews done"} {
		if !strings.Contains(text, want) {
			t.Errorf("화면에 %q 가 없다: %s", want, text)
		}
	}

	out.Reset()
	printReport(&out, reconcile.Report{}, nil)
	if !strings.Contains(out.String(), "가격 변경 할 일: 0") || strings.Contains(out.String(), "cmd/pricereviews") {
		t.Errorf("없을 때의 화면 = %s", out.String())
	}
}
