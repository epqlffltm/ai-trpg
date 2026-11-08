// billing-server/internal/httpapi/attendance_grant.go

package httpapi

import (
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 출석의 실버를 주는 주소. 인증 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/grants/attendance
//
// 출석은 인증 서버로 옮긴다(2026-11-08 결정). 누가 언제 출석했는지, 주기의 며칠째인지, 하루 양과 보물 상자에서 나온 실버는
// 인증 서버가 정해 보낸다. 이 서버는 지갑에 넣기만 한다. 양을 받는 까닭이다(환영 크레딧, 초대 보상과 다르다).
// 이 서버가 지키는 것은 "한 사용자, 한 날짜에 하루 양 한 번, 상자 한 번"이다. 지급의 이름으로 지킨다.
// 이름은 이 서버의 출석(#339)과 같다(attendance-<날짜>, chest-<날짜>). 옮기는 동안 두 길로 같은 날을 두 번 받지 못한다.
// 하루 양과 상자는 따로 준다. 하나를 주다 실패해도 인증 서버가 같은 것을 다시 보내면 남은 것만 들어간다.
// 응답은 환영 크레딧과 같은 모양이다(welcomeBody). 이번에 새로 준 실버의 합이다.

// MaxAttendanceSilver 는 출석으로 한 번에 받는 하루 양과 상자의 실버 각각의 가장 큰 값이다. 0 을 몇 개 더 붙인 실수를 막는다.
const MaxAttendanceSilver credit.Amount = 100_000

// attendanceDayLayout 은 출석한 날(한국 날짜)의 모양이다.
const attendanceDayLayout = "2006-01-02"

// grantAttendanceRequest 는 출석의 실버를 달라는 요청의 본문이다. 양은 다른 양처럼 글자다.
type grantAttendanceRequest struct {
	// UserID 는 받을 사용자다. 인증 서버의 public_id 다.
	UserID uuid.UUID `json:"user_id"`
	// Day 는 출석한 날이다. 한국 날짜, YYYY-MM-DD 다. 지급의 이름에 들어간다.
	Day string `json:"day"`
	// Silver 는 그날의 하루 양이다. 1 부터다.
	Silver string `json:"silver"`
	// ChestSilver 는 그날 연 보물 상자에서 나온 실버다. 상자를 열지 않았거나 꽝이면 "0" 이다. 비워도 "0" 이다.
	ChestSilver string `json:"chest_silver"`
}

// attendanceGrant 는 읽어 낸 요청이다.
type attendanceGrant struct {
	user   uuid.UUID
	day    time.Time
	silver credit.Amount
	chest  credit.Amount
}

// readAttendanceGrant 는 요청의 본문을 읽고 값을 본다. 틀렸으면 그 까닭이다(빈 글자가 아니다).
func readAttendanceGrant(request grantAttendanceRequest) (attendanceGrant, string) {
	if request.UserID == uuid.Nil {
		return attendanceGrant{}, "user_id 가 있어야 합니다."
	}
	day, err := time.Parse(attendanceDayLayout, request.Day)
	if err != nil {
		return attendanceGrant{}, "day 는 YYYY-MM-DD 여야 합니다."
	}
	silver, err := credit.Parse(request.Silver)
	if err != nil || silver < 1 || silver > MaxAttendanceSilver {
		return attendanceGrant{}, "silver 는 1 에서 100000 사이의 실버(글자)여야 합니다."
	}
	chest := credit.Amount(0)
	if request.ChestSilver != "" {
		chest, err = credit.Parse(request.ChestSilver)
		if err != nil || chest < 0 || chest > MaxAttendanceSilver {
			return attendanceGrant{}, "chest_silver 는 0 에서 100000 사이의 실버(글자)여야 합니다."
		}
	}
	return attendanceGrant{user: request.UserID, day: day, silver: silver, chest: chest}, ""
}

// grantedPart 는 지급 하나를 한 결과다. 이미 받은 것이면 granted 가 거짓이다.
type grantedPart struct {
	granted bool
	grant   wallet.Grant
}

// grantOnce 는 그 이름의 실버를 한 번 준다. 이미 받았으면 오류가 아니다(granted 가 거짓).
func grantOnce(c *gin.Context, granter WelcomeGranter, user uuid.UUID, amount credit.Amount, key string) (grantedPart, error) {
	grant, err := granter.GrantFreeOnce(c.Request.Context(), user, amount, key)
	if errors.Is(err, wallet.ErrAlreadyGranted) {
		return grantedPart{}, nil
	}
	if err != nil {
		return grantedPart{}, err
	}
	return grantedPart{granted: true, grant: grant}, nil
}

// attendanceParts 는 하루 양과(꽝이 아니면) 상자의 실버를 차례로 준다. 하나라도 실패하면 오류다. 준 것은 그대로다.
func attendanceParts(c *gin.Context, granter WelcomeGranter, grant attendanceGrant) ([]grantedPart, error) {
	daily, err := grantOnce(c, granter, grant.user, grant.silver, attendance.GrantKey(grant.day))
	if err != nil || grant.chest == 0 {
		return []grantedPart{daily}, err
	}
	chest, err := grantOnce(c, granter, grant.user, grant.chest, attendance.ChestGrantKey(grant.day))
	return []grantedPart{daily, chest}, err
}

// attendanceBody 는 새로 준 것들을 응답의 모양으로 바꾼다. 하나도 새로 주지 않았으면 already_granted 다.
// 사라지는 시각은 새로 준 것 중 처음 것이다(하루 양과 상자는 같은 때에 사라진다).
func attendanceBody(parts []grantedPart) (int, welcomeBody) {
	body := welcomeBody{Status: welcomeAlreadyGranted}
	for _, part := range parts {
		if !part.granted {
			continue
		}
		body.Granted += part.grant.Amount
		if body.ExpiresAt == nil {
			expires := part.grant.ExpiresAt
			body.ExpiresAt = &expires
		}
	}
	if body.ExpiresAt == nil {
		return http.StatusOK, body
	}
	body.Status = welcomeGranted
	return http.StatusCreated, body
}

// grantAttendance 는 출석의 실버를 주는 핸들러를 만든다.
//   - 하나라도 새로 줬다 -> 201(granted). granted 는 새로 준 실버의 합이다
//   - 모두 이미 받았다 -> 200(already_granted). 인증 서버가 응답을 못 받아 다시 보낸 요청일 수 있다
//   - 본문이 틀렸다 -> 400
func grantAttendance(granter WelcomeGranter) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request grantAttendanceRequest
		if !readJSON(c, &request) {
			return
		}
		grant, problem := readAttendanceGrant(request)
		if problem != "" {
			badRequest(c, problem)
			return
		}
		parts, err := attendanceParts(c, granter, grant)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(attendanceBody(parts))
	}
}
