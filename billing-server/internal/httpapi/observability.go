// billing-server/internal/httpapi/observability.go

package httpapi

import (
	"fmt"
	"log/slog"
	"net/http"
	"runtime/debug"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// 요청마다 식별자를 걸고, 끝나면 공통 규격의 한 줄을 남긴다. 규격은 저장소 루트의 docs/observability.md 에 있다.
// 식별자를 정하는 규칙과 로그의 모양은 internal/obs 에 있다. 여기는 그것을 gin 에 붙이는 일만 한다.

const (
	// httpOperation 은 HTTP 요청을 처리하는 일의 이름이다. 어느 주소인지는 method 와 route 칸에 있다.
	httpOperation = "http.request"
	// unmatchedRoute 는 맞는 주소가 없는 요청의 route 칸에 적는 표시다.
	// 실제 주소를 route 에 적지 않는다. route 는 집계의 기준이라 값의 종류가 끝없이 늘면 안 된다.
	unmatchedRoute = "(unmatched)"
	// 처리하지 못한 패닉의 오류 코드
	codeUnhandled = "http.unhandled_exception"
	// 핸들러가 스스로 5xx 로 답한 오류의 코드
	codeInternal = "internal.error"
)

// 요청이 어떻게 끝났는지(result 칸).
const (
	resultSuccess     = "success"
	resultClientError = "client_error"
	resultServerError = "server_error"
)

// requestLogging 은 요청에 식별자를 걸고, 응답에 돌려주고, 끝나면 한 줄을 남기는 미들웨어다.
// 가장 먼저 붙인다. 뒤에 오는 모든 미들웨어와 핸들러의 로그에 식별자가 붙는다.
func requestLogging(logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		started := time.Now()
		requestID := obs.RequestIDFrom(singleHeader(c.Request, obs.RequestIDHeader))
		trace := obs.TraceFrom(singleHeader(c.Request, obs.TraceparentHeader))
		c.Request = c.Request.WithContext(obs.WithRequest(c.Request.Context(), requestID, trace))
		// 핸들러가 돌기 전에 붙인다. 어떤 응답(401, 404, 500)에도 식별자가 실린다
		c.Header(obs.RequestIDHeader, requestID)

		c.Next()

		logHandledErrors(logger, c)
		logFinished(logger, c, time.Since(started))
	}
}

// singleHeader 는 머리말의 값을 돌려준다. 같은 머리말이 여러 번 왔으면 빈 글자다. 어느 것을 믿을지 정할 수 없다.
func singleHeader(request *http.Request, name string) string {
	values := request.Header.Values(name)
	if len(values) != 1 {
		return ""
	}
	return values[0]
}

// logFinished 는 요청이 끝났다는 한 줄을 남긴다. 머리말, 주소 뒤에 붙은 값, 본문은 적지 않는다.
func logFinished(logger *slog.Logger, c *gin.Context, elapsed time.Duration) {
	status := c.Writer.Status()
	attrs := []slog.Attr{
		slog.String(obs.FieldOperation, httpOperation),
		slog.String("method", c.Request.Method),
	}
	attrs = append(attrs, routeAttrs(c)...)
	attrs = append(attrs,
		slog.Int("status_code", status),
		slog.Int64(obs.FieldDurationMS, elapsed.Milliseconds()),
		slog.String(obs.FieldResult, resultOf(status)),
	)
	logger.LogAttrs(c.Request.Context(), levelOf(status), "요청을 처리했다", attrs...)
}

// routeAttrs 는 요청이 맞은 주소의 틀을 적는다(/api/v1/billing/orders/:id). 실제 주소가 아니다.
// 맞은 틀이 없을 때만(404) 실제 경로를 path 칸에 따로 싣는다. 주소 뒤에 붙은 값(?a=b)은 싣지 않는다.
func routeAttrs(c *gin.Context) []slog.Attr {
	if route := c.FullPath(); route != "" {
		return []slog.Attr{slog.String("route", route)}
	}
	return []slog.Attr{
		slog.String("route", unmatchedRoute),
		slog.String("path", c.Request.URL.Path),
	}
}

// resultOf 는 상태 코드를 결과로 바꾼다.
func resultOf(status int) string {
	switch {
	case status >= http.StatusInternalServerError:
		return resultServerError
	case status >= http.StatusBadRequest:
		return resultClientError
	default:
		return resultSuccess
	}
}

// levelOf 는 상태 코드에 맞는 로그의 수준이다. 요청의 잘못(4xx)은 info 다. 서버는 제 일을 했다.
func levelOf(status int) slog.Level {
	if status >= http.StatusInternalServerError {
		return slog.LevelError
	}
	return slog.LevelInfo
}

// logHandledErrors 는 핸들러가 남긴 오류(c.Error)를 적는다. internalError 가 5xx 로 답하면서 남긴 원인이다.
// 원인은 응답에 싣지 않으므로 여기서만 볼 수 있다.
func logHandledErrors(logger *slog.Logger, c *gin.Context) {
	for _, handled := range c.Errors {
		logger.LogAttrs(c.Request.Context(), slog.LevelError, "요청을 처리하다 오류가 났다",
			slog.String(obs.FieldOperation, httpOperation),
			slog.String(obs.FieldErrorCode, codeInternal),
			slog.String(obs.FieldErrorType, fmt.Sprintf("%T", handled.Err)),
			slog.String(obs.FieldErrorMessage, handled.Err.Error()),
		)
	}
}

// recoverPanics 는 처리 중에 패닉이 나도 서버가 죽지 않고 500 으로 답하게 하는 미들웨어다.
// 패닉의 내용과 호출 기록은 로그에만 남긴다. 응답에는 싣지 않는다.
// requestLogging 뒤에 붙인다. 그래야 요청이 끝난 줄에 500 이 적힌다.
func recoverPanics(logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			recovered := recover()
			if recovered == nil {
				return
			}
			// net/http 가 "응답을 중단한다"는 뜻으로 쓰는 패닉이다. 오류가 아니다. 그대로 넘긴다
			if recovered == http.ErrAbortHandler {
				panic(recovered)
			}
			logPanic(logger, c, recovered)
			answerPanic(c)
		}()
		c.Next()
	}
}

// logPanic 은 패닉을 공통 규격으로 적는다.
func logPanic(logger *slog.Logger, c *gin.Context, recovered any) {
	logger.LogAttrs(c.Request.Context(), slog.LevelError, "처리하지 못한 패닉이 났다",
		slog.String(obs.FieldOperation, httpOperation),
		slog.String(obs.FieldErrorCode, codeUnhandled),
		slog.String(obs.FieldErrorType, fmt.Sprintf("%T", recovered)),
		slog.String(obs.FieldErrorMessage, fmt.Sprint(recovered)),
		slog.String(obs.FieldStackTrace, string(debug.Stack())),
	)
}

// answerPanic 은 패닉이 난 요청에 500 으로 답한다. 이미 응답을 보내기 시작했으면 더 쓰지 않는다.
func answerPanic(c *gin.Context) {
	if c.Writer.Written() {
		c.Abort()
		return
	}
	c.AbortWithStatusJSON(http.StatusInternalServerError, errorBody{
		Detail: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
	})
}
