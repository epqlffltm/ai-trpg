// billing-server/internal/attendance/attendance.go

// Package attendance 는 출석과 보물 상자다(#339). 사용자가 하루에 한 번 "출석"을 눌러 실버(무료 크레딧)를 받는다.
//
//   - 본인인증을 한 사용자만 받는다. 한 사람이 계정을 여럿 만들어 받는 것을 본인인증이 막는다(한 사람 = 한 계정)
//   - 날짜는 한국 날짜다. 자정(Asia/Seoul)에 바뀐다
//   - 주기는 하루 양의 목록(Schedule)의 길이다(기본 7일). 하루라도 빠지면 1일째부터 다시 센다
//   - 주기의 마지막 날에 보물 상자를 함께 연다(chest.go). 다음 날은 1일째다
//
// 이 파일은 규칙만 둔다. DB 를 보지 않는다. 적고 읽는 일은 store.go 가 한다.
package attendance

import (
	"errors"
	"fmt"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

var (
	// ErrVerificationRequired 는 본인인증을 하지 않아 출석 보상을 받을 수 없다는 오류다.
	ErrVerificationRequired = errors.New("출석 보상을 받으려면 먼저 본인인증을 해야 합니다")
	// ErrAlreadyClaimed 는 오늘 이미 받았다는 오류다. 이 오류가 나면 아무것도 바뀌지 않는다.
	ErrAlreadyClaimed = errors.New("오늘은 이미 출석 보상을 받았습니다. 내일 다시 오세요")
	// ErrInvalidSchedule 은 하루 양의 목록이 틀렸다는 오류다. 서버가 뜰 때 걸러진다.
	ErrInvalidSchedule = errors.New("출석의 하루 양이 틀렸습니다")
)

// MaxCycleLength 는 주기의 가장 긴 날 수다. 그보다 길면 마지막 날의 상자가 너무 멀다.
const MaxCycleLength = 14

// MaxDailySilver 는 하루 양으로 받는 가장 큰 실버다. 0 을 몇 개 더 붙인 실수를 막는다.
const MaxDailySilver credit.Amount = 100_000

// DefaultSchedule 은 하루 양의 기본값이다. 1판(20 실버)을 하루 7판에서 시작해 하루 1판씩 늘린다. 한 주에 1,400 실버다.
// 작게 시작해 천천히 올린다(사용자 결정). 부를 때마다 새 목록을 준다. 받은 쪽이 고쳐도 기본값은 그대로다.
func DefaultSchedule() Schedule {
	return Schedule{140, 160, 180, 200, 220, 240, 260}
}

// Schedule 은 주기의 날마다 받는 실버다. 첫째 값이 1일째다. 길이가 주기의 날 수다.
type Schedule []credit.Amount

// Validate 는 목록이 맞는지 본다. 1 일에서 MaxCycleLength 일까지, 날마다 1 에서 MaxDailySilver 실버까지다.
func (s Schedule) Validate() error {
	if len(s) == 0 || len(s) > MaxCycleLength {
		return fmt.Errorf("%w: 1 일에서 %d 일까지여야 합니다", ErrInvalidSchedule, MaxCycleLength)
	}
	for i, silver := range s {
		if silver < 1 || silver > MaxDailySilver {
			return fmt.Errorf("%w: %d 일째는 1 에서 %s 실버 사이여야 합니다", ErrInvalidSchedule, i+1, MaxDailySilver)
		}
	}
	return nil
}

// Length 는 주기의 날 수다.
func (s Schedule) Length() int { return len(s) }

// SilverOn 은 주기의 day 일째에 받는 실버다. day 는 1 부터 Length 까지다.
func (s Schedule) SilverOn(day int) credit.Amount { return s[day-1] }

// OpensChest 는 주기의 day 일째에 보물 상자를 여는지다. 마지막 날에 연다.
func (s Schedule) OpensChest(day int) bool { return day == s.Length() }

// Last 는 그 사용자가 가장 최근에 출석한 날과 그날이 주기의 며칠째였는지다.
type Last struct {
	// Day 는 한국 날짜다(0시 UTC 의 시각).
	Day      time.Time
	CycleDay int
}

// CycleDayOn 은 today 에 출석하면 주기의 며칠째인지 센다. last 는 가장 최근의 출석이다(없으면 nil).
//   - 어제 출석했고 주기가 아직 안 끝났다 -> 어제의 다음 날
//   - 그 밖(처음이다, 하루라도 빠졌다, 어제가 마지막 날이었다) -> 1일째
//
// 오늘 이미 출석했는지는 보지 않는다. 부르는 쪽이 먼저 본다.
// 주기를 줄였으면(설정) 어제가 새 주기의 길이를 넘어도 1일째다.
func CycleDayOn(last *Last, today time.Time, length int) int {
	if last == nil {
		return 1
	}
	if last.Day.Equal(today.AddDate(0, 0, -1)) && last.CycleDay < length {
		return last.CycleDay + 1
	}
	return 1
}

// GrantKey 는 그날의 하루 양에 붙이는 지급의 이름이다. 지갑이 한 사용자에게 같은 이름을 두 번 주지 않는다.
// 출석의 기본 키(사용자, 날짜)와 함께 같은 날 두 번 받는 것을 두 겹으로 막는다.
func GrantKey(day time.Time) string { return "attendance-" + day.Format("20060102") }

// ChestGrantKey 는 그날 연 상자의 실버에 붙이는 지급의 이름이다.
func ChestGrantKey(day time.Time) string { return "chest-" + day.Format("20060102") }

// ChestResult 는 연 보물 상자다.
type ChestResult struct {
	// Table 은 연 때의 확률표의 버전이다.
	Table   string
	Outcome Outcome
}

// Claim 은 받은 출석 보상이다.
type Claim struct {
	// Day 는 출석한 한국 날짜다(0시 UTC 의 시각).
	Day      time.Time
	CycleDay int
	Silver   credit.Amount
	// Chest 는 연 보물 상자다. 연 날이 아니면 nil 이다.
	Chest *ChestResult
	// ExpiresAt 은 이번에 받은 실버가 사라지는 시각이다.
	ExpiresAt time.Time
}

// Status 는 오늘의 출석이다. 화면이 단추를 그릴 때 쓴다.
type Status struct {
	// Today 는 오늘의 한국 날짜다(0시 UTC 의 시각).
	Today time.Time
	// Verified 는 본인인증을 했는지다. false 면 받을 수 없다. 화면은 본인인증으로 보낸다.
	Verified bool
	// Claimed 는 오늘 이미 받았는지다.
	Claimed bool
	// CycleDay 는 오늘이 주기의 며칠째인지다. 받았으면 받은 날의 값, 아직이면 지금 받으면 될 값이다.
	CycleDay int
	// Silver 는 오늘의 하루 양이다. 받았으면 받은 양이다.
	Silver credit.Amount
	// Chest 는 오늘 보물 상자를 여는 날인지다.
	Chest bool
}
