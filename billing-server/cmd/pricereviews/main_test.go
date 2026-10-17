// billing-server/cmd/pricereviews/main_test.go

package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview"
)

// fakeReviews 는 받은 일을 적어 두고 정해 둔 할 일로 답하는 가짜다.
type fakeReviews struct {
	action string
	draft  pricereview.Draft
	id     int64
	step   pricereview.Step
	by     string
	note   string
	all    bool
	answer []pricereview.Review
	err    error
}

func (f *fakeReviews) Add(_ context.Context, draft pricereview.Draft) (pricereview.Review, error) {
	f.action, f.draft = "add", draft
	return f.first(), f.err
}

func (f *fakeReviews) Done(_ context.Context, id int64, step pricereview.Step, by string, note string) (pricereview.Review, error) {
	f.action, f.id, f.step, f.by, f.note = "done", id, step, by, note
	return f.first(), f.err
}

func (f *fakeReviews) Cancel(_ context.Context, id int64, by string, reason string) (pricereview.Review, error) {
	f.action, f.id, f.by, f.note = "cancel", id, by, reason
	return f.first(), f.err
}

func (f *fakeReviews) List(_ context.Context, all bool) ([]pricereview.Review, error) {
	f.action, f.all = "list", all
	return f.answer, f.err
}

func (f *fakeReviews) first() pricereview.Review {
	if len(f.answer) == 0 {
		return pricereview.Review{}
	}
	return f.answer[0]
}

var kst = time.FixedZone("", 9*60*60)

func TestParseReadsEachCommand(t *testing.T) {
	at := time.Date(2026, 11, 21, 0, 0, 0, 0, kst)
	cases := map[string]struct {
		args []string
		want request
	}{
		"list":       {[]string{"list"}, request{action: "list", by: "cli:me"}},
		"list -all":  {[]string{"list", "-all"}, request{action: "list", all: true, by: "cli:me"}},
		"add, 옵션이 뒤": {[]string{"add", "GPT-5.6 Sol", "-at", "2026-11-21T00:00:00+09:00", "-note", "공지"}, request{action: "add", subject: "GPT-5.6 Sol", at: at, note: "공지", by: "cli:me"}},
		"add, 옵션이 앞": {[]string{"-by", "ops", "-at", "2026-11-21T00:00:00+09:00", "add", "GPT-5.6 Sol"}, request{action: "add", subject: "GPT-5.6 Sol", at: at, by: "ops"}},
		"done":       {[]string{"done", "3", "notice", "-note", "https://example.com/n"}, request{action: "done", id: 3, step: pricereview.StepNotice, note: "https://example.com/n", by: "cli:me"}},
		"cancel":     {[]string{"cancel", "3", "-note", "거둬들임"}, request{action: "cancel", id: 3, note: "거둬들임", by: "cli:me"}},
	}
	for name, tc := range cases {
		got, err := parse(tc.args, "cli:me")
		if err != nil {
			t.Errorf("%s: 오류 = %v", name, err)
			continue
		}
		if got.action != tc.want.action || got.id != tc.want.id || got.step != tc.want.step || got.subject != tc.want.subject ||
			!got.at.Equal(tc.want.at) || got.note != tc.want.note || got.by != tc.want.by || got.all != tc.want.all {
			t.Errorf("%s: 읽은 것 = %+v, 기대 = %+v", name, got, tc.want)
		}
	}
}

func TestParseRefusesWrongCommands(t *testing.T) {
	bads := map[string][]string{
		"빈 명령":             nil,
		"모르는 일":            {"remove", "3"},
		"add 에 시각이 없다":     {"add", "x"},
		"add 의 시각 모양":      {"add", "x", "-at", "2026-11-21"},
		"add 에 무엇이 없다":     {"add", "-at", "2026-11-21T00:00:00+09:00"},
		"done 의 번호가 숫자 아님": {"done", "three", "notice"},
		"done 의 번호가 0":     {"done", "0", "notice"},
		"done 에 할 일이 없다":   {"done", "3"},
		"cancel 에 이유가 없다":  {"cancel", "3"},
		"list 에 -at":       {"list", "-at", "2026-11-21T00:00:00+09:00"},
		"done 에 -at":       {"done", "3", "notice", "-at", "2026-11-21T00:00:00+09:00"},
		"list 에 -note":     {"list", "-note", "x"},
		"done 에 -all":      {"done", "3", "notice", "-all"},
		"모르는 옵션":           {"list", "-what"},
	}
	for name, args := range bads {
		if _, err := parse(args, "cli:me"); err == nil {
			t.Errorf("%s: 오류가 나야 한다", name)
		}
	}
}

