// billing-server/internal/httpapi/router_test.go

package httpapi_test

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// TestMain 은 이 패키지의 테스트를 돌리기 전에 gin 을 조용하게 맞춘다.
// 요청 기록과 패닉의 호출 기록을 화면에 찍지 않는다. 테스트의 결과가 그 사이에 묻히지 않게 한다.
// gin 은 라우터를 만들 때 이 값을 읽으므로 라우터를 만들기 전에 정한다.
func TestMain(m *testing.M) {
	httpapi.SetMode(false)
	gin.DefaultWriter = io.Discard
	gin.DefaultErrorWriter = io.Discard
	os.Exit(m.Run())
}

// fakeDB 는 정해 둔 대로 답하는 가짜 DB 다. 준비 상태 확인이 받은 context 도 적어 둔다.
type fakeDB struct {
	err      error
	deadline time.Duration
	called   int
}

func (f *fakeDB) Ping(ctx context.Context) error {
	f.called++
	if limit, ok := ctx.Deadline(); ok {
		f.deadline = time.Until(limit)
	}
	return f.err
}

// get 은 라우터에 GET 요청을 보내고 응답을 돌려준다. 실제 포트를 열지 않는다.
func get(t *testing.T, db database.Pinger, path string) *httptest.ResponseRecorder {
	t.Helper()
	router := httpapi.NewRouter(httpapi.Dependencies{DB: db})
	response := httptest.NewRecorder()
	router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))
	return response
}

func TestHealthAnswersWithoutTheDatabase(t *testing.T) {
	db := &fakeDB{err: errors.New("db is down")}

	response := get(t, db, "/health")

	if response.Code != http.StatusOK {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
	if got := strings.TrimSpace(response.Body.String()); got != `{"status":"ok"}` {
		t.Errorf("본문 = %s", got)
	}
	// DB 가 죽어도 프로세스는 살아 있다고 답한다. DB 에 묻지도 않는다
	if db.called != 0 {
		t.Errorf("DB 를 %d번 불렀다. 부르지 않아야 한다", db.called)
	}
}

func TestReadinessIsOkWhenTheDatabaseAnswers(t *testing.T) {
	db := &fakeDB{}

	response := get(t, db, "/health/ready")

	if response.Code != http.StatusOK {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
	if got := strings.TrimSpace(response.Body.String()); got != `{"status":"ok"}` {
		t.Errorf("본문 = %s", got)
	}
	if db.called != 1 {
		t.Errorf("DB 를 %d번 불렀다. 한 번이어야 한다", db.called)
	}
}

func TestReadinessIsUnavailableWhenTheDatabaseFails(t *testing.T) {
	const secret = "password=do-not-print-me host=10.0.0.7"
	db := &fakeDB{err: errors.New(secret)}

	response := get(t, db, "/health/ready")

	if response.Code != http.StatusServiceUnavailable {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusServiceUnavailable)
	}
	// 실패한 이유를 싣지 않는다. 드라이버의 오류에는 주소와 계정 이름이 들어 있을 수 있다
	if got := strings.TrimSpace(response.Body.String()); got != `{"status":"unavailable"}` {
		t.Errorf("본문 = %s", got)
	}
}

func TestReadinessGivesTheDatabaseALimitedTime(t *testing.T) {
	db := &fakeDB{}

	get(t, db, "/health/ready")

	// 제한이 없으면 멈춘 DB 를 확인하는 요청이 끝나지 않는다
	if db.deadline <= 0 || db.deadline > httpapi.ReadinessTimeout {
		t.Errorf("DB 에 준 시간 = %v, 0 보다 크고 %v 이하여야 한다", db.deadline, httpapi.ReadinessTimeout)
	}
}

func TestReadinessWithTheRealDatabase(t *testing.T) {
	pool, err := database.NewPool(context.Background(), testenv.DatabaseURL(t), config.DefaultSchema)
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	defer pool.Close()

	response := get(t, pool, "/health/ready")

	if response.Code != http.StatusOK {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
}

func TestUnknownPathIsNotFound(t *testing.T) {
	response := get(t, &fakeDB{}, httpapi.APIPrefix+"/nothing-here")

	if response.Code != http.StatusNotFound {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusNotFound)
	}
}

func TestPanicBecomesInternalServerError(t *testing.T) {
	// 준비 상태 확인이 부르는 DB 가 패닉을 내도 서버가 죽지 않는다
	response := get(t, panickingDB{}, "/health/ready")

	if response.Code != http.StatusInternalServerError {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusInternalServerError)
	}
}

// panickingDB 는 부르면 패닉을 내는 가짜 DB 다.
type panickingDB struct{}

func (panickingDB) Ping(context.Context) error {
	panic("boom")
}
