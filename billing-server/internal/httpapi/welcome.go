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

// 환영 크레딧을 받는 주소. 사용자가 스스로 한 번만 받는 무료 크레딧이다.
//
// 가입할 때 저절로 주는 것이 더 자연스럽다. 그러려면 인증 서버가 이 서버를 불러야 하는데,
// 서버끼리 서로를 확인하는 방법이 아직 없다. 그때까지는 사용자가 이 주소를 불러 받는다.

// WelcomeGrantKey 는 환영 크레딧이라는 지급의 이름이다. 한 사용자는 이 이름의 지급을 한 번만 받는다.
const WelcomeGrantKey = "welcome"

// WelcomeGranter 는 한 번만 주는 무료 크레딧을 주는 것의 모양이다. *wallet.Service 가 이 모양이다.
type WelcomeGranter interface {
	GrantFreeOnce(ctx context.Context, userID uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error)
}

// welcomeBody 는 환영 크레딧을 받은 응답의 모양이다.
type welcomeBody struct {
	// Granted 는 받은 무료 크레딧의 양이다.
	Granted credit.Amount `json:"granted"`
	// ExpiresAt 은 이 크레딧이 사라지는 시각이다.
	ExpiresAt time.Time `json:"expires_at"`
}

// claimWelcome 은 토큰의 주인에게 환영 크레딧을 주는 핸들러를 만든다. amount 는 줄 양이다.
//   - 받았다 -> 201
//   - 이미 받았다 -> 409. 다 썼거나 사라진 뒤에도 같다
//   - amount 가 0 이다 -> 404. 설정으로 꺼 둔 것이다
func claimWelcome(granter WelcomeGranter, amount credit.Amount) gin.HandlerFunc {
	return func(c *gin.Context) {
		if amount == 0 {
			notFound(c, "지금은 환영 크레딧을 주지 않습니다.")
			return
		}
		grant, err := granter.GrantFreeOnce(c.Request.Context(), currentUser(c).UserID, amount, WelcomeGrantKey)
		if errors.Is(err, wallet.ErrAlreadyGranted) {
			conflict(c, "환영 크레딧은 한 번만 받을 수 있습니다.")
			return
		}
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusCreated, welcomeBody{Granted: grant.Amount, ExpiresAt: grant.ExpiresAt})
	}
}
