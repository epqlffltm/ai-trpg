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
