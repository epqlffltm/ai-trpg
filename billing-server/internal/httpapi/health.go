// billing-server/internal/httpapi/health.go

package httpapi

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// ReadinessTimeout 은 준비 상태를 확인할 때 DB 의 답을 기다리는 가장 긴 시간이다.
// 확인하는 쪽(프록시, 관리 도구)이 오래 붙들려 있지 않게 한다.
const ReadinessTimeout = 3 * time.Second

// statusBody 는 상태를 확인하는 주소들의 응답 모양이다.
type statusBody struct {
	Status string `json:"status"`
}

// health 는 프로세스가 살아 있는지만 답한다. DB 를 보지 않는다.
// DB 가 죽었다고 이 주소까지 실패하면, 프로세스를 다시 띄워도 낫지 않는 문제에 재시작만 되풀이된다.
func health(c *gin.Context) {
	c.JSON(http.StatusOK, statusBody{Status: "ok"})
}

// readiness 는 요청을 받을 준비가 됐는지 답하는 핸들러를 만든다. DB 가 답하면 200, 아니면 503 이다.
// 실패한 이유는 응답에 싣지 않는다. 접속 주소나 계정 이름이 밖으로 나가지 않게 한다. 로그에는 오류의 종류만 남긴다.
func readiness(db database.Pinger, logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		if err := pingWithin(ctx, db); err != nil {
			logUnreachable(ctx, logger, err)
			c.JSON(http.StatusServiceUnavailable, statusBody{Status: "unavailable"})
			return
		}
		c.JSON(http.StatusOK, statusBody{Status: "ok"})
	}
}

// pingWithin 은 정해 둔 시간 안에 DB 가 답하는지 묻는다. 답하지 않으면 그 오류를 돌려준다.
func pingWithin(ctx context.Context, db database.Pinger) error {
	ctx, cancel := context.WithTimeout(ctx, ReadinessTimeout)
	defer cancel()
	return db.Ping(ctx)
}

// logUnreachable 은 DB 에 닿지 않은 까닭을 남긴다. 다른 세 서버처럼 오류의 종류만 적는다.
// 오류의 글은 적지 않는다. 드라이버의 오류에는 접속 주소와 계정 이름이 들어 있다.
func logUnreachable(ctx context.Context, logger *slog.Logger, err error) {
	logger.LogAttrs(ctx, slog.LevelWarn, "DB 에 닿지 않는다",
		slog.String(obs.FieldErrorType, fmt.Sprintf("%T", err)),
	)
}
