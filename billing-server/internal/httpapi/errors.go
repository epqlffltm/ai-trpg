// billing-server/internal/httpapi/errors.go

package httpapi

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// errorBody 는 오류 응답의 모양이다. 다른 서버들과 같은 칸 이름(detail)을 쓴다.
type errorBody struct {
	Detail string `json:"detail"`
}

// badRequest 는 요청의 값이 틀렸을 때의 응답이다. 무엇을 고치면 되는지 적는다.
func badRequest(c *gin.Context, detail string) {
	c.AbortWithStatusJSON(http.StatusBadRequest, errorBody{Detail: detail})
}

// notFound 는 그런 것이 없을 때의 응답이다. 남의 것도 없는 것으로 답한다.
func notFound(c *gin.Context, detail string) {
	c.AbortWithStatusJSON(http.StatusNotFound, errorBody{Detail: detail})
}

// conflict 는 요청이 지금의 상태와 맞지 않을 때의 응답이다. 같은 요청을 다시 보내도 되지 않는다.
func conflict(c *gin.Context, detail string) {
	c.AbortWithStatusJSON(http.StatusConflict, errorBody{Detail: detail})
}

// internalError 는 서버 쪽의 문제로 처리하지 못했을 때의 응답이다.
// 원인은 서버의 기록에만 남기고 응답에는 싣지 않는다. DB 의 오류에는 테이블 이름과 쿼리가 들어 있다.
func internalError(c *gin.Context, cause error) {
	// gin 의 요청 기록(Logger)이 이 오류를 그 요청의 줄에 함께 찍는다
	_ = c.Error(cause)
	c.AbortWithStatusJSON(http.StatusInternalServerError, errorBody{
		Detail: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
	})
}
