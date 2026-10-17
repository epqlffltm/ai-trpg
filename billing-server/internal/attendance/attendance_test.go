// billing-server/internal/attendance/attendance_test.go

package attendance

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

func day(month time.Month, d int) time.Time {
	return time.Date(2026, month, d, 0, 0, 0, 0, time.UTC)
}

func TestTheFirstAttendanceIsDayOne(t *testing.T) {
	if got := CycleDayOn(nil, day(10, 18), 7); got != 1 {
		t.Fatalf("처음이면 1일째여야 하는데 %d 다", got)
	}
}

func TestAttendingTheNextDayContinuesTheCycle(t *testing.T) {
	last := &Last{Day: day(10, 17), CycleDay: 3}
	if got := CycleDayOn(last, day(10, 18), 7); got != 4 {
		t.Fatalf("어제가 3일째면 오늘은 4일째여야 하는데 %d 다", got)
	}
}

func TestTheCycleContinuesAcrossTheMonth(t *testing.T) {
	last := &Last{Day: day(10, 31), CycleDay: 2}
	if got := CycleDayOn(last, day(11, 1), 7); got != 3 {
		t.Fatalf("10월 31일 다음은 11월 1일이다. 3일째여야 하는데 %d 다", got)
	}
}

func TestMissingADayStartsOver(t *testing.T) {
	last := &Last{Day: day(10, 16), CycleDay: 5}
	if got := CycleDayOn(last, day(10, 18), 7); got != 1 {
		t.Fatalf("하루 빠지면 1일째여야 하는데 %d 다", got)
	}
}

func TestTheDayAfterTheLastDayIsDayOne(t *testing.T) {
	last := &Last{Day: day(10, 17), CycleDay: 7}
	if got := CycleDayOn(last, day(10, 18), 7); got != 1 {
		t.Fatalf("7일째 다음은 1일째여야 하는데 %d 다", got)
	}
}

func TestAShorterCycleStartsOver(t *testing.T) {
	// 주기를 7일에서 5일로 줄였다. 어제가 6일째였다
	last := &Last{Day: day(10, 17), CycleDay: 6}
	if got := CycleDayOn(last, day(10, 18), 5); got != 1 {
		t.Fatalf("어제가 새 주기의 길이를 넘었으면 1일째여야 하는데 %d 다", got)
	}
}

func TestTheDefaultScheduleGrowsByOneGame(t *testing.T) {
	schedule := DefaultSchedule()
	want := []credit.Amount{140, 160, 180, 200, 220, 240, 260}
	if len(schedule) != len(want) {
		t.Fatalf("7일이어야 하는데 %d 일이다", len(schedule))
	}
	for i := range want {
		if schedule.SilverOn(i+1) != want[i] {
			t.Fatalf("%d 일째는 %s 이어야 하는데 %s 다", i+1, want[i], schedule.SilverOn(i+1))
		}
	}
	if !schedule.OpensChest(7) || schedule.OpensChest(6) {
		t.Fatal("상자는 7일째에만 연다")
	}
	if err := schedule.Validate(); err != nil {
		t.Fatalf("기본값이 틀렸다: %v", err)
	}
}

func TestTheDefaultScheduleIsAFreshList(t *testing.T) {
	first := DefaultSchedule()
	first[0] = 1
	if DefaultSchedule()[0] != 140 {
		t.Fatal("받은 목록을 고쳐도 기본값은 그대로여야 한다")
	}
}

func TestABadScheduleIsRejected(t *testing.T) {
	long := make(Schedule, MaxCycleLength+1)
	for i := range long {
		long[i] = 1
	}
	cases := map[string]Schedule{
		"비었다":    {},
		"너무 길다":  long,
		"0 이 있다": {140, 0, 180},
		"너무 많다":  {MaxDailySilver + 1},
	}
	for name, schedule := range cases {
		if err := schedule.Validate(); !errors.Is(err, ErrInvalidSchedule) {
			t.Errorf("%s: ErrInvalidSchedule 이어야 하는데 %v 다", name, err)
		}
	}
	edge := make(Schedule, MaxCycleLength)
	for i := range edge {
		edge[i] = MaxDailySilver
	}
	if err := edge.Validate(); err != nil {
		t.Fatalf("가장 긴 주기와 가장 큰 양은 받아야 한다: %v", err)
	}
	if err := (Schedule{1}).Validate(); err != nil {
		t.Fatalf("1일, 1 실버는 받아야 한다: %v", err)
	}
}

func TestGrantKeysNameTheDay(t *testing.T) {
	if got := GrantKey(day(10, 18)); got != "attendance-20261018" {
		t.Fatalf("하루 양의 이름이 틀렸다: %s", got)
	}
	if got := ChestGrantKey(day(1, 2)); got != "chest-20260102" {
		t.Fatalf("상자의 이름이 틀렸다: %s", got)
	}
}

