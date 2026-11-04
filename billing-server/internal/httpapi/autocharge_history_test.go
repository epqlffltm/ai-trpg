// billing-server/internal/httpapi/autocharge_history_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

var autoChargeHistoryURL = httpapi.APIPrefix + "/auto-charge/history"

// fakeAutoChargeHistory 는 정해 둔 내역을 돌려주는 가짜다. 누구의 것을 읽었는지 적어 둔다.
type fakeAutoChargeHistory struct {
	items []autocharge.HistoryItem
	err   error
	user  uuid.UUID
}

func (f *fakeAutoChargeHistory) History(_ context.Context, userID uuid.UUID) ([]autocharge.HistoryItem, error) {
	f.user = userID
	return f.items, f.err
}

// autoChargeHistoryCall 은 최근 내역의 주소에 토큰을 붙여 요청을 보낸다.
func autoChargeHistoryCall(t *testing.T, history httpapi.AutoChargeHistory) *httptest.ResponseRecorder {
	t.Helper()
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier, AutoChargeHistory: history})
	request := httptest.NewRequest(http.MethodGet, autoChargeHistoryURL, nil)
	request.Header.Set("Authorization", "Bearer the-token")
	return serve(t, router, request)
}

func TestAutoChargeHistoryShowsEachRequestOfTheTokenOwner(t *testing.T) {
	finished := registeredAt.Add(time.Minute)
	history := &fakeAutoChargeHistory{items: []autocharge.HistoryItem{
		{
			ID: uuid.MustParse("0b6f3c1e-7d2a-4c55-9a51-3c1d2e4f5a61"), ProductID: "credits-1000", Price: 1_000, Credits: 1_000,
			Status: autocharge.HistoryProcessing, CreatedAt: registeredAt.Add(time.Hour),
		},
		{
			ID: uuid.MustParse("1c7a4d2f-8e3b-4d66-8b62-4d2e3f5a6b72"), ProductID: "credits-1000", Price: 1_000, Credits: 1_000,
			Status: autocharge.HistorySkipped, Reason: autocharge.SkipMonthlyCap, CreatedAt: registeredAt, FinishedAt: &finished,
		},
		{
			ID: uuid.MustParse("2d8b5e3a-9f4c-4e77-9c73-5e3f4a6b7c83"), ProductID: "credits-5000", Price: 5_000, Credits: 5_500,
			Status: autocharge.HistoryDeclined, TurnedOff: true, CreatedAt: registeredAt, FinishedAt: &finished,
		},
	}}

	response := autoChargeHistoryCall(t, history)

	want := `{"items":[` +
		`{"id":"0b6f3c1e-7d2a-4c55-9a51-3c1d2e4f5a61","product_id":"credits-1000","price":1000,"credits":"1000","status":"processing",` +
		`"reason":null,"turned_off":false,"created_at":"2026-11-10T04:00:00Z","finished_at":null},` +
		`{"id":"1c7a4d2f-8e3b-4d66-8b62-4d2e3f5a6b72","product_id":"credits-1000","price":1000,"credits":"1000","status":"skipped",` +
		`"reason":"monthly_limit","turned_off":false,"created_at":"2026-11-10T03:00:00Z","finished_at":"2026-11-10T03:01:00Z"},` +
		`{"id":"2d8b5e3a-9f4c-4e77-9c73-5e3f4a6b7c83","product_id":"credits-5000","price":5000,"credits":"5500","status":"declined",` +
		`"reason":null,"turned_off":true,"created_at":"2026-11-10T03:00:00Z","finished_at":"2026-11-10T03:01:00Z"}]}`
	if response.Code != http.StatusOK || response.Body.String() != want || history.user.String() != testenv.UserID {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestAnEmptyAutoChargeHistoryIsAnEmptyList(t *testing.T) {
	response := autoChargeHistoryCall(t, &fakeAutoChargeHistory{})

	if response.Code != http.StatusOK || response.Body.String() != `{"items":[]}` {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestAutoChargeHistoryThatCannotBeReadIs500(t *testing.T) {
	response := autoChargeHistoryCall(t, &fakeAutoChargeHistory{err: errors.New("boom")})

	if response.Code != http.StatusInternalServerError {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestAutoChargeHistoryNeedsAToken(t *testing.T) {
	history := &fakeAutoChargeHistory{}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: &fakeVerifier{}, AutoChargeHistory: history})

	response := serve(t, router, httptest.NewRequest(http.MethodGet, autoChargeHistoryURL, nil))

	if response.Code != http.StatusUnauthorized || history.user != uuid.Nil {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestAutoChargeHistoryIsClosedWithoutTheService(t *testing.T) {
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: &fakeVerifier{}})

	response := serve(t, router, httptest.NewRequest(http.MethodGet, autoChargeHistoryURL, nil))

	if response.Code != http.StatusNotFound {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}
