// billing-server/internal/httpapi/deadline.go

package httpapi

import (
	"context"
	"errors"
	"time"

	"github.com/gin-gonic/gin"
)

// 요청 하나를 처리하는 시간에 마감을 둔다(#334).
//
// 연결 풀이 모두 쓰이면 요청은 연결이 빌 때까지 기다린다. DB 의 lock_timeout, statement_timeout 은 연결을 얻은 뒤의
// 쿼리에만 걸리므로 이 기다림을 세지 않는다. 마감이 없으면 기다림은 클라이언트가 떠날 때만 끝난다.
// 마감은 기다림과 쿼리를 함께 덮는다. 쿼리 중에 걸리면 pgx 가 DB 에 취소를 보낸다. 그 쿼리는 적히지 않는다.
//
// 결제 작업(승인, 청약철회, 알림)은 요청과 떼어 낸 제 마감(order.OperationTimeout)으로 돈다. 이 마감은 그것을 끊지 않는다.

// RequestTimeout 은 요청 하나를 처리하는 가장 긴 시간이다.
// 게임 서버가 결제 서버에 주는 예산(BILLING_BUDGET_SECONDS)과, 서버의 쿼리 한도(database.ServerLimits 의 10초)와 같다.
// 이 서버의 쿼리는 가장 느린 것도 0.5초 안이다(README 의 "DB 도 스스로 끊는다"). 멀쩡한 요청은 닿지 않는다.
const RequestTimeout = 10 * time.Second

// statusClientClosed 는 응답을 받기 전에 클라이언트가 떠난 요청을 로그에 적는 상태 코드다(nginx 의 499).
// 받을 쪽이 없으니 본문은 쓰지 않는다. 4xx 라 서버의 오류로 세지 않는다.
const statusClientClosed = 499

// requestTimeoutOf 는 라우터가 쓸 마감을 고른다. 넣어 준 것이 없으면 RequestTimeout 이다.
func requestTimeoutOf(deps Dependencies) time.Duration {
	if deps.RequestTimeout > 0 {
		return deps.RequestTimeout
	}
	return RequestTimeout
}

// requestDeadline 은 요청의 ctx 에 마감을 거는 미들웨어다. 뒤에 오는 미들웨어와 핸들러가 모두 이 ctx 를 쓴다.
func requestDeadline(limit time.Duration) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx, cancel := context.WithTimeout(c.Request.Context(), limit)
		defer cancel()
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

// pastDeadline 은 오류가 마감에 걸려 난 것인지 본다. 풀을 기다리다 걸린 것과 쿼리 중에 걸린 것이 모두 이것이다.
// pgx 는 두 경우 모두 context.DeadlineExceeded 를 감싸 돌려준다. DB 의 SQLSTATE 가 아니라 database.IsTimeout 에는 걸리지 않는다.
// 결제 작업이 제 마감에 걸린 것(order.ErrTimedOut)은 그 핸들러가 먼저 가린다.
func pastDeadline(err error) bool {
	return errors.Is(err, context.DeadlineExceeded)
}

// clientLeft 는 응답을 받기 전에 클라이언트가 떠나 요청이 끊긴 것인지 본다.
// 오류만 보지 않고 요청의 ctx 가 정말 취소되었는지도 본다. 다른 까닭의 context.Canceled 를 서버의 오류에서 빼지 않는다.
func clientLeft(c *gin.Context, err error) bool {
	return errors.Is(err, context.Canceled) && errors.Is(c.Request.Context().Err(), context.Canceled)
}
