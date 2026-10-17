// billing-server/cmd/prices/main_test.go

package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// fakePrices 는 받은 일을 적어 두고 정해 둔 줄로 답하는 가짜 가격표다.
type fakePrices struct {
	action string
	code   string
	change pricing.Change
	answer []pricing.Version
	err    error
	// entries, reason, by 는 Plan·Import 가 받은 것이고, planned 는 그 둘이 돌려줄 줄들이다.
	entries []pricing.Entry
	reason  string
	by      string
	planned []pricing.Planned
}

func (f *fakePrices) Current(context.Context) ([]pricing.Version, error) {
	f.action = "list"
	return f.answer, f.err
}

func (f *fakePrices) History(_ context.Context, code string) ([]pricing.Version, error) {
	f.action, f.code = "history", code
	return f.answer, f.err
}

func (f *fakePrices) Set(_ context.Context, change pricing.Change) (pricing.Version, error) {
	f.action, f.change = "set", change
	return f.first(), f.err
}

func (f *fakePrices) Stop(_ context.Context, change pricing.Change) (pricing.Version, error) {
	f.action, f.change = "stop", change
	return f.first(), f.err
}

func (f *fakePrices) Plan(_ context.Context, entries []pricing.Entry, reason string, by string) ([]pricing.Planned, error) {
	f.action, f.entries, f.reason, f.by = "plan", entries, reason, by
	return f.planned, f.err
}

func (f *fakePrices) Import(_ context.Context, entries []pricing.Entry, reason string, by string) ([]pricing.Planned, error) {
	f.action, f.entries, f.reason, f.by = "import", entries, reason, by
	return f.planned, f.err
}

func (f *fakePrices) first() pricing.Version {
	if len(f.answer) == 0 {
		return pricing.Version{}
	}
	return f.answer[0]
}

func TestParseReadsEachCommand(t *testing.T) {
	at := time.Date(2026, 11, 1, 0, 0, 0, 0, time.FixedZone("", 9*60*60))
	cases := map[string]struct {
		args []string
		want request
	}{
		"list":       {[]string{"list"}, request{action: "list", by: "cli:me"}},
		"history":    {[]string{"history", "narration.standard"}, request{action: "history", code: "narration.standard", by: "cli:me"}},
		"set, 옵션이 뒤": {[]string{"set", "narration.x", "120", "-reason", "새 모델"}, request{action: "set", code: "narration.x", credits: 120, reason: "새 모델", by: "cli:me"}},
		"set, 옵션이 앞": {[]string{"-reason", "새 모델", "-by", "ops", "set", "narration.x", "120"}, request{action: "set", code: "narration.x", credits: 120, reason: "새 모델", by: "ops"}},
		"set, 적용 시각": {[]string{"set", "narration.x", "120", "-at", "2026-11-01T00:00:00+09:00", "-reason", "r"}, request{action: "set", code: "narration.x", credits: 120, at: at, reason: "r", by: "cli:me"}},
		"stop":       {[]string{"stop", "narration.x", "-reason", "모델을 내림"}, request{action: "stop", code: "narration.x", reason: "모델을 내림", by: "cli:me"}},
	}
	for name, args := range map[string][]string{
		"import, 미리 보기": {"import", "prices.csv", "-reason", "모델별 가격"},
		"import, 넣기":    {"-apply", "import", "prices.csv", "-reason", "모델별 가격"},
	} {
		got, err := parse(args, "cli:me")
		if err != nil || got.action != "import" || got.file != "prices.csv" || got.reason != "모델별 가격" || got.apply != (name == "import, 넣기") {
			t.Errorf("%s: 요청 = %+v, %v", name, got, err)
		}
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			got, err := parse(tc.args, "cli:me")
			if err != nil || got.action != tc.want.action || got.code != tc.want.code || got.credits != tc.want.credits ||
				got.reason != tc.want.reason || got.by != tc.want.by || !got.at.Equal(tc.want.at) {
				t.Errorf("요청 = %+v, %v\n기대 = %+v", got, err, tc.want)
			}
		})
	}
}

