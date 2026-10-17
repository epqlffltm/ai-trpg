// billing-server/internal/httpapi/attendance.go

package httpapi

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 출석과 보물 상자의 주소들(#339).
//
//	GET  /attendance          오늘의 출석(로그인)
//	POST /attendance          오늘의 출석 보상을 받는다(로그인)
//	GET  /attendance/rewards  하루 양과 보물 상자의 확률(로그인 없음. 누구나 본다)
//
// 누구의 출석인지는 토큰에서만 정한다. 본문을 받지 않는다.

// dateLayout 은 응답의 날짜 모양이다. 한국 날짜다.
const dateLayout = "2006-01-02"

// rewardsCacheSeconds 는 확률을 공개하는 주소의 응답을 브라우저와 프록시가 기억해도 되는 시간이다.
// 표는 PR 로만 바뀐다. 바뀐 뒤 몇 분 옛것이 보여도 괜찮다
const rewardsCacheSeconds = 300

// AttendanceService 는 출석을 받고 읽는 것의 모양이다. *attendance.Service 가 이 모양이다.
type AttendanceService interface {
	Status(ctx context.Context, userID uuid.UUID) (attendance.Status, error)
	Claim(ctx context.Context, userID uuid.UUID) (attendance.Claim, error)
	Rewards() (attendance.Schedule, attendance.ChestTable)
}

// attendanceStatusBody 는 오늘의 출석의 응답 모양이다.
type attendanceStatusBody struct {
	// Today 는 오늘의 한국 날짜다(YYYY-MM-DD).
	Today string `json:"today"`
	// Verified 가 false 면 본인인증 전이다. 받을 수 없다.
	Verified bool `json:"verified"`
	// Claimed 는 오늘 이미 받았는지다.
	Claimed bool `json:"claimed"`
	// CycleDay 는 오늘이 주기의 며칠째인지, CycleLength 는 주기의 날 수다.
	CycleDay    int `json:"cycle_day"`
	CycleLength int `json:"cycle_length"`
	// Silver 는 오늘의 하루 양이다.
	Silver credit.Amount `json:"silver"`
	// Chest 는 오늘 보물 상자를 여는 날인지다.
	Chest bool `json:"chest"`
}

// chestBody 는 연 보물 상자의 응답 모양이다.
type chestBody struct {
	// Table 은 연 때의 확률표의 버전이다.
	Table   string        `json:"table"`
	Outcome string        `json:"outcome"`
	Name    string        `json:"name"`
	Silver  credit.Amount `json:"silver"`
}

// attendanceClaimBody 는 받은 출석 보상의 응답 모양이다.
type attendanceClaimBody struct {
	Day      string        `json:"day"`
	CycleDay int           `json:"cycle_day"`
	Silver   credit.Amount `json:"silver"`
	// Chest 는 연 보물 상자다. 연 날이 아니면 null 이다.
	Chest *chestBody `json:"chest"`
	// ExpiresAt 은 이번에 받은 실버가 사라지는 시각이다.
	ExpiresAt time.Time `json:"expires_at"`
}

// rewardDayBody 는 주기의 하루다.
type rewardDayBody struct {
	Day    int           `json:"day"`
	Silver credit.Amount `json:"silver"`
	Chest  bool          `json:"chest"`
}

// rewardOutcomeBody 는 보물 상자의 결과 하나와 그 확률이다.
type rewardOutcomeBody struct {
	Outcome string        `json:"outcome"`
	Name    string        `json:"name"`
	Silver  credit.Amount `json:"silver"`
	// Chance 는 만분율의 확률이다(1000 은 10%). Percent 는 같은 값을 사람이 읽는 글자로 쓴 것이다.
	Chance  int    `json:"chance"`
	Percent string `json:"percent"`
}

// rewardChestBody 는 보물 상자의 확률표다.
type rewardChestBody struct {
	Table string `json:"table"`
	// Scale 은 확률의 단위다(10000). 결과의 chance 를 모두 더하면 이 값이다.
	Scale    int                 `json:"scale"`
	Outcomes []rewardOutcomeBody `json:"outcomes"`
	// ExpectedSilver 는 상자 하나의 평균 실버다(내림).
	ExpectedSilver credit.Amount `json:"expected_silver"`
}

// rewardsBody 는 공개하는 보상표의 응답 모양이다.
type rewardsBody struct {
	Cycle []rewardDayBody `json:"cycle"`
	Chest rewardChestBody `json:"chest"`
}

// getAttendance 는 토큰의 주인의 오늘 출석을 돌려주는 핸들러를 만든다.
func getAttendance(service AttendanceService) gin.HandlerFunc {
	return func(c *gin.Context) {
		status, err := service.Status(c.Request.Context(), currentUser(c).UserID)
		if err != nil {
			internalError(c, err)
			return
		}
		schedule, _ := service.Rewards()
		c.JSON(http.StatusOK, toAttendanceStatusBody(status, schedule.Length()))
	}
}

// claimAttendance 는 토큰의 주인에게 오늘의 출석 보상을 주는 핸들러를 만든다.
//   - 줬다 -> 201
//   - 본인인증 전이다 -> 403 attendance.verification_required. 화면은 본인인증으로 보낸다
//   - 오늘 이미 받았다 -> 409 attendance.already_claimed
func claimAttendance(service AttendanceService) gin.HandlerFunc {
	return func(c *gin.Context) {
		claim, err := service.Claim(c.Request.Context(), currentUser(c).UserID)
		switch {
		case errors.Is(err, attendance.ErrVerificationRequired):
			abort(c, http.StatusForbidden, codeAttendanceVerificationRequired, err.Error()+".")
		case errors.Is(err, attendance.ErrAlreadyClaimed):
			abort(c, http.StatusConflict, codeAttendanceAlreadyClaimed, err.Error()+".")
		case err != nil:
			internalError(c, err)
		default:
			c.JSON(http.StatusCreated, toAttendanceClaimBody(claim))
		}
	}
}

// attendanceRewards 는 하루 양과 보물 상자의 확률을 돌려주는 핸들러를 만든다. 로그인 없이 누구나 본다.
func attendanceRewards(service AttendanceService) gin.HandlerFunc {
	return func(c *gin.Context) {
		schedule, chest := service.Rewards()
		c.Header("Cache-Control", fmt.Sprintf("public, max-age=%d", rewardsCacheSeconds))
		c.JSON(http.StatusOK, toRewardsBody(schedule, chest))
	}
}

// toAttendanceStatusBody 는 오늘의 출석을 응답의 모양으로 바꾼다.
func toAttendanceStatusBody(status attendance.Status, length int) attendanceStatusBody {
	return attendanceStatusBody{
		Today: status.Today.Format(dateLayout), Verified: status.Verified, Claimed: status.Claimed,
		CycleDay: status.CycleDay, CycleLength: length, Silver: status.Silver, Chest: status.Chest,
	}
}

// toAttendanceClaimBody 는 받은 출석 보상을 응답의 모양으로 바꾼다.
func toAttendanceClaimBody(claim attendance.Claim) attendanceClaimBody {
	body := attendanceClaimBody{
		Day: claim.Day.Format(dateLayout), CycleDay: claim.CycleDay, Silver: claim.Silver, ExpiresAt: claim.ExpiresAt,
	}
	if claim.Chest != nil {
		outcome := claim.Chest.Outcome
		body.Chest = &chestBody{Table: claim.Chest.Table, Outcome: outcome.ID, Name: outcome.Name, Silver: outcome.Silver}
	}
	return body
}

// toRewardsBody 는 하루 양과 확률표를 응답의 모양으로 바꾼다.
func toRewardsBody(schedule attendance.Schedule, chest attendance.ChestTable) rewardsBody {
	cycle := make([]rewardDayBody, schedule.Length())
	for i := range cycle {
		day := i + 1
		cycle[i] = rewardDayBody{Day: day, Silver: schedule.SilverOn(day), Chest: schedule.OpensChest(day)}
	}
	outcomes := make([]rewardOutcomeBody, len(chest.Outcomes))
	for i, outcome := range chest.Outcomes {
		outcomes[i] = rewardOutcomeBody{
			Outcome: outcome.ID, Name: outcome.Name, Silver: outcome.Silver,
			Chance: outcome.Chance, Percent: percentOf(outcome.Chance),
		}
	}
	return rewardsBody{Cycle: cycle, Chest: rewardChestBody{
		Table: chest.Version, Scale: attendance.ChanceScale, Outcomes: outcomes, ExpectedSilver: chest.ExpectedSilver(),
	}}
}

// percentOf 는 만분율을 백분율의 글자로 쓴다. 1000 은 "10%", 250 은 "2.5%", 1 은 "0.01%" 다. 끝의 0 은 쓰지 않는다.
func percentOf(chance int) string {
	whole, rest := chance/100, chance%100
	switch {
	case rest == 0:
		return fmt.Sprintf("%d%%", whole)
	case rest%10 == 0:
		return fmt.Sprintf("%d.%d%%", whole, rest/10)
	default:
		return fmt.Sprintf("%d.%02d%%", whole, rest)
	}
}
