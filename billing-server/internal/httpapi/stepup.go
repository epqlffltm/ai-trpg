// billing-server/internal/httpapi/stepup.go

package httpapi

import (
	"context"
	"errors"
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/stepup"
)

// 민감한 작업(청약철회, 카드 등록·바꾸기·지우기) 앞의 본인 확인(F5). 묻는 것은 인증 서버다(internal/stepup).
//   - 창이 열려 있으면 작업을 한다. 인증 서버가 창을 늘렸다
//   - 창이 닫혔으면 403 step_up.required. 화면이 본인 확인 창을 띄우고, 확인한 뒤 같은 요청을 다시 보낸다
//   - 본인 확인을 끈 사람이면 카드 작업은 하고, 청약철회는 403 step_up.disabled 로 받지 않는다
//   - 인증 서버에 묻지 못하면 503. 같은 요청을 다시 보내면 된다
// 플레이, 충전, 지갑 보기 같은 보통의 작업에는 붙이지 않는다.

const (
	// codeStepUpRequired 는 본인 확인 창이 닫혀 있다는 것이다(403). 화면은 본인 확인을 받고 같은 요청을 다시 보낸다.
	codeStepUpRequired = "step_up.required"
	// codeStepUpDisabled 는 본인 확인을 끈 사람의 청약철회라는 것이다(403). 화면은 본인 확인을 다시 켜게 안내한다.
	codeStepUpDisabled = "step_up.disabled"
)

// StepUpGate 는 그 사용자의 그 세션이 지금 본인 확인 창 안인지 묻는 것의 모양이다. *stepup.HTTPChecker 가 이 모양이다.
type StepUpGate interface {
	Check(ctx context.Context, userID uuid.UUID, sessionID string) (stepup.State, error)
}

// stepUpPolicy 는 본인 확인을 끈 사람의 작업을 받을지다.
type stepUpPolicy int

const (
	// allowWhenDisabled 는 끈 사람이면 확인 없이 한다는 것이다(카드).
	allowWhenDisabled stepUpPolicy = iota
	// refuseWhenDisabled 는 끈 사람이면 받지 않는다는 것이다(청약철회).
	refuseWhenDisabled
)

// requireStepUp 은 민감한 작업 앞에 붙이는 미들웨어를 만든다. requireUser 뒤에 붙는다(토큰의 주인과 세션을 읽는다).
func requireStepUp(gate StepUpGate, policy stepUpPolicy, logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		claims := currentUser(c)
		state, err := gate.Check(c.Request.Context(), claims.UserID, claims.SessionID)
		if err != nil {
			stepUpUnavailable(c, logger, err)
			return
		}
		switch {
		case state == stepup.Open:
			c.Next()
		case state == stepup.Disabled && policy == allowWhenDisabled:
			c.Next()
		case state == stepup.Disabled:
			c.AbortWithStatusJSON(http.StatusForbidden, errorBody{
				Detail: "본인 확인을 끈 동안에는 청약철회를 할 수 없습니다. 회원정보에서 본인 확인을 켜 주세요.",
				Code:   codeStepUpDisabled,
			})
		default:
			c.AbortWithStatusJSON(http.StatusForbidden, errorBody{
				Detail: "본인 확인이 필요합니다. 메일로 받은 코드를 넣어 주세요.",
				Code:   codeStepUpRequired,
			})
		}
	}
}

// stepUpUnavailable 은 인증 서버에 묻지 못했을 때의 응답이다. 오류의 글에는 주소가 없다(stepup 이 종류만 싣는다).
func stepUpUnavailable(c *gin.Context, logger *slog.Logger, err error) {
	code := "step_up.unavailable"
	if !errors.Is(err, stepup.ErrUnavailable) {
		code = "step_up.check_failed"
	}
	logger.WarnContext(c.Request.Context(), "본인 확인 창을 묻지 못했습니다",
		slog.String(obs.FieldOperation, "step_up.check"),
		slog.String(obs.FieldErrorCode, code),
		slog.String(obs.FieldErrorMessage, err.Error()),
	)
	c.AbortWithStatusJSON(http.StatusServiceUnavailable, errorBody{
		Detail: "지금은 본인 확인을 할 수 없습니다. 잠시 후 다시 시도해 주세요.",
	})
}
