// billing-server/internal/httpapi/metrics_test.go

package httpapi_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"slices"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
)

// 요청과 DB 의 상태가 정한 이름과 label 로 세어지는지 본다. 이름과 label 은 docs/observability.md 의 "메트릭"에 있다.
// 이름은 OTLP 의 이름이다. Prometheus 의 이름(…_total, …_seconds)이 되는지는 CI 의 stack 이 본다.

// measured 는 메트릭을 메모리에 모으는 라우터로 요청을 보낸다.
func measured(t *testing.T, db database.Pinger) (*metricstest.Recorder, func(method, path string) int) {
	t.Helper()
	recorder := metricstest.New(t)
	router := httpapi.NewRouter(httpapi.Dependencies{DB: db, Meter: recorder.Meter()})
	send := func(method, path string) int {
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequest(method, path, nil))
		return response.Code
	}
	return recorder, send
}

// labels 는 요청 수의 label 이다.
func labels(method, route string, status int) []attribute.KeyValue {
	return []attribute.KeyValue{
		attribute.String("method", method), attribute.String("route", route), attribute.Int("status_code", status),
	}
}

func TestRequestsAreCountedByTheirRouteTemplateAndStatus(t *testing.T) {
	recorder, send := measured(t, &fakeDB{})
	send(http.MethodGet, httpapi.HealthPath)
	send(http.MethodGet, httpapi.HealthPath)
	// 로그인이 필요한 주소에 토큰 없이 왔다. 401 이고 route 는 틀(/api/v1/billing/orders/:id)이다
	send(http.MethodGet, httpapi.APIPrefix+"/orders/1234")

	if got := recorder.Int64("http_server_requests", labels(http.MethodGet, httpapi.HealthPath, http.StatusOK)...); got != 2 {
		t.Errorf("/health 의 수 = %d. 2 여야 한다", got)
	}
	route := httpapi.APIPrefix + "/orders/:id"
	if got := recorder.Int64("http_server_requests", labels(http.MethodGet, route, http.StatusUnauthorized)...); got != 1 {
		t.Errorf("%s 의 401 = %d. 1 이어야 한다", route, got)
	}
}

func TestAnUnknownPathIsCountedAsUnmatched(t *testing.T) {
	// 실제 주소를 label 에 쓰면 아무 주소나 찔러 보는 요청이 값의 종류를 끝없이 늘린다
	recorder, send := measured(t, &fakeDB{})
	send(http.MethodGet, "/wp-login.php")
	send(http.MethodGet, "/.env")

	if got := recorder.Int64("http_server_requests", labels(http.MethodGet, "(unmatched)", http.StatusNotFound)...); got != 2 {
		t.Errorf("맞은 틀이 없는 요청 = %d. 2 여야 한다", got)
	}
}

func TestAnInventedMethodIsCountedAsOther(t *testing.T) {
	recorder, send := measured(t, &fakeDB{})
	send("PROPFIND", httpapi.HealthPath)

	if got := recorder.Int64("http_server_requests", labels("_OTHER", "(unmatched)", http.StatusNotFound)...); got != 1 {
		t.Errorf("정하지 않은 메서드 = %d. _OTHER 로 1 이어야 한다", got)
	}
}

func TestRequestDurationIsInSecondsWithTheSharedBuckets(t *testing.T) {
	recorder, send := measured(t, &fakeDB{})
	send(http.MethodGet, httpapi.HealthPath)

	found := recorder.Find("http_server_request_duration")
	if found.Unit != "s" {
		t.Errorf("단위 = %q. s 여야 한다(수집기가 _seconds 를 붙인다)", found.Unit)
	}
	count := recorder.HistogramCount("http_server_request_duration",
		attribute.String("method", http.MethodGet), attribute.String("route", httpapi.HealthPath))
	if count != 1 {
		t.Errorf("잰 수 = %d. 1 이어야 한다(status_code 는 시간의 label 이 아니다)", count)
	}
	if bounds := recorder.Bounds("http_server_request_duration"); !slices.Equal(bounds, metrics.DurationBuckets) {
		t.Errorf("구간 = %v. 다섯 서버가 함께 쓰는 구간이어야 한다", bounds)
	}
}

func TestActiveRequestsGoBackToZero(t *testing.T) {
	recorder, send := measured(t, &fakeDB{})
	send(http.MethodGet, httpapi.HealthPath)

	if got := recorder.Int64("http_server_active_requests"); got != 0 {
		t.Errorf("처리 중인 요청 = %d. 끝났으니 0 이어야 한다", got)
	}
}

func TestAPanickedRequestIsCountedAsServerError(t *testing.T) {
	recorder, send := measured(t, panickingDB{})
	send(http.MethodGet, httpapi.ReadyPath)

	if got := recorder.Int64("http_server_requests", labels(http.MethodGet, httpapi.ReadyPath, http.StatusInternalServerError)...); got != 1 {
		t.Errorf("패닉으로 끝난 요청 = %d. 500 으로 1 이어야 한다", got)
	}
}

func TestReadinessRecordsWhetherTheDatabaseAnswers(t *testing.T) {
	db := &fakeDB{}
	recorder, send := measured(t, db)
	if recorder.Has("db_up") {
		t.Fatal("확인하기 전에 db_up 이 있다. 모르는 것을 0 이나 1 로 적으면 안 된다")
	}

	send(http.MethodGet, httpapi.ReadyPath)
	if got := recorder.Int64("db_up"); got != 1 {
		t.Errorf("DB 가 답할 때 db_up = %d. 1 이어야 한다", got)
	}

	db.err = errors.New("connection refused")
	send(http.MethodGet, httpapi.ReadyPath)
	if got := recorder.Int64("db_up"); got != 0 {
		t.Errorf("DB 가 답하지 않을 때 db_up = %d. 0 이어야 한다", got)
	}
}

func TestARouterWithoutAMeterStillAnswers(t *testing.T) {
	// 메트릭을 넣지 않은 테스트와 명령은 세지 않을 뿐이다
	if code := get(t, &fakeDB{}, httpapi.HealthPath).Code; code != http.StatusOK {
		t.Errorf("상태 = %d", code)
	}
}
