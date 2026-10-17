// billing-server/internal/pricereview/schedule_internal_test.go

// 할 일의 날짜 세기를 DB 없이 시험한다.
package pricereview

import (
	"slices"
	"testing"
	"time"
)

// changesAt 은 시험에서 공급사가 값을 바꾸는 시각이다(한국 시각 2026-11-21 0시).
var changesAt = time.Date(2026, 11, 21, 0, 0, 0, 0, time.FixedZone("KST", 9*60*60))

// review 는 done 을 끝낸 할 일 하나를 만든다.
func review(done ...Step) Review {
	r := Review{ID: 7, Subject: "GPT-5.6 Sol", ChangesAt: changesAt, Done: map[Step]Mark{}}
	for _, step := range done {
		r.Done[step] = Mark{MarkedBy: "ops"}
	}
	return r
}

// stepsOf 는 때가 된 할 일들의 이름이다.
func stepsOf(due []Due) []Step {
	steps := make([]Step, len(due))
	for i, d := range due {
		steps[i] = d.Step
	}
	return steps
}

func TestEachStepStartsOnItsDay(t *testing.T) {
	cases := map[string]struct {
		now  time.Time
		want []Step
	}{
		"31일 전":        {changesAt.Add(-31 * day), nil},
		"30일 전에서 1초 전": {changesAt.Add(-30*day - time.Second), nil},
		"30일 전":        {changesAt.Add(-30 * day), []Step{StepAnnounce}},
		"14일 전":        {changesAt.Add(-14 * day), []Step{StepAnnounce, StepNotice}},
		"하루 전":         {changesAt.Add(-day), []Step{StepAnnounce, StepNotice, StepFinal}},
		"지난 뒤":         {changesAt.Add(3 * day), []Step{StepAnnounce, StepNotice, StepFinal}},
	}
	for name, tc := range cases {
		if got := stepsOf(dueSteps([]Review{review()}, tc.now)); !slices.Equal(got, tc.want) {
			t.Errorf("%s: 때가 된 할 일 = %v, 기대 = %v", name, got, tc.want)
		}
	}
}

func TestFinishedStepsAreNotDue(t *testing.T) {
	now := changesAt.Add(-day)
	got := stepsOf(dueSteps([]Review{review(StepAnnounce, StepFinal)}, now))
	if !slices.Equal(got, []Step{StepNotice}) {
		t.Errorf("때가 된 할 일 = %v. 끝내지 않은 notice 만 남아야 한다", got)
	}
}

func TestACancelledReviewHasNothingDue(t *testing.T) {
	r := review(StepAnnounce)
	r.Cancelled = &Mark{Note: "공급사가 인상을 거둬들임", MarkedBy: "ops"}
	if due := dueSteps([]Review{r}, changesAt.Add(day)); len(due) != 0 {
		t.Errorf("닫은 할 일에서 경고가 나왔다: %+v", due)
	}
	if r.Open() || len(r.Remaining()) != 0 {
		t.Errorf("닫은 할 일이 열려 있다: 열림 = %v, 남은 것 = %v", r.Open(), r.Remaining())
	}
}

func TestAReviewClosesWhenEveryStepIsDone(t *testing.T) {
	if !review(StepAnnounce, StepNotice).Open() {
		t.Error("final 이 남았는데 닫혔다")
	}
	if review(StepAnnounce, StepNotice, StepFinal).Open() {
		t.Error("셋을 다 끝냈는데 열려 있다")
	}
}

func TestDueCarriesTheStageAndTheDaysLeft(t *testing.T) {
	cases := map[string]struct {
		now   time.Time
		stage Stage
		days  int
	}{
		"딱 30일 전":      {changesAt.Add(-30 * day), StageD30, 30},
		"14일 하고 1시간 전": {changesAt.Add(-14*day - time.Hour), StageD30, 15},
		"딱 14일 전":      {changesAt.Add(-14 * day), StageD14, 14},
		"하루 하고 1초 전":   {changesAt.Add(-day - time.Second), StageD14, 2},
		"딱 하루 전":       {changesAt.Add(-day), StageD1, 1},
		"1시간 전":        {changesAt.Add(-time.Hour), StageD1, 1},
		"바뀌는 순간":       {changesAt, StageOverdue, 0},
		"23시간 지남":      {changesAt.Add(23 * time.Hour), StageOverdue, 0},
		"이틀 지남":        {changesAt.Add(2 * day), StageOverdue, -2},
	}
	for name, tc := range cases {
		due := dueSteps([]Review{review()}, tc.now)
		if len(due) == 0 {
			t.Fatalf("%s: 때가 된 할 일이 없다", name)
		}
		first := due[0]
		if first.Stage != tc.stage || first.DaysLeft != tc.days {
			t.Errorf("%s: 구간 = %s, 남은 날 = %d. 기대 = %s, %d", name, first.Stage, first.DaysLeft, tc.stage, tc.days)
		}
		if first.ReviewID != 7 || first.Subject != "GPT-5.6 Sol" || !first.ChangesAt.Equal(changesAt) {
			t.Errorf("%s: 할 일의 정보가 빠졌다: %+v", name, first)
		}
	}
}

func TestDueTellsWhenEachStepStarted(t *testing.T) {
	due := dueSteps([]Review{review()}, changesAt)
	want := map[Step]time.Time{
		StepAnnounce: changesAt.Add(-30 * day),
		StepNotice:   changesAt.Add(-14 * day),
		StepFinal:    changesAt.Add(-day),
	}
	if len(due) != len(want) {
		t.Fatalf("때가 된 할 일 = %d 개, 기대 = %d", len(due), len(want))
	}
	for _, d := range due {
		if !d.StartsAt.Equal(want[d.Step]) {
			t.Errorf("%s 의 시작 = %s, 기대 = %s", d.Step, d.StartsAt, want[d.Step])
		}
	}
}

func TestDueKeepsTheOrderOfReviews(t *testing.T) {
	early, late := review(), review()
	early.ID, late.ID = 1, 2
	late.ChangesAt = changesAt.Add(10 * day)
	due := dueSteps([]Review{early, late}, changesAt.Add(-day))
	if len(due) == 0 || due[0].ReviewID != 1 || due[len(due)-1].ReviewID != 2 {
		t.Errorf("할 일의 차례가 바뀌었다: %+v", due)
	}
}

func TestOnlyTheThreeStepsAreKnown(t *testing.T) {
	for _, step := range []Step{StepAnnounce, StepNotice, StepFinal} {
		if !knownStep(step) {
			t.Errorf("%s 를 모른다", step)
		}
	}
	for _, step := range []Step{"cancel", "", "Announce"} {
		if knownStep(step) {
			t.Errorf("%q 를 할 일로 받았다", step)
		}
	}
}
