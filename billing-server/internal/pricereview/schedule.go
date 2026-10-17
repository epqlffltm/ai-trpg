// billing-server/internal/pricereview/schedule.go

package pricereview

import (
	"time"
)

// 할 일의 날짜를 센다. DB 를 보지 않는다. 받은 할 일과 시각만으로 답한다.

// day 는 하루다. 시간대를 따지지 않고 24시간으로 센다. 공급사가 값을 바꾸는 시각을 시간대까지 적어 받는다.
const day = 24 * time.Hour

// window 는 할 일 하나가 공급사가 값을 바꾸는 시각보다 얼마나 앞서 시작되는지다.
type window struct {
	step   Step
	before time.Duration
}

// schedule 은 할 일들과 그 시작이다. 차례대로다.
var schedule = []window{
	{StepAnnounce, 30 * day},
	{StepNotice, 14 * day},
	{StepFinal, 1 * day},
}

// Stage 는 공급사가 값을 바꾸기까지 얼마나 남았는지의 구간이다. 경고의 stage 칸에 적힌다.
type Stage string

const (
	// StageD30 은 30일에서 14일 남은 때다.
	StageD30 Stage = "d30"
	// StageD14 는 14일에서 하루 남은 때다.
	StageD14 Stage = "d14"
	// StageD1 은 하루 안이다.
	StageD1 Stage = "d1"
	// StageOverdue 는 공급사가 이미 값을 바꾼 뒤다. 남은 할 일은 늦었다.
	StageOverdue Stage = "overdue"
)

// Due 는 때가 되었는데 끝내지 않은 할 일 하나다.
type Due struct {
	ReviewID  int64
	Subject   string
	ChangesAt time.Time
	Step      Step
	// StartsAt 은 이 할 일을 시작할 때다(D-30, D-14, D-1).
	StartsAt time.Time
	Stage    Stage
	// DaysLeft 는 공급사가 값을 바꾸기까지 남은 날의 수다. 하루가 안 되게 남았으면 1 이고, 이미 지났으면 0 이하다.
	DaysLeft int
}

// StartOf 는 그 할 일을 시작할 때다. 모르는 할 일이면 두 번째 값이 false 다.
func StartOf(step Step, changesAt time.Time) (time.Time, bool) {
	for _, w := range schedule {
		if w.step == step {
			return changesAt.Add(-w.before), true
		}
	}
	return time.Time{}, false
}

// knownStep 은 announce, notice, final 가운데 하나인지다.
func knownStep(step Step) bool {
	_, ok := StartOf(step, time.Time{})
	return ok
}

// dueSteps 는 할 일들 가운데 now 에 때가 되었는데 끝내지 않은 것을 돌려준다. 받은 차례를 지킨다.
func dueSteps(reviews []Review, now time.Time) []Due {
	var due []Due
	for _, review := range reviews {
		due = append(due, dueOf(review, now)...)
	}
	return due
}

// dueOf 는 할 일 하나에서 때가 된 것들을 돌려준다.
func dueOf(review Review, now time.Time) []Due {
	var due []Due
	for _, step := range review.Remaining() {
		startsAt, _ := StartOf(step, review.ChangesAt)
		if now.Before(startsAt) {
			continue
		}
		due = append(due, Due{
			ReviewID:  review.ID,
			Subject:   review.Subject,
			ChangesAt: review.ChangesAt,
			Step:      step,
			StartsAt:  startsAt,
			Stage:     stageAt(review.ChangesAt, now),
			DaysLeft:  DaysUntil(review.ChangesAt, now),
		})
	}
	return due
}

// stageAt 은 now 가 공급사가 값을 바꾸기 전 어느 구간인지다.
func stageAt(changesAt time.Time, now time.Time) Stage {
	left := changesAt.Sub(now)
	switch {
	case left <= 0:
		return StageOverdue
	case left <= day:
		return StageD1
	case left <= 14*day:
		return StageD14
	default:
		return StageD30
	}
}

// DaysUntil 은 공급사가 값을 바꾸기까지 남은 날의 수다. 남은 것은 올려 센다(30일 하고 1시간이면 31).
// 지난 것은 다 찬 날만 센다. 막 지났으면 0, 하루 넘게 지났으면 -1 이다(정수 나눗셈은 0 쪽으로 자른다).
func DaysUntil(changesAt time.Time, now time.Time) int {
	left := changesAt.Sub(now)
	if left > 0 {
		return int((left + day - 1) / day)
	}
	return int(left / day)
}
