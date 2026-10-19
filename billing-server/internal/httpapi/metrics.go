// billing-server/internal/httpapi/metrics.go

package httpapi

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// 요청과 DB 의 상태를 메트릭으로 센다. 이름과 label 은 저장소 루트의 docs/observability.md 의 "메트릭"에 있다.
// 이름은 OTLP 의 이름이다. 수집기가 단위와 _total 을 붙여 표의 이름(http_server_requests_total …)이 된다.

// 계측기의 이름.
const (
	metricRequests       = "http_server_requests"
	metricRequestSeconds = "http_server_request_duration"
	metricActiveRequests = "http_server_active_requests"
	metricDBUp           = "db_up"
)

// otherMethod 는 HTTP 가 정한 메서드가 아닌 것을 적는 값이다(OpenTelemetry 의 규칙과 같다).
// 클라이언트가 지어 보낸 메서드를 그대로 label 로 쓰면 값의 종류가 끝없이 는다.
const otherMethod = "_OTHER"

// knownMethods 는 label 에 그대로 적는 메서드다.
var knownMethods = map[string]bool{
	http.MethodGet: true, http.MethodHead: true, http.MethodPost: true, http.MethodPut: true, http.MethodPatch: true,
	http.MethodDelete: true, http.MethodOptions: true, http.MethodConnect: true, http.MethodTrace: true,
}

// httpMetrics 는 요청을 세는 계측기들이다.
type httpMetrics struct {
	requests metric.Int64Counter
	duration metric.Float64Histogram
	active   metric.Int64UpDownCounter
}

// newHTTPMetrics 는 요청의 계측기를 만든다.
func newHTTPMetrics(meter metric.Meter) (httpMetrics, error) {
	requests, requestsErr := meter.Int64Counter(metricRequests,
		metric.WithDescription("끝난 요청의 수"))
	duration, durationErr := meter.Float64Histogram(metricRequestSeconds,
		metric.WithDescription("요청을 받아 응답을 끝낼 때까지"),
		metric.WithUnit("s"),
		metric.WithExplicitBucketBoundaries(metrics.DurationBuckets...))
	active, activeErr := meter.Int64UpDownCounter(metricActiveRequests,
		metric.WithDescription("지금 처리 중인 요청의 수"))
	if err := firstError(requestsErr, durationErr, activeErr); err != nil {
		return httpMetrics{}, err
	}
	return httpMetrics{requests: requests, duration: duration, active: active}, nil
}

// firstError 는 처음 나온 오류다.
func firstError(errs ...error) error {
	for _, err := range errs {
		if err != nil {
			return err
		}
	}
	return nil
}

// measureRequests 는 요청을 세고 걸린 시간을 재는 미들웨어다. 요청이 끝난 줄(requestLogging)과 같은 값을 쓴다.
// 주소는 맞은 틀(route)이다. 맞은 것이 없으면 (unmatched) 다. 실제 주소는 label 로 쓰지 않는다.
func measureRequests(m httpMetrics) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		started := time.Now()
		m.active.Add(ctx, 1)
		defer m.active.Add(ctx, -1)

		c.Next()

		recordRequest(ctx, m, c, time.Since(started))
	}
}

// recordRequest 는 끝난 요청 하나를 센다.
func recordRequest(ctx context.Context, m httpMetrics, c *gin.Context, elapsed time.Duration) {
	method := attribute.String("method", methodLabel(c.Request.Method))
	route := attribute.String("route", routeLabel(c))
	status := attribute.Int("status_code", c.Writer.Status())
	m.requests.Add(ctx, 1, metric.WithAttributes(method, route, status))
	m.duration.Record(ctx, elapsed.Seconds(), metric.WithAttributes(method, route))
}

// methodLabel 은 메서드를 label 의 값으로 바꾼다. 정한 메서드가 아니면 _OTHER 다.
func methodLabel(method string) string {
	if knownMethods[method] {
		return method
	}
	return otherMethod
}

// routeLabel 은 요청이 맞은 주소의 틀이다. 로그의 route 칸과 같은 값이다.
func routeLabel(c *gin.Context) string {
	if route := c.FullPath(); route != "" {
		return route
	}
	return unmatchedRoute
}

// dbGauge 는 준비 상태 확인이 마지막으로 본 DB 의 상태를 적는 계측기다. 1 이면 닿는다.
// 확인(/health/ready)이 오기 전에는 값이 없다. 아직 모르는 것을 0(닿지 않음)으로 적지 않는다.
type dbGauge struct {
	up metric.Int64Gauge
}

// newDBGauge 는 DB 의 상태를 적는 계측기를 만든다.
func newDBGauge(meter metric.Meter) (dbGauge, error) {
	up, err := meter.Int64Gauge(metricDBUp, metric.WithDescription("준비 상태 확인이 마지막으로 본 DB 의 상태. 1 이면 닿는다"))
	if err != nil {
		return dbGauge{}, err
	}
	return dbGauge{up: up}, nil
}

// record 는 DB 에 닿았는지를 적는다.
func (g dbGauge) record(ctx context.Context, reachable bool) {
	value := int64(0)
	if reachable {
		value = 1
	}
	g.up.Record(ctx, value)
}

// routerMetrics 는 라우터가 쓰는 계측기들이다.
type routerMetrics struct {
	http httpMetrics
	db   dbGauge
}

// newRouterMetrics 는 라우터의 계측기를 만든다. 만들지 못하면(이름이 틀렸다) 그 까닭을 남기고 세지 않는 것으로 바꾼다.
// 메트릭 때문에 서버가 뜨지 못하게 하지 않는다. 이름은 이 파일의 상수라 테스트가 먼저 잡는다.
func newRouterMetrics(meter metric.Meter, logger *slog.Logger) routerMetrics {
	httpm, httpErr := newHTTPMetrics(metrics.MeterOrNoop(meter))
	db, dbErr := newDBGauge(metrics.MeterOrNoop(meter))
	if err := firstError(httpErr, dbErr); err != nil {
		logger.Error("요청의 메트릭을 만들지 못했습니다. 세지 않고 진행합니다",
			slog.String(obs.FieldOperation, "metrics.setup"),
			slog.String(obs.FieldErrorMessage, err.Error()),
		)
		httpm, _ = newHTTPMetrics(metrics.MeterOrNoop(nil))
		db, _ = newDBGauge(metrics.MeterOrNoop(nil))
	}
	return routerMetrics{http: httpm, db: db}
}
