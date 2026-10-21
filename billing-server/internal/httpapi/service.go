// billing-server/internal/httpapi/service.go

package httpapi

import (
	"bytes"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/peers"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

// 우리 서버들이 부르는 주소들(/api/v1/billing/service/...) 앞에 붙는 확인.
// 사용자의 토큰을 보지 않는다. 요청의 서명을 본다. 사용자는 이 주소들을 부를 수 없다.

const (
	// GameServer 는 게임 서버의 이름이다. 홀드에 "누가 걸었는가"로 적힌다(internal/peers).
	GameServer = peers.Game
	// AuthServer 는 인증 서버의 이름이다.
	AuthServer = peers.Auth
	// ChatServer 는 chat 서버의 이름이다. chat 과 story 의 말 한 번에 홀드를 건다(docs/architecture/chat-server.md).
	ChatServer = peers.Chat
	// callerKey 는 서명을 확인한 서버의 이름을 요청에 실어 두는 이름이다.
	callerKey = "service.caller"
)

// serviceCaller 는 이 서버를 부르는 우리 서버 하나와 그 서버와 함께 아는 비밀이다.
type serviceCaller struct {
	name   string
	secret string
}

// requireService 는 서버 하나의 서명을 확인하는 미들웨어를 만든다. name 은 그 비밀을 가진 서버의 이름이다.
func requireService(name string, secret string, now func() time.Time) gin.HandlerFunc {
	return requireAnyService([]serviceCaller{{name: name, secret: secret}}, now)
}

// requireAnyService 는 callers 가운데 하나의 서명인지 확인하는 미들웨어를 만든다. 같은 주소를 여러 서버가 부를 때 쓴다.
// 맞는 비밀을 가진 서버의 이름을 요청에 실어 다음으로 넘기고, 아무것과도 맞지 않으면 여기서 401 로 답하고 끝낸다.
// 핸들러는 그 이름으로 무엇을 할 수 있는지 가른다(홀드의 주인, 쓸 수 있는 가격표).
//
// 서명은 받은 바이트 그대로에 대한 것이다. 그래서 본문을 먼저 다 읽어 확인하고, 핸들러가 다시 읽을 수 있게 되돌려 놓는다.
func requireAnyService(callers []serviceCaller, now func() time.Time) gin.HandlerFunc {
	return func(c *gin.Context) {
		raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, maxBodyBytes))
		if err != nil {
			abort(c, http.StatusBadRequest, codeServiceBadRequest, "요청의 본문을 읽지 못했습니다.")
			return
		}
		header := c.GetHeader(serviceauth.SignatureHeader)
		// 주소는 받은 그대로(경로와 그 뒤에 붙은 값)를 쓴다. 부르는 서버가 서명한 것과 같은 글자여야 한다
		name, ok := signedBy(callers, header, c.Request.Method, c.Request.URL.RequestURI(), raw, now())
		if !ok {
			abort(c, http.StatusUnauthorized, codeServiceBadSignature, "요청의 서명이 맞지 않습니다.")
			return
		}
		c.Request.Body = io.NopCloser(bytes.NewReader(raw))
		c.Set(callerKey, name)
		c.Next()
	}
}

// signedBy 는 요청에 서명한 서버의 이름을 찾는다. 비밀이 빈 서버(chat 서버를 띄우지 않는 동안)는 후보가 아니다.
// 빈 비밀로는 누구나 서명할 수 있다. 서명 검사(internal/signature)도 짧은 비밀을 받지 않지만 여기서 먼저 뺀다.
// 비밀은 서버마다 다르다(설정이 막는다). 그래서 맞는 서버는 많아야 하나다.
func signedBy(callers []serviceCaller, header string, method string, requestURI string, body []byte, at time.Time) (string, bool) {
	for _, candidate := range callers {
		if candidate.secret == "" {
			continue
		}
		if serviceauth.Verify(candidate.secret, header, method, requestURI, body, at) == nil {
			return candidate.name, true
		}
	}
	return "", false
}

// caller 는 requireService 가 실어 둔 서버의 이름을 꺼낸다. requireService 뒤의 핸들러만 부른다.
func caller(c *gin.Context) string {
	// requireService 를 거치지 않은 주소에서 부르면 여기서 패닉이 난다. 주소를 잘못 묶은 것이라 일찍 드러나야 한다
	return c.MustGet(callerKey).(string)
}
