// billing-server/internal/httpapi/spec_test.go

// API 목록(api/openapi.yaml, #560)이 라우터와 어긋나지 않는지 시험한다.
//
//   - 목록이 OpenAPI 의 규칙에 맞는다
//   - 라우터의 주소와 목록의 주소가 서로 빠짐없이 같다. 주소를 더하고 목록을 빼먹거나, 지운 주소가 목록에 남지 않는다
//   - 이 패키지의 HTTP 테스트는 요청을 serve 로 보낸다. 받은 응답이 목록의 상태 코드와 모양에 맞지 않으면 그 테스트가 실패한다
//
// 보지 않는 응답이 있다.
//   - 목록에 없는 주소(테스트가 따로 붙인 주소)의 것. 그런 주소가 라우터에 있으면 위의 둘째가 잡는다
//   - 라우터가 열지 않은 주소의 404(설정이 없어 닫은 출석과 토스의 알림). 목록에는 열었을 때의 모양만 둔다
//   - 응답을 받기 전에 떠난 요청의 499. 로그에만 적고 받는 쪽이 없다
package httpapi_test

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"

	"github.com/getkin/kin-openapi/openapi3"
	"github.com/getkin/kin-openapi/openapi3filter"
	"github.com/getkin/kin-openapi/routers"
	"github.com/getkin/kin-openapi/routers/legacy"

	"github.com/epqlffltm/ai-trpg/billing-server/api"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
)

// ginNotFound 는 라우터에 없는 주소에 gin 이 돌려주는 본문이다.
const ginNotFound = "404 page not found"

// clientClosed 는 응답을 받기 전에 떠난 요청을 로그에 적는 상태 코드다(deadline.go).
const clientClosed = 499

// notInSpec 는 라우터에 있지만 목록에 두지 않는 주소다. 개발용 결제 화면은 API 가 아니라 HTML 이다.
var notInSpec = map[string]bool{"GET " + httpapi.CheckoutPath: true}

// spec 은 읽은 목록과 주소를 찾는 것이다. 테스트 전체에서 한 번 읽는다.
var spec struct {
	once   sync.Once
	doc    *openapi3.T
	router routers.Router
	err    error
}

// loadSpec 은 목록을 읽어 돌려준다. 읽지 못하면 테스트를 멈춘다.
func loadSpec(t *testing.T) (*openapi3.T, routers.Router) {
	t.Helper()
	spec.once.Do(func() {
		spec.doc, spec.err = api.Load(context.Background())
		if spec.err == nil {
			spec.router, spec.err = legacy.NewRouter(spec.doc)
		}
	})
	if spec.err != nil {
		t.Fatalf("API 목록을 읽지 못했다: %v", spec.err)
	}
	return spec.doc, spec.router
}

// serve 는 요청을 handler 에 보내고 응답을 돌려준다. 목록에 있는 주소면 응답이 목록에 맞는지 본다.
func serve(t *testing.T, handler http.Handler, request *http.Request) *httptest.ResponseRecorder {
	t.Helper()
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	checkResponse(t, request, response)
	return response
}

// checkResponse 는 응답이 목록의 상태 코드와 모양에 맞는지 본다. 보지 않는 응답은 이 파일의 맨 위에 적었다.
// 인증은 보지 않는다(토큰과 서명은 그 테스트들이 본다). 목록에 없는 상태 코드는 틀린 것이다.
func checkResponse(t *testing.T, request *http.Request, response *httptest.ResponseRecorder) {
	t.Helper()
	if !answeredByARoute(response) {
		return
	}
	_, router := loadSpec(t)
	route, params, err := router.FindRoute(request)
	if err != nil {
		return
	}
	input := &openapi3filter.ResponseValidationInput{
		RequestValidationInput: &openapi3filter.RequestValidationInput{Request: request, PathParams: params, Route: route},
		Status:                 response.Code,
		Header:                 response.Header(),
		Body:                   io.NopCloser(bytes.NewReader(response.Body.Bytes())),
		Options:                &openapi3filter.Options{IncludeResponseStatus: true, MultiError: true},
	}
	if err := openapi3filter.ValidateResponse(request.Context(), input); err != nil {
		t.Errorf("%s %s 의 응답(%d)이 API 목록과 맞지 않다: %v\n본문: %s",
			request.Method, request.URL.Path, response.Code, err, response.Body.String())
	}
}

// answeredByARoute 는 열린 주소가 답해 받는 쪽이 있는 응답인지 본다. 닫은 주소의 404 와 떠난 요청의 499 가 아니다.
func answeredByARoute(response *httptest.ResponseRecorder) bool {
	closed := response.Code == http.StatusNotFound && response.Body.String() == ginNotFound
	return !closed && response.Code != clientClosed
}

// serveUnchecked 는 응답을 목록으로 보지 않고 요청을 보낸다. 실제로는 그 주소가 내지 않는 응답을 일부러 만드는 테스트가 쓴다.
func serveUnchecked(handler http.Handler, request *http.Request) *httptest.ResponseRecorder {
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func TestTheSpecIsValidOpenAPI(t *testing.T) {
	doc, _ := loadSpec(t)

	if doc.Info.Title == "" || len(doc.Paths.Map()) == 0 {
		t.Fatalf("목록이 비었다: %+v", doc.Info)
	}
}

func TestEveryRouteIsInTheSpecAndEveryPathIsARoute(t *testing.T) {
	doc, _ := loadSpec(t)
	// 모든 주소를 여는 설정이다. 넣지 않으면 열지 않는 주소가 있다(출석, 토스의 알림, 개발용 결제 화면)
	router := httpapi.NewRouter(httpapi.Dependencies{
		Attendance: &fakeAttendance{}, TossWebhook: true, CheckoutClientKey: "test_ck",
	})

	fromRouter := map[string]bool{}
	for _, route := range router.Routes() {
		key := route.Method + " " + openAPIPath(route.Path)
		if !notInSpec[route.Method+" "+route.Path] {
			fromRouter[key] = true
		}
	}
	fromSpec := map[string]bool{}
	for path, item := range doc.Paths.Map() {
		for method := range item.Operations() {
			fromSpec[method+" "+path] = true
		}
	}

	if missing := difference(fromRouter, fromSpec); len(missing) > 0 {
		t.Errorf("라우터에 있는데 API 목록에 없다(api/openapi.yaml 에 더한다): %v", missing)
	}
	if extra := difference(fromSpec, fromRouter); len(extra) > 0 {
		t.Errorf("API 목록에 있는데 라우터에 없다: %v", extra)
	}
}

// openAPIPath 는 gin 의 주소 틀(/orders/:id)을 OpenAPI 의 모양(/orders/{id})으로 바꾼다.
func openAPIPath(path string) string {
	parts := strings.Split(path, "/")
	for i, part := range parts {
		if strings.HasPrefix(part, ":") {
			parts[i] = "{" + strings.TrimPrefix(part, ":") + "}"
		}
	}
	return strings.Join(parts, "/")
}

// difference 는 a 에만 있는 것들이다. 이름 차례다.
func difference(a, b map[string]bool) []string {
	var only []string
	for key := range a {
		if !b[key] {
			only = append(only, key)
		}
	}
	sort.Strings(only)
	return only
}