func TestTheFirstChestTableIsTheOneWeAnnounced(t *testing.T) {
	if err := ChestV1.Validate(); err != nil {
		t.Fatalf("v1 이 틀렸다: %v", err)
	}
	// 공개한 표(프로젝트 문서의 v1)와 같은지 본다. 바꾸려면 새 버전을 만든다
	want := map[string][2]int64{
		"mimic_bite": {0, 1000}, "mimic_teeth": {100, 2000}, "goblin_pouch": {300, 3000},
		"adventurer_pack": {600, 2200}, "treasure_hoard": {1500, 1500}, "dragon_hoard": {5000, 300},
	}
	if ChestV1.Version != "v1" || len(ChestV1.Outcomes) != len(want) {
		t.Fatalf("v1 의 모양이 틀렸다: %+v", ChestV1)
	}
	for _, outcome := range ChestV1.Outcomes {
		w, ok := want[outcome.ID]
		if !ok || int64(outcome.Silver) != w[0] || int64(outcome.Chance) != w[1] {
			t.Errorf("%s 이 공개한 값과 다르다: %+v", outcome.ID, outcome)
		}
	}
	if got := ChestV1.ExpectedSilver(); got != 617 {
		t.Fatalf("평균은 617 실버여야 하는데 %s 다", got)
	}
}

func TestPickFollowsTheIntervals(t *testing.T) {
	// 구간: 꽝 [0,1000) 이빨 [1000,3000) 고블린 [3000,6000) 배낭 [6000,8200) 더미 [8200,9700) 용 [9700,10000)
	cases := map[int]string{
		0: "mimic_bite", 999: "mimic_bite", 1000: "mimic_teeth", 2999: "mimic_teeth",
		3000: "goblin_pouch", 5999: "goblin_pouch", 6000: "adventurer_pack", 8199: "adventurer_pack",
		8200: "treasure_hoard", 9699: "treasure_hoard", 9700: "dragon_hoard", 9999: "dragon_hoard",
	}
	for n, want := range cases {
		if got := ChestV1.Pick(n).ID; got != want {
			t.Errorf("%d 은 %s 이어야 하는데 %s 다", n, want, got)
		}
	}
}

func TestPickOutOfRangeGivesTheFirst(t *testing.T) {
	if got := ChestV1.Pick(ChanceScale).ID; got != "mimic_bite" {
		t.Fatalf("범위 밖이면 가장 앞의 것이어야 하는데 %s 다", got)
	}
}

func TestEveryNumberPicksWithTheAnnouncedChance(t *testing.T) {
	counts := map[string]int{}
	for n := 0; n < ChanceScale; n++ {
		counts[ChestV1.Pick(n).ID]++
	}
	for _, outcome := range ChestV1.Outcomes {
		if counts[outcome.ID] != outcome.Chance {
			t.Errorf("%s 은 %d 개의 수를 차지해야 하는데 %d 개다", outcome.ID, outcome.Chance, counts[outcome.ID])
		}
	}
}

func TestABadChestTableIsRejected(t *testing.T) {
	cases := map[string]ChestTable{
		"버전이 없다":   {Outcomes: []Outcome{{ID: "a", Chance: ChanceScale}}},
		"결과가 없다":   {Version: "v9"},
		"이름이 겹친다":  {Version: "v9", Outcomes: []Outcome{{ID: "a", Chance: 5000}, {ID: "a", Chance: 5000}}},
		"이름이 비었다":  {Version: "v9", Outcomes: []Outcome{{Chance: ChanceScale}}},
		"확률이 0 이다": {Version: "v9", Outcomes: []Outcome{{ID: "a", Chance: ChanceScale}, {ID: "b"}}},
		"실버가 음수다":  {Version: "v9", Outcomes: []Outcome{{ID: "a", Chance: ChanceScale, Silver: -1}}},
		"합이 모자란다":  {Version: "v9", Outcomes: []Outcome{{ID: "a", Chance: ChanceScale - 1}}},
		"합이 넘친다":   {Version: "v9", Outcomes: []Outcome{{ID: "a", Chance: ChanceScale}, {ID: "b", Chance: 1}}},
	}
	for name, table := range cases {
		if err := table.Validate(); !errors.Is(err, ErrInvalidChest) {
			t.Errorf("%s: ErrInvalidChest 이어야 하는데 %v 다", name, err)
		}
	}
}

func TestCryptoRollStaysInRange(t *testing.T) {
	for range 1000 {
		n, err := CryptoRoll()
		if err != nil {
			t.Fatalf("난수를 고르지 못했다: %v", err)
		}
		if n < 0 || n >= ChanceScale {
			t.Fatalf("0 이상 %d 미만이어야 하는데 %d 다", ChanceScale, n)
		}
	}
}