func TestParseRejectsWrongCommands(t *testing.T) {
	cases := [][]string{
		nil,
		{"remove", "narration.x"},
		{"history"},
		{"set", "narration.x", "-reason", "r"},
		{"set", "narration.x", "12.5", "-reason", "r"},
		{"set", "narration.x", "many", "-reason", "r"},
		{"set", "narration.x", "120"},
		{"stop", "narration.x"},
		{"set", "narration.x", "120", "-reason", "r", "-at", "내일"},
		{"list", "-unknown"},
		{"import", "prices.csv"},
		{"import", "-reason", "r"},
		{"import", "prices.csv", "-reason", "r", "-at", "2026-11-01T00:00:00+09:00"},
		{"set", "narration.x", "120", "-reason", "r", "-apply"},
		{"list", "-apply"},
	}
	for _, args := range cases {
		if _, err := parse(args, "cli:me"); err == nil {
			t.Errorf("%v: 오류가 나야 한다", args)
		}
	}
}

func TestDoPassesTheChangeAndPrintsTheLine(t *testing.T) {
	answer := pricing.Version{Code: "narration.x", Credits: 120, OnSale: true, EffectiveAt: time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC),
		Reason: "새 모델", ChangedBy: "ops"}
	fake := &fakePrices{answer: []pricing.Version{answer}}
	var out bytes.Buffer
	req := request{action: "set", code: "narration.x", credits: 120, reason: "새 모델", by: "ops"}

	err := do(context.Background(), fake, req, &out)

	want := pricing.Change{Code: "narration.x", Credits: 120, Reason: "새 모델", ChangedBy: "ops"}
	if err != nil || fake.action != "set" || fake.change != want {
		t.Fatalf("오류 = %v, 넘긴 것 = %s %+v", err, fake.action, fake.change)
	}
	if !strings.Contains(out.String(), "narration.x  120 크레딧") || !strings.Contains(out.String(), "(새 모델, ops)") {
		t.Errorf("화면 = %q", out.String())
	}
}

func TestDoShowsAStoppedLineAndPassesErrors(t *testing.T) {
	var out bytes.Buffer
	stopped := &fakePrices{answer: []pricing.Version{{Code: "narration.x", OnSale: false}}}
	if err := do(context.Background(), stopped, request{action: "list"}, &out); err != nil || !strings.Contains(out.String(), "판매 중지") {
		t.Errorf("오류 = %v, 화면 = %q", err, out.String())
	}

	out.Reset()
	failing := &fakePrices{err: pricing.ErrSameMoment}
	err := do(context.Background(), failing, request{action: "stop", code: "narration.x", reason: "r", by: "b"}, &out)
	if !errors.Is(err, pricing.ErrSameMoment) || out.Len() != 0 {
		t.Errorf("오류 = %v, 화면 = %q. 오류를 돌려주고 아무것도 찍지 않아야 한다", err, out.String())
	}

	out.Reset()
	if err := do(context.Background(), &fakePrices{}, request{action: "history", code: "narration.none"}, &out); err != nil || !strings.Contains(out.String(), "줄이 없습니다") {
		t.Errorf("오류 = %v, 화면 = %q", err, out.String())
	}
}

func TestParseEntriesReadsValuesStopsAndTimes(t *testing.T) {
	text := "code,credits,effective_at\n" +
		"# 새 모델\n" +
		"narration.a.i0.o0,120,\n" +
		"narration.b.i0.o0, 240 ,2026-12-01T00:00:00+09:00\n" +
		"narration.c.i0.o0,stop,\n"

	entries, err := parseEntries(strings.NewReader(text))

	at := time.Date(2026, 12, 1, 0, 0, 0, 0, time.FixedZone("", 9*60*60))
	want := []pricing.Entry{
		{Code: "narration.a.i0.o0", Credits: 120},
		{Code: "narration.b.i0.o0", Credits: 240, EffectiveAt: at},
		{Code: "narration.c.i0.o0", Stop: true},
	}
	if err != nil || len(entries) != len(want) {
		t.Fatalf("줄 = %+v, %v", entries, err)
	}
	for i := range want {
		if entries[i].Code != want[i].Code || entries[i].Credits != want[i].Credits || entries[i].Stop != want[i].Stop ||
			!entries[i].EffectiveAt.Equal(want[i].EffectiveAt) {
			t.Errorf("%d: %+v, 기대 %+v", i, entries[i], want[i])
		}
	}
}

