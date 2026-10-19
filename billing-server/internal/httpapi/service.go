// billing-server/internal/httpapi/service.go

package httpapi

import (
	"bytes"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

// 우리 서버들이 부르는 주소들(/api/v1/billing/service/...) 앞에 붙는 확인.
// 사용자의 토큰을 보지 않는다. 요청의 서명을 본다. 사용자는 이 주소들을 부를 수 없다.

const (
	// GameServer 는 게임 서버의 이름이다. 홀드에 "누가 걸었는가"로 적힌다. 관측 규격의 서비스 이름과 같다.
	GameServer = "trpg-server"
	// AuthServer 는 인증 서버의 이름이다.
	AuthServer = "auth-server"
	// callerKey 는 서명을 확인한 서버의 이름을 요청에 실어 두는 이름이다.
	callerKey = "service.caller"
)

// requireService 는 요청의 서명을 확인하는 미들웨어를 만든다. name 은 그 비밀을 가진 서버의 이름이다.
// 통과하면 그 이름을 요청에 실어 다음으로 넘기고, 아니면 여기서 401 로 답하고 끝낸다.
//
// 서명은 받은 바이트 그대로에 대한 것이다. 그래서 본문을 먼저 다 읽어 확인하고, 핸들러가 다시 읽을 수 있게 되돌려 놓는다.
func requireService(name string, secret string, now func() time.Time) gin.HandlerFunc {
	return func(c *gin.Context) {
		raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, maxBodyBytes))
		if err != nil {
			abort(c, http.StatusBadRequest, codeServiceBadRequest, "요청의 본문을 읽지 못했습니다.")
			return
		}
		header := c.GetHeader(serviceauth.SignatureHeader)
		// 주소는 받은 그대로(경로와 그 뒤에 붙은 값)를 쓴다. 부르는 서버가 서명한 것과 같은 글자여야 한다
		if err := serviceauth.Verify(secret, header, c.Request.Method, c.Request.URL.RequestURI(), raw, now()); err != nil {
			abort(c, http.StatusUnauthorized, codeServiceBadSignature, "요청의 서명이 맞지 않습니다.")
			return
		}
		c.Request.Body = io.NopCloser(bytes.NewReader(raw))
		c.Set(callerKey, name)
		c.Next()
	}
}

// caller 는 requireService 가 실어 둔 서버의 이름을 꺼낸다. requireService 뒤의 핸들러만 부른다.
func caller(c *gin.Context) string {
	// requireService 를 거치지 않은 주소에서 부르면 여기서 패닉이 난다. 주소를 잘못 묶은 것이라 일찍 드러나야 한다
	return c.MustGet(callerKey).(string)
}
