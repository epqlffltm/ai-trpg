// billing-server/internal/httpapi/coupons_test.go

package httpapi_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const redeemURL = httpapi.APIPrefix + "/coupons/redeem"

// fakeCoupons 는 정해 둔 대로 답하는 가짜 쿠폰이다. 누가 무엇을 넣었는지 적어 둔다.
type fakeCoupons struct {
	redemption coupon.Redemption
	err        error
	user       uuid.UUID
	code       string
}

func (f *fakeCoupons) Redeem(_ context.Context, userID uuid.UUID, code string) (coupon.Redemption, error) {
	f.user, f.code = userID, code
	return f.redemption, f.err
}

// redeemCall 은 쿠폰을 넣는 요청을 보낸다. token 이 true 면 testenv.UserID 의 토큰을 붙인다.
func redeemCall(t *testing.T, service httpapi.CouponRedeemer, payload string, token bool) *httptest.ResponseRecorder {
	t.Helper()
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier, Coupons: service})
	request := httptest.NewRequest(http.MethodPost, redeemURL, strings.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	if token {
		request.Header.Set("Authorization", "Bearer the-token")
	}
	return serve(t, router, request)
}

func TestRedeemingNeedsAToken(t *testing.T) {
	service := &fakeCoupons{}

	response := redeemCall(t, service, `{"code":"LAUNCH"}`, false)

	if response.Code != http.StatusUnauthorized || service.code != "" {
		t.Fatalf("토큰 없이 = %d, 부른 코드 = %q", response.Code, service.code)
	}
}

func TestRedeemingGivesTheTokenOwnerTheSilver(t *testing.T) {
	expires := time.Date(2026, 12, 10, 3, 0, 0, 0, time.UTC)
	service := &fakeCoupons{redemption: coupon.Redemption{Code: "LAUNCH-2026", Silver: 300, ExpiresAt: expires}}

	response := redeemCall(t, service, `{"code":" launch-2026 "}`, true)

	want := `{"code":"LAUNCH-2026","silver":"300","expires_at":"2026-12-10T03:00:00Z"}`
	if response.Code != http.StatusCreated || body(response) != want {
		t.Fatalf("받기 = %d %s, 기대 = 201 %s", response.Code, body(response), want)
	}
	if service.user != mustUUID(t, testenv.UserID) || service.code != " launch-2026 " {
		t.Fatalf("부른 것 = %s %q. 토큰의 주인과 넣은 글 그대로여야 한다", service.user, service.code)
	}
}

func TestRedeemingFailuresHaveCodes(t *testing.T) {
	cases := []struct {
		err    error
		status int
		code   string
	}{
		{coupon.ErrNotFound, http.StatusNotFound, "coupon.not_found"},
		{coupon.ErrVerificationRequired, http.StatusForbidden, "coupon.verification_required"},
		{coupon.ErrAlreadyRedeemed, http.StatusConflict, "coupon.already_redeemed"},
		{coupon.ErrExhausted, http.StatusConflict, "coupon.exhausted"},
		{coupon.ErrEnded, http.StatusConflict, "coupon.ended"},
		{coupon.ErrStopped, http.StatusConflict, "coupon.ended"},
		{coupon.ErrNotStarted, http.StatusConflict, "coupon.not_started"},
	}
	for _, tc := range cases {
		response := redeemCall(t, &fakeCoupons{err: tc.err}, `{"code":"LAUNCH"}`, true)
		if response.Code != tc.status || !strings.Contains(body(response), `"code":"`+tc.code+`"`) {
			t.Errorf("%v = %d %s, 기대 = %d %s", tc.err, response.Code, body(response), tc.status, tc.code)
		}
	}
}

func TestTooManyWrongCodesSayWhenToTryAgain(t *testing.T) {
	service := &fakeCoupons{err: &coupon.TooManyAttemptsError{RetryAfter: 90*time.Second + time.Millisecond}}

	response := redeemCall(t, service, `{"code":"LAUNCH"}`, true)

	if response.Code != http.StatusTooManyRequests || response.Header().Get("Retry-After") != "91" {
		t.Fatalf("너무 자주 = %d, Retry-After %q. 429 와 올림한 91 이어야 한다", response.Code, response.Header().Get("Retry-After"))
	}
	if !strings.Contains(body(response), `"code":"coupon.too_many_attempts"`) {
		t.Fatalf("본문 = %s", body(response))
	}
}

func TestRedeemingNeedsAJSONBody(t *testing.T) {
	service := &fakeCoupons{}

	response := redeemCall(t, service, `not json`, true)

	if response.Code != http.StatusBadRequest || service.code != "" {
		t.Fatalf("JSON 이 아닌 본문 = %d, 부른 코드 = %q", response.Code, service.code)
	}
}
