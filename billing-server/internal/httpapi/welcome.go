// billing-server/internal/httpapi/welcome.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 환영 크레딧을 주는 주소. 인증 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/grants/welcome
//
// 사용자가 휴대폰 본인인증을 마치면 인증 서버가 이 주소를 불러 무료 크레딧을 준다(#336. 그 전에는 이메일 인증 때).
// 누구에게 줄지는 인증 서버가 정한다. 한 사람이 계정을 여럿 만들어 여러 번 받는 것을 막는 일도 인증 서버가 한다.
// 이 서버가 지키는 것은 "한 사용자 번호에 한 번"이다.

// WelcomeGrantKey 는 환영 크레딧이라는 지급의 이름이다. 한 사용자는 이 이름의 지급을 한 번만 받는다.
const WelcomeGrantKey = "welcome"

// 환영 크레딧을 달라는 요청의 결과. 응답의 status 에 이 글자가 그대로 나간다.
const (
	// welcomeGranted 는 이번에 줬다는 뜻이다.
	welcomeGranted = "granted"
	// welcomeAlreadyGranted 는 이 사용자가 전에 이미 받았다는 뜻이다. 다 썼거나 사라진 뒤에도 같다.
	welcomeAlreadyGranted = "already_granted"
	// welcomeDisabled 는 설정으로 꺼 두었다는 뜻이다(WELCOME_CREDITS=0).
	welcomeDisabled = "disabled"
)

// WelcomeGranter 는 한 번만 주는 무료 크레딧을 주는 것의 모양이다. *wallet.Service 가 이 모양이다.
type WelcomeGranter interface {
	GrantFreeOnce(ctx context.Context, userID uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error)
}

// grantWelcomeRequest 는 환영 크레딧을 달라는 요청의 본문이다. 양은 받지 않는다. 서버의 설정이 정한다.
type grantWelcomeRequest struct {
	// UserID 는 받을 사용자다. 인증 서버의 public_id 다.
	UserID uuid.UUID `json:"user_id"`
}

// welcomeBody 는 환영 크레딧을 달라는 요청의 응답 모양이다.
type welcomeBody struct {
	// Status 는 granted, already_granted, disabled 중 하나다.
	Status string `json:"status"`
	// Granted 는 이번에 준 무료 크레딧의 양이다. 주지 않았으면 "0" 이다.
	Granted credit.Amount `json:"granted"`
	// ExpiresAt 은 이번에 준 크레딧이 사라지는 시각이다. 주지 않았으면 null 이다.
	ExpiresAt *time.Time `json:"expires_at"`
}

// grantWelcome 은 사용자에게 환영 크레딧을 주는 핸들러를 만든다. amount 는 줄 양이다.
//   - 줬다 -> 201
//   - 이미 받은 사용자다 -> 200. 오류가 아니다. 부르는 서버가 응답을 못 받아 다시 보낸 요청일 수 있다
//   - amount 가 0 이다 -> 200. 설정으로 꺼 둔 것이다. 부르는 서버는 할 일을 다 한 것으로 본다
func grantWelcome(granter WelcomeGranter, amount credit.Amount) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request grantWelcomeRequest
		if !readJSON(c, &request) {
			return
		}
		if request.UserID == uuid.Nil {
			badRequest(c, "user_id 가 있어야 합니다.")
			return
		}
		if amount == 0 {
			c.JSON(http.StatusOK, welcomeBody{Status: welcomeDisabled})
			return
		}
		grant, err := granter.GrantFreeOnce(c.Request.Context(), request.UserID, amount, WelcomeGrantKey)
		if errors.Is(err, wallet.ErrAlreadyGranted) {
			c.JSON(http.StatusOK, welcomeBody{Status: welcomeAlreadyGranted})
			return
		}
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusCreated, welcomeBody{Status: welcomeGranted, Granted: grant.Amount, ExpiresAt: &grant.ExpiresAt})
	}
}
