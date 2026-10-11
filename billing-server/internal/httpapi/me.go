// billing-server/internal/httpapi/me.go

package httpapi

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// meBody 는 /me 의 응답 모양이다.
type meBody struct {
	// UserID 는 인증 서버의 public_id 다.
	UserID uuid.UUID `json:"user_id"`
}

// me 는 토큰의 주인이 누구인지 돌려준다.
// 인증 서버가 발급한 토큰을 이 서버가 검증할 수 있는지 확인하는 가장 작은 주소다.
// 결제 서버는 사용자의 이름이나 이메일을 모른다. 인증 서버의 public_id 만 안다.
func me(c *gin.Context) {
	c.JSON(http.StatusOK, meBody{UserID: currentUser(c).UserID})
}
