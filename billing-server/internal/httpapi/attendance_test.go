// billing-server/internal/httpapi/attendance_test.go

package httpapi_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const (
	attendanceURL = httpapi.APIPrefix + "/attendance"
	rewardsURL    = httpapi.APIPrefix + "/attendance/rewards"
)

// fakeAttendance 는 정해 둔 대로 답하는 가짜 출석이다. 누구의 것을 물었는지 적어 둔다.
type fakeAttendance struct {
	status   attendance.Status
	claim    attendance.Claim
	err      error
	schedule attendance.Schedule
	chest    attendance.ChestTable
	user     uuid.UUID
}

func (f *fakeAttendance) Status(_ context.Context, userID uuid.UUID) (attendance.Status, error) {
	f.user = userID
	return f.status, f.err
}

func (f *fakeAttendance) Claim(_ context.Context, userID uuid.UUID) (attendance.Claim, error) {
	f.user = userID
	return f.claim, f.err
}

func (f *fakeAttendance) Rewards() (attendance.Schedule, attendance.ChestTable) {
	if f.schedule == nil {
		return attendance.DefaultSchedule(), attendance.ChestV1
	}
	return f.schedule, f.chest
}

// attendanceCall 은 출석의 주소에 요청을 보낸다. token 이 true 면 testenv.UserID 의 토큰을 붙인다.
func attendanceCall(t *testing.T, service httpapi.AttendanceService, method string, path string, token bool) *httptest.ResponseRecorder {
	t.Helper()
	return attendanceCallAs(t, service, method, path, token, mustUUID(t, testenv.UserID))
}

// attendanceCallAs 는 attendanceCall 과 같되 토큰의 주인을 고른다.
func attendanceCallAs(t *testing.T, service httpapi.AttendanceService, method string, path string, token bool, user uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	verifier := &fakeVerifier{claims: auth.Claims{UserID: user}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier, Attendance: service})
	request := httptest.NewRequest(method, path, nil)
	if token {
		request.Header.Set("Authorization", "Bearer the-token")
	}
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}

var koreanToday = time.Date(2026, 10, 18, 0, 0, 0, 0, time.UTC)

func TestAttendanceNeedsAToken(t *testing.T) {
	service := &fakeAttendance{}
	for _, method := range []string{http.MethodGet, http.MethodPost} {
		if response := attendanceCall(t, service, method, attendanceURL, false); response.Code != http.StatusUnauthorized {
			t.Errorf("%s 은 토큰이 없으면 401 이어야 하는데 %d 다", method, response.Code)
		}
	}
	if service.user != uuid.Nil {
		t.Fatal("토큰이 없으면 출석을 부르지 않아야 한다")
	}
}

func TestAttendanceStatusIsTheTokenOwners(t *testing.T) {
	service := &fakeAttendance{status: attendance.Status{
		Today: koreanToday, Verified: true, CycleDay: 7, Silver: 260, Chest: true,
	}}
	response := attendanceCall(t, service, http.MethodGet, attendanceURL, true)
	want := `{"today":"2026-10-18","verified":true,"claimed":false,"cycle_day":7,"cycle_length":7,"silver":"260","chest":true}`
	if response.Code != http.StatusOK || body(response) != want {
		t.Fatalf("상태 = %d %s, 기대 = 200 %s", response.Code, body(response), want)
	}
	if service.user != mustUUID(t, testenv.UserID) {
		t.Fatal("토큰의 주인의 것을 물어야 한다")
	}
}

func TestClaimWithoutAChestHasANullChest(t *testing.T) {
	expires := time.Date(2026, 11, 17, 3, 0, 0, 0, time.UTC)
	service := &fakeAttendance{claim: attendance.Claim{Day: koreanToday, CycleDay: 2, Silver: 160, ExpiresAt: expires}}
	response := attendanceCall(t, service, http.MethodPost, attendanceURL, true)
	want := `{"day":"2026-10-18","cycle_day":2,"silver":"160","chest":null,"expires_at":"2026-11-17T03:00:00Z"}`
	if response.Code != http.StatusCreated || body(response) != want {
		t.Fatalf("받기 = %d %s, 기대 = 201 %s", response.Code, body(response), want)
	}
}