func TestParseEntriesRefusesBrokenFiles(t *testing.T) {
	cases := map[string]string{
		"빈 파일":      "",
		"머리줄이 없다":   "narration.a.i0.o0,120,\n",
		"머리줄이 다르다":  "code,amount,at\nnarration.a.i0.o0,120,\n",
		"칸이 모자라다":   "code,credits,effective_at\nnarration.a.i0.o0,120\n",
		"값이 정수가 아님": "code,credits,effective_at\nnarration.a.i0.o0,12.5,\n",
		"시각의 모양":    "code,credits,effective_at\nnarration.a.i0.o0,120,내일\n",
	}
	for name, text := range cases {
		if _, err := parseEntries(strings.NewReader(text)); err == nil {
			t.Errorf("%s: 오류가 나야 한다", name)
		}
	}
	_, err := parseEntries(strings.NewReader("code,credits,effective_at\nnarration.a.i0.o0,120,\nnarration.b.i0.o0,x,\n"))
	if err == nil || !strings.Contains(err.Error(), "2번째 줄(narration.b.i0.o0)") {
		t.Errorf("오류 = %v. 틀린 줄의 번호와 이름을 알려야 한다", err)
	}
}

func TestImportPreviewsUnlessApplied(t *testing.T) {
	at := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	planned := []pricing.Planned{
		{Entry: pricing.Entry{Code: "narration.a.i0.o0", Credits: 120}, EffectiveAt: at, Effect: pricing.EffectNew},
		{Entry: pricing.Entry{Code: "narration.b.i0.o0", Credits: 240}, EffectiveAt: at,
			Before: &pricing.Price{Credits: 120}, Effect: pricing.EffectRaise},
		{Entry: pricing.Entry{Code: "narration.c.i0.o0", Stop: true}, EffectiveAt: at, Before: &pricing.Price{Credits: 30}, Effect: pricing.EffectStop},
	}
	entries := []pricing.Entry{{Code: "narration.a.i0.o0", Credits: 120}}
	req := request{action: "import", entries: entries, reason: "모델별 가격", by: "ops"}

	preview := &fakePrices{planned: planned}
	var out bytes.Buffer
	err := do(context.Background(), preview, req, &out)
	text := out.String()
	if err != nil || preview.action != "plan" || preview.reason != "모델별 가격" || preview.by != "ops" || len(preview.entries) != 1 {
		t.Fatalf("오류 = %v, 넘긴 것 = %s %q %q %v", err, preview.action, preview.reason, preview.by, preview.entries)
	}
	for _, want := range []string{"narration.a.i0.o0  새로  - → 120", "narration.b.i0.o0  올림  120 → 240", "narration.c.i0.o0  멈춤  30 → 판매 중지",
		"새로 1, 올림 1, 내림 0, 멈춤 1, 같음(넣지 않음) 0", "미리 보기만 했습니다"} {
		if !strings.Contains(text, want) {
			t.Errorf("화면에 %q 가 없다:\n%s", want, text)
		}
	}

	req.apply = true
	applied := &fakePrices{planned: planned}
	out.Reset()
	if err := do(context.Background(), applied, req, &out); err != nil || applied.action != "import" || !strings.Contains(out.String(), "넣었습니다") {
		t.Errorf("오류 = %v, 일 = %s, 화면 = %q", err, applied.action, out.String())
	}

	failing := &fakePrices{err: pricing.ErrDuplicateEntry}
	out.Reset()
	if err := do(context.Background(), failing, req, &out); !errors.Is(err, pricing.ErrDuplicateEntry) || out.Len() != 0 {
		t.Errorf("오류 = %v, 화면 = %q. 오류를 돌려주고 아무것도 찍지 않아야 한다", err, out.String())
	}
}