func TestDoPassesTheRequestOn(t *testing.T) {
	at := time.Date(2026, 11, 21, 0, 0, 0, 0, kst)
	now := at.Add(-40 * 24 * time.Hour)
	cases := map[string]struct {
		req   request
		check func(*fakeReviews) bool
	}{
		"list": {request{action: "list", all: true}, func(f *fakeReviews) bool { return f.action == "list" && f.all }},
		"add": {request{action: "add", subject: "s", at: at, note: "n", by: "ops"}, func(f *fakeReviews) bool {
			return f.action == "add" && f.draft == pricereview.Draft{Subject: "s", ChangesAt: at, Note: "n", CreatedBy: "ops"}
		}},
		"done": {request{action: "done", id: 3, step: pricereview.StepFinal, note: "n", by: "ops"}, func(f *fakeReviews) bool {
			return f.action == "done" && f.id == 3 && f.step == pricereview.StepFinal && f.note == "n" && f.by == "ops"
		}},
		"cancel": {request{action: "cancel", id: 3, note: "이유", by: "ops"}, func(f *fakeReviews) bool {
			return f.action == "cancel" && f.id == 3 && f.note == "이유" && f.by == "ops"
		}},
	}
	for name, tc := range cases {
		fake := &fakeReviews{}
		var out bytes.Buffer
		if err := do(context.Background(), fake, tc.req, &out, now); err != nil {
			t.Errorf("%s: 오류 = %v", name, err)
		}
		if !tc.check(fake) {
			t.Errorf("%s: 넘긴 것 = %+v", name, fake)
		}
	}
}

func TestDoReturnsTheErrorWithoutPrinting(t *testing.T) {
	fake := &fakeReviews{err: pricereview.ErrClosed, answer: []pricereview.Review{{ID: 3, Subject: "s"}}}
	var out bytes.Buffer

	err := do(context.Background(), fake, request{action: "done", id: 3, step: pricereview.StepNotice}, &out, time.Now())

	if !errors.Is(err, pricereview.ErrClosed) || out.Len() != 0 {
		t.Errorf("오류 = %v, 화면 = %q", err, out.String())
	}
}

func TestPrintReviewShowsEachStep(t *testing.T) {
	changesAt := time.Date(2026, 11, 20, 15, 0, 0, 0, time.UTC)
	now := changesAt.Add(-20 * 24 * time.Hour)
	review := pricereview.Review{
		ID: 3, Subject: "GPT-5.6 Sol", ChangesAt: changesAt, Note: "https://example.com/pricing",
		Done: map[pricereview.Step]pricereview.Mark{
			pricereview.StepAnnounce: {MarkedBy: "ops", Note: "공지 1", MarkedAt: now},
		},
	}
	var out bytes.Buffer

	printReview(&out, review, now)

	text := out.String()
	for _, want := range []string{"#3  GPT-5.6 Sol", "(D-20)", "메모: https://example.com/pricing", "announce", "끝냄", "ops — 공지 1", "notice", "부터", "final"} {
		if !strings.Contains(text, want) {
			t.Errorf("화면에 %q 가 없다:\n%s", want, text)
		}
	}
	if strings.Contains(text, "할 때가 됨") || strings.Contains(text, "닫음") {
		t.Errorf("20일 전에 첫 공지를 끝냈으면 할 때가 된 것이 없다:\n%s", text)
	}

	out.Reset()
	review.Cancelled = &pricereview.Mark{MarkedBy: "ops", Note: "거둬들임", MarkedAt: now}
	printReview(&out, review, changesAt.Add(48*time.Hour))
	if text := out.String(); !strings.Contains(text, "바뀐 뒤 2일") || !strings.Contains(text, "닫음:") || !strings.Contains(text, "거둬들임") {
		t.Errorf("닫은 할 일의 화면:\n%s", text)
	}
}

func TestStepStateTellsWhenAStepIsDue(t *testing.T) {
	changesAt := time.Date(2026, 11, 20, 15, 0, 0, 0, time.UTC)
	review := pricereview.Review{ChangesAt: changesAt, Done: map[pricereview.Step]pricereview.Mark{}}
	if got := stepState(review, pricereview.StepNotice, changesAt.Add(-14*24*time.Hour)); !strings.HasPrefix(got, "할 때가 됨") {
		t.Errorf("14일 전의 notice = %q", got)
	}
	if got := stepState(review, pricereview.StepNotice, changesAt.Add(-15*24*time.Hour)); strings.HasPrefix(got, "할 때가 됨") {
		t.Errorf("15일 전의 notice = %q", got)
	}
}

func TestPrintReviewsSaysWhenThereIsNothing(t *testing.T) {
	var out bytes.Buffer
	if err := printReviews(&out, nil, time.Now(), nil); err != nil || !strings.Contains(out.String(), "남은 할 일이 없습니다") {
		t.Errorf("오류 = %v, 화면 = %q", err, out.String())
	}
}