func TestClaimWithAChestShowsWhatCameOut(t *testing.T) {
	dragon := attendance.ChestV1.Outcomes[5]
	service := &fakeAttendance{claim: attendance.Claim{
		Day: koreanToday, CycleDay: 7, Silver: 260,
		Chest: &attendance.ChestResult{Table: "v1", Outcome: dragon}, ExpiresAt: koreanToday,
	}}
	response := attendanceCall(t, service, http.MethodPost, attendanceURL, true)
	want := `"chest":{"table":"v1","outcome":"dragon_hoard","name":"용의 보물","silver":"5000"}`
	if response.Code != http.StatusCreated || !strings.Contains(body(response), want) {
		t.Fatalf("받기 = %d %s, 기대에 %s", response.Code, body(response), want)
	}
}

func TestClaimErrorsHaveCodes(t *testing.T) {
	cases := []struct {
		err    error
		status int
		code   string
	}{
		{attendance.ErrVerificationRequired, http.StatusForbidden, "attendance.verification_required"},
		{attendance.ErrAlreadyClaimed, http.StatusConflict, "attendance.already_claimed"},
	}
	for _, tc := range cases {
		response := attendanceCall(t, &fakeAttendance{err: tc.err}, http.MethodPost, attendanceURL, true)
		var parsed struct {
			Code   string `json:"code"`
			Detail string `json:"detail"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &parsed); err != nil || response.Code != tc.status ||
			parsed.Code != tc.code || parsed.Detail == "" {
			t.Errorf("%v: %d %s, 기대 = %d %s", tc.err, response.Code, body(response), tc.status, tc.code)
		}
	}
}

func TestAttendanceFailureIsAnInternalErrorWithoutTheCause(t *testing.T) {
	broken := errors.New("relation attendance_claims does not exist")
	for _, method := range []string{http.MethodGet, http.MethodPost} {
		response := attendanceCall(t, &fakeAttendance{err: broken}, method, attendanceURL, true)
		if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "attendance_claims") {
			t.Errorf("%s = %d %s, 기대 = 원인 없는 500", method, response.Code, body(response))
		}
	}
}

func TestRewardsArePublic(t *testing.T) {
	response := attendanceCall(t, &fakeAttendance{}, http.MethodGet, rewardsURL, false)
	if response.Code != http.StatusOK {
		t.Fatalf("토큰 없이 200 이어야 하는데 %d %s 다", response.Code, body(response))
	}
	if got := response.Header().Get("Cache-Control"); got != "public, max-age=300" {
		t.Errorf("Cache-Control = %q", got)
	}
	var parsed struct {
		Cycle []struct {
			Day    int    `json:"day"`
			Silver string `json:"silver"`
			Chest  bool   `json:"chest"`
		} `json:"cycle"`
		Chest struct {
			Table    string `json:"table"`
			Scale    int    `json:"scale"`
			Outcomes []struct {
				Outcome string `json:"outcome"`
				Name    string `json:"name"`
				Silver  string `json:"silver"`
				Chance  int    `json:"chance"`
				Percent string `json:"percent"`
			} `json:"outcomes"`
			ExpectedSilver string `json:"expected_silver"`
		} `json:"chest"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &parsed); err != nil {
		t.Fatalf("JSON 이 아니다: %v", err)
	}
	if len(parsed.Cycle) != 7 || parsed.Cycle[0].Silver != "140" || parsed.Cycle[0].Chest ||
		parsed.Cycle[6].Day != 7 || parsed.Cycle[6].Silver != "260" || !parsed.Cycle[6].Chest {
		t.Errorf("주기 = %+v", parsed.Cycle)
	}
	chest := parsed.Chest
	if chest.Table != "v1" || chest.Scale != 10000 || chest.ExpectedSilver != "617" || len(chest.Outcomes) != 6 {
		t.Fatalf("상자 = %+v", chest)
	}
	first, last := chest.Outcomes[0], chest.Outcomes[5]
	if first.Outcome != "mimic_bite" || first.Silver != "0" || first.Chance != 1000 || first.Percent != "10%" {
		t.Errorf("첫 결과 = %+v", first)
	}
	if last.Outcome != "dragon_hoard" || last.Name != "용의 보물" || last.Silver != "5000" || last.Percent != "3%" {
		t.Errorf("마지막 결과 = %+v", last)
	}
}

func TestRewardsWritePercentsWithoutTrailingZeros(t *testing.T) {
	table := attendance.ChestTable{Version: "v9", Outcomes: []attendance.Outcome{
		{ID: "a", Chance: 9_749}, {ID: "b", Chance: 250}, {ID: "c", Chance: 1},
	}}
	service := &fakeAttendance{schedule: attendance.Schedule{10}, chest: table}
	got := body(attendanceCall(t, service, http.MethodGet, rewardsURL, false))
	for _, want := range []string{`"percent":"97.49%"`, `"percent":"2.5%"`, `"percent":"0.01%"`, `"cycle":[{"day":1,"silver":"10","chest":true}]`} {
		if !strings.Contains(got, want) {
			t.Errorf("응답에 %s 이 없다: %s", want, got)
		}
	}
}

func TestAttendanceIsClosedWithoutTheService(t *testing.T) {
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier})
	for _, path := range []string{attendanceURL, rewardsURL} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.Header.Set("Authorization", "Bearer the-token")
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)
		if response.Code != http.StatusNotFound {
			t.Errorf("%s 는 404 여야 하는데 %d 다", path, response.Code)
		}
	}
}

func TestAttendanceWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않고 실제 서비스와 DB 로 받고 읽는다
	pool := testenv.Pool(t)
	now := func() time.Time { return time.Date(2026, 10, 18, 3, 0, 0, 0, time.UTC) }
	rules := config.Rules{FreeCreditTTL: time.Hour, HoldTTL: time.Hour, OrderTTL: time.Hour}
	services, err := app.NewServices(pool, rules, app.NoProviders(), now)
	if err != nil {
		t.Fatal(err)
	}
	service, err := attendance.NewService(pool, now, services.Wallet, services.Eligibility, attendance.Options{})
	if err != nil {
		t.Fatal(err)
	}
	// 다른 테스트와 겹치지 않게 새 사용자로 한다
	user := uuid.New()
	ctx := context.Background()
	if response := attendanceCallAs(t, service, http.MethodPost, attendanceURL, true, user); response.Code != http.StatusForbidden {
		t.Fatalf("본인인증 전에는 403 이어야 하는데 %d %s 다", response.Code, body(response))
	}
	if _, err := services.Eligibility.Apply(ctx, eligibility.Update{UserID: user, Version: 1}); err != nil {
		t.Fatal(err)
	}
	claimed := attendanceCallAs(t, service, http.MethodPost, attendanceURL, true, user)
	if claimed.Code != http.StatusCreated || !strings.Contains(body(claimed), `"cycle_day":1,"silver":"140","chest":null`) {
		t.Fatalf("받기 = %d %s", claimed.Code, body(claimed))
	}
	again := attendanceCallAs(t, service, http.MethodPost, attendanceURL, true, user)
	if again.Code != http.StatusConflict {
		t.Fatalf("두 번째는 409 여야 하는데 %d %s 다", again.Code, body(again))
	}
	status := attendanceCallAs(t, service, http.MethodGet, attendanceURL, true, user)
	want := `{"today":"2026-10-18","verified":true,"claimed":true,"cycle_day":1,"cycle_length":7,"silver":"140","chest":false}`
	if status.Code != http.StatusOK || body(status) != want {
		t.Fatalf("상태 = %d %s, 기대 = %s", status.Code, body(status), want)
	}
}
