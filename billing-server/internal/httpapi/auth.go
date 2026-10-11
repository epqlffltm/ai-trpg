// billing-server/internal/httpapi/auth.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
)

// 검증의 결과를 HTTP 응답으로 바꾸는 일을 여기서 한다. 게임 서버와 같은 응답이다.
//   - 토큰이 없거나 틀렸다 -> 401. 클라이언트는 토큰을 갱신하거나 다시 로그인한다.
//   - 키를 구할 수 없어 확인하지 못했다 -> 503. 클라이언트의 잘못이 아니다. 로그아웃시키면 안 된다.

const (
	// bearerPrefix 는 Authorization 머리말에서 토큰 앞에 붙는 말이다.
	bearerPrefix = "Bearer "
	// claimsKey 는 검증을 마친 값을 요청에 실어 두는 이름이다.
	claimsKey = "auth.claims"
)

// TokenVerifier 는 access 토큰을 검증하는 것의 모양이다. *auth.Verifier 가 이 모양이다.
type TokenVerifier interface {
	Verify(ctx context.Context, token string) (auth.Claims, error)
}

// requireUser 는 요청의 토큰을 검증하는 미들웨어를 만든다. 로그인이 필요한 주소 앞에 붙인다.
// 통과하면 토큰의 주인을 요청에 실어 다음으로 넘기고, 아니면 여기서 응답하고 끝낸다.
func requireUser(verifier TokenVerifier) gin.HandlerFunc {
	return func(c *gin.Context) {
		token, ok := bearerToken(c.GetHeader("Authorization"))
		if !ok {
			unauthorized(c)
			return
		}
		claims, err := verifier.Verify(c.Request.Context(), token)
		if errors.Is(err, jwks.ErrUnavailable) {
			verificationUnavailable(c)
			return
		}
		if err != nil {
			unauthorized(c)
			return
		}
		c.Set(claimsKey, claims)
		c.Next()
	}
}

// bearerToken 은 "Bearer <토큰>" 모양의 머리말에서 토큰을 꺼낸다. 그 모양이 아니면 false 다.
// Bearer 라는 말은 대소문자를 가리지 않는다(RFC 9110).
func bearerToken(header string) (string, bool) {
	if len(header) <= len(bearerPrefix) || !strings.EqualFold(header[:len(bearerPrefix)], bearerPrefix) {
		return "", false
	}
	token := strings.TrimSpace(header[len(bearerPrefix):])
	return token, token != ""
}

// currentUser 는 requireUser 가 실어 둔 토큰의 주인을 꺼낸다. requireUser 뒤의 핸들러만 부른다.
func currentUser(c *gin.Context) auth.Claims {
	// requireUser 를 거치지 않은 주소에서 부르면 여기서 패닉이 난다. 주소를 잘못 묶은 것이라 일찍 드러나야 한다
	return c.MustGet(claimsKey).(auth.Claims)
}

// unauthorized 는 토큰이 없거나 받아들일 수 없을 때의 응답이다.
// 이유를 적지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
// WWW-Authenticate 는 401 응답에 붙이게 되어 있는 머리말이다. 어떤 방식으로 인증하는지 알려 준다.
func unauthorized(c *gin.Context) {
	c.Header("WWW-Authenticate", "Bearer")
	c.AbortWithStatusJSON(http.StatusUnauthorized, errorBody{Detail: "인증이 필요합니다."})
}

// verificationUnavailable 은 토큰이 맞는지 확인할 수 없을 때의 응답이다.
// Retry-After 는 언제 다시 시도하면 되는지 알려 준다. 키를 다시 가져오는 간격과 같다.
func verificationUnavailable(c *gin.Context) {
	c.Header("Retry-After", strconv.Itoa(int(jwks.RefetchInterval.Seconds())))
	c.AbortWithStatusJSON(http.StatusServiceUnavailable, errorBody{
		Detail: "지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
	})
}
