// billing-server/internal/pricing/import_test.go

// 여러 줄을 한꺼번에 넣는 것(Plan, Import)을 실제 DB 에서 시험한다.
package pricing_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// newCode 는 이 테스트만 쓰는 이름을 하나 더 짓는다.
func newCode() string {
	return "test." + uuid.NewString()
}

// historyOf 는 그 이름의 줄 수를 센다.
func (f fixture) historyOf(code string) int {
	f.t.Helper()
	versions, err := f.service.History(ctx(f.t), code)
	if err != nil {
		f.t.Fatalf("이력을 읽지 못했다: %v", err)
	}
	return len(versions)
}

func TestPlanShowsEachChangeAndWritesNothing(t *testing.T) {
	f := setUp(t)
	raised, lowered, same, stopped, fresh := f.code, newCode(), newCode(), newCode(), newCode()
	for code, credits := range map[string]int64{raised: 120, lowered: 120, same: 120, stopped: 120} {
		change := f.change(0)
		change.Code, change.Credits = code, credit.Amount(credits)
		f.set(change)
	}
	later := startedAt.Add(24 * time.Hour)
	entries := []pricing.Entry{
		{Code: raised, Credits: 240, EffectiveAt: later},
		{Code: lowered, Credits: 90},
		{Code: same, Credits: 120},
		{Code: stopped, Stop: true},
		{Code: fresh, Credits: 70},
	}

	planned, err := f.service.Plan(ctx(t), entries, "모델별 가격", "test")

	if err != nil || len(planned) != len(entries) {
		t.Fatalf("계산 = %+v, %v", planned, err)
	}
	want := []pricing.Effect{pricing.EffectRaise, pricing.EffectLower, pricing.EffectSame, pricing.EffectStop, pricing.EffectNew}
	for i, line := range planned {
		if line.Effect != want[i] {
			t.Errorf("%d: 바뀜 = %s, 기대 %s", i, line.Effect, want[i])
		}
	}
	if !planned[0].EffectiveAt.Equal(later) || planned[0].Before == nil || planned[0].Before.Credits != 120 {
		t.Errorf("올림 줄 = %+v", planned[0])
	}
	if !planned[1].EffectiveAt.Equal(startedAt) || planned[4].Before != nil {
		t.Errorf("시각을 비운 줄은 지금이고, 새 이름은 바뀌기 전 값이 없어야 한다: %+v / %+v", planned[1], planned[4])
	}
	for _, code := range []string{raised, lowered, same, stopped} {
		if n := f.historyOf(code); n != 1 {
			t.Errorf("%s: 줄 %d 개. 미리 보기는 아무것도 넣지 않아야 한다", code, n)
		}
	}
	if n := f.historyOf(fresh); n != 0 {
		t.Errorf("새 이름의 줄 %d 개. 미리 보기는 아무것도 넣지 않아야 한다", n)
	}
}

func TestImportAddsTheChangesAndSkipsTheSameOnes(t *testing.T) {
	f := setUp(t)
	f.set(f.change(120))
	fresh := newCode()
	entries := []pricing.Entry{{Code: f.code, Credits: 120}, {Code: fresh, Credits: 70}}

	planned, err := f.service.Import(ctx(t), entries, "모델별 가격", "test")

	if err != nil || len(planned) != 2 || planned[0].Effect != pricing.EffectSame || planned[1].Effect != pricing.EffectNew {
		t.Fatalf("넣기 = %+v, %v", planned, err)
	}
	if n := f.historyOf(f.code); n != 1 {
		t.Errorf("값이 같은 이름의 줄 %d 개. 같은 줄은 넣지 않아야 한다", n)
	}
	versions, err := f.service.History(ctx(t), fresh)
	if err != nil || len(versions) != 1 || versions[0].Credits != 70 || versions[0].Reason != "모델별 가격" || versions[0].ChangedBy != "test" {
		t.Errorf("새 이름의 줄 = %+v, %v", versions, err)
	}
}

func TestImportWritesNothingWhenAnyLineIsWrong(t *testing.T) {
	cases := map[string]func(f fixture, first string) []pricing.Entry{
		"값이 0": func(_ fixture, first string) []pricing.Entry {
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: newCode(), Credits: 0}}
		},
		"이름의 모양": func(_ fixture, first string) []pricing.Entry {
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: "Narration.X", Credits: 10}}
		},
		"지난 시각": func(_ fixture, first string) []pricing.Entry {
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: newCode(), Credits: 10, EffectiveAt: startedAt.Add(-time.Hour)}}
		},
		"같은 이름이 둘": func(_ fixture, first string) []pricing.Entry {
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: first, Credits: 200}}
		},
		"판 적 없는 이름의 판매 중지": func(_ fixture, first string) []pricing.Entry {
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: newCode(), Stop: true}}
		},
		// 계산은 통과하고 넣다가 걸리는 경우다. 앞 줄은 이미 넣었지만 트랜잭션이 함께 되돌린다
		"같은 적용 시각의 줄이 이미 있다": func(f fixture, first string) []pricing.Entry {
			taken := newCode()
			later := startedAt.Add(time.Hour)
			change := f.change(50)
			change.Code, change.EffectiveAt = taken, later
			f.set(change)
			return []pricing.Entry{{Code: first, Credits: 100}, {Code: taken, Credits: 60, EffectiveAt: later}}
		},
	}
	for name, build := range cases {
		t.Run(name, func(t *testing.T) {
			f := setUp(t)
			entries := build(f, f.code)

			_, err := f.service.Import(ctx(t), entries, "r", "test")

			if err == nil || !strings.Contains(err.Error(), "2번째 줄") {
				t.Fatalf("오류 = %v. 틀린 줄의 번호를 알려야 한다", err)
			}
			if n := f.historyOf(f.code); n != 0 {
				t.Errorf("첫 줄이 %d 개 들어갔다. 하나라도 틀리면 아무것도 넣지 않아야 한다", n)
			}
		})
	}
}

func TestImportReportsTheUnderlyingErrors(t *testing.T) {
	f := setUp(t)
	cases := map[error][]pricing.Entry{
		pricing.ErrNoEntries:      nil,
		pricing.ErrDuplicateEntry: {{Code: f.code, Credits: 1}, {Code: f.code, Credits: 2}},
		pricing.ErrInvalidCredits: {{Code: f.code, Credits: pricing.MaxCredits + 1}},
		pricing.ErrUnknownCode:    {{Code: f.code, Stop: true}},
	}
	for want, entries := range cases {
		if _, err := f.service.Import(ctx(t), entries, "r", "test"); !errors.Is(err, want) {
			t.Errorf("오류 = %v, 기대 %v", err, want)
		}
	}
	if _, err := f.service.Import(ctx(t), []pricing.Entry{{Code: f.code, Credits: 1}}, "", "test"); !errors.Is(err, pricing.ErrMissingNote) {
		t.Errorf("이유가 없을 때 = %v", err)
	}
}
