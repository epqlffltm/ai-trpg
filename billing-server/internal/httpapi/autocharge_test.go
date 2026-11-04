// billing-server/internal/httpapi/autocharge_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

var (
	autoChargeURL  = httpapi.APIPrefix + "/auto-charge"
	cardsURL       = httpapi.APIPrefix + "/cards"
	customerKeyURL = httpapi.APIPrefix + "/cards/customer-key"
)

var registeredAt = time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC)

// fakeAutoCharge 는 정해 둔 대로 답하는 가짜 자동 충전이다. 받은 것을 적어 둔다.
type fakeAutoCharge struct {
	view        autocharge.View
	err         error
	user        uuid.UUID
	settings    autocharge.Settings
	agreedTerms int
	authKey     string
	key         uuid.UUID
	removed     bool
}

func (f *fakeAutoCharge) Get(_ context.Context, userID uuid.UUID) (autocharge.View, error) {
	f.user = userID
	return f.view, f.err
}

func (f *fakeAutoCharge) Update(_ context.Context, userID uuid.UUID, settings autocharge.Settings, agreedTerms int) (autocharge.View, error) {
	f.user, f.settings, f.agreedTerms = userID, settings, agreedTerms
	return f.view, f.err
}

func (f *fakeAutoCharge) CustomerKey(_ context.Context, userID uuid.UUID) (uuid.UUID, error) {
	f.user = userID
	return uuid.MustParse("6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11"), f.err
}

func (f *fakeAutoCharge) RegisterCard(_ context.Context, userID uuid.UUID, authKey string, key uuid.UUID) (autocharge.Card, error) {
	f.user, f.authKey, f.key = userID, authKey, key
	return autocharge.Card{IssuerCode: "61", Number: "43301234****123*", RegisteredAt: registeredAt}, f.err
}

func (f *fakeAutoCharge) RemoveCard(_ context.Context, userID uuid.UUID) error {
	f.user, f.removed = userID, true
	return f.err
}

// autoChargeCall 은 자동 충전의 주소에 토큰을 붙여 요청을 보낸다.
func autoChargeCall(t *testing.T, service httpapi.AutoChargeService, method, url, payload string) *httptest.ResponseRecorder {
	t.Helper()
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier, AutoCharge: service})
	request := httptest.NewRequest(method, url, strings.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer the-token")
	return serve(t, router, request)
}

const goodSettings = `{"enabled":true,"threshold":"500","product_id":"credits-5000","monthly_limit":30000,"terms_version":1}`

func TestAutoChargeShowsSettingsAndCardWithoutTheBillingKey(t *testing.T) {
	service := &fakeAutoCharge{view: autocharge.View{
		Settings:            &autocharge.Settings{Enabled: true, Threshold: 500, ProductID: "credits-5000", MonthlyLimit: 30_000},
		ConsecutiveFailures: 1,
		Card:                &autocharge.Card{IssuerCode: "61", Number: "43301234****123*", RegisteredAt: registeredAt},
		AgreedTermsVersion:  1,
	}}

	response := autoChargeCall(t, service, http.MethodGet, autoChargeURL, "")

	want := `{"settings":{"enabled":true,"threshold":"500","product_id":"credits-5000","monthly_limit":30000},` +
		`"consecutive_failures":1,"card":{"issuer_code":"61","number":"43301234****123*","registered_at":"2026-11-10T03:00:00Z"},` +
		`"terms":{"version":1,"agreed_version":1}}`
	if response.Code != http.StatusOK || response.Body.String() != want || service.user.String() != testenv.UserID {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestNothingYetIsNulls(t *testing.T) {
	response := autoChargeCall(t, &fakeAutoCharge{}, http.MethodGet, autoChargeURL, "")

	if response.Body.String() != `{"settings":null,"consecutive_failures":0,"card":null,"terms":{"version":1,"agreed_version":null}}` {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestSettingsArePassedOn(t *testing.T) {
	service := &fakeAutoCharge{}

	response := autoChargeCall(t, service, http.MethodPut, autoChargeURL, goodSettings)

	want := autocharge.Settings{Enabled: true, Threshold: 500, ProductID: "credits-5000", MonthlyLimit: 30_000}
	if response.Code != http.StatusOK || service.settings != want || service.agreedTerms != 1 {
		t.Errorf("%d, 받은 설정 = %+v, 동의한 판 = %d", response.Code, service.settings, service.agreedTerms)
	}
}

func TestSettingErrorsHaveCodes(t *testing.T) {
	for name, tc := range map[string]struct {
		payload string
		err     error
		status  int
		code    string
	}{
		"JSON 이 아니다":   {"nope", nil, http.StatusBadRequest, "autocharge.invalid_settings"},
		"기준이 양이 아니다":   {`{"enabled":true,"threshold":"1e3","product_id":"credits-5000","monthly_limit":30000}`, nil, http.StatusBadRequest, "autocharge.invalid_settings"},
		"값이 틀렸다":       {goodSettings, autocharge.ErrInvalidSettings, http.StatusBadRequest, "autocharge.invalid_settings"},
		"카드가 없다":       {goodSettings, autocharge.ErrNoCard, http.StatusConflict, "autocharge.no_card"},
		"동의하지 않았다":     {goodSettings, autocharge.ErrTermsRequired, http.StatusBadRequest, "autocharge.terms_required"},
		"옛 판에 동의했다":    {goodSettings, autocharge.ErrTermsOutdated, http.StatusConflict, "autocharge.terms_outdated"},
		"본인인증 전":       {goodSettings, eligibility.ErrVerificationRequired, http.StatusForbidden, "payment.verification_required"},
		"보호자 동의가 없다":   {goodSettings, eligibility.ErrGuardianConsentRequired, http.StatusForbidden, "payment.guardian_consent_required"},
		"DB 가 답하지 않는다": {goodSettings, errors.New("boom"), http.StatusInternalServerError, ""},
	} {
		response := autoChargeCall(t, &fakeAutoCharge{err: tc.err}, http.MethodPut, autoChargeURL, tc.payload)

		if response.Code != tc.status || (tc.code != "" && !strings.Contains(response.Body.String(), `"code":"`+tc.code+`"`)) {
			t.Errorf("%s: %d %s", name, response.Code, response.Body.String())
		}
	}
}

func TestTheCustomerKeyIsGiven(t *testing.T) {
	response := autoChargeCall(t, &fakeAutoCharge{}, http.MethodPost, customerKeyURL, "")

	if response.Code != http.StatusOK || response.Body.String() != `{"customer_key":"6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11"}` {
		t.Errorf("%d %s", response.Code, response.Body.String())
	}
}

func TestACardIsRegistered(t *testing.T) {
	service := &fakeAutoCharge{}

	response := autoChargeCall(t, service, http.MethodPost, cardsURL,
		`{"auth_key":"bln_123","customer_key":"6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11"}`)

	if response.Code != http.StatusCreated || service.authKey != "bln_123" || service.key.String() != "6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11" {
		t.Errorf("%d %s, 받은 것 = %q %v", response.Code, response.Body.String(), service.authKey, service.key)
	}
	if strings.Contains(response.Body.String(), "billing") {
		t.Errorf("빌링키를 실었다: %s", response.Body.String())
	}
}

func TestCardErrorsHaveCodesAndHideTheProviderReason(t *testing.T) {
	good := `{"auth_key":"bln_123","customer_key":"6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11"}`
	for name, tc := range map[string]struct {
		payload string
		err     error
		status  int
		code    string
	}{
		"고객 키가 틀린 모양":     {`{"auth_key":"bln_123","customer_key":"nope"}`, nil, http.StatusBadRequest, "card.invalid_request"},
		"인증 키가 틀렸다":       {good, autocharge.ErrInvalidAuthKey, http.StatusBadRequest, "card.invalid_request"},
		"남의 고객 키":         {good, autocharge.ErrCustomerKeyMismatch, http.StatusConflict, "card.customer_key_mismatch"},
		"결제 대행사가 거절했다":    {good, &payment.RefusedError{Code: "SECRET_REASON"}, http.StatusUnprocessableEntity, "card.refused"},
		"결제 대행사가 답하지 않았다": {good, autocharge.ErrIssuerUnavailable, http.StatusServiceUnavailable, "card.issuer_unavailable"},
	} {
		response := autoChargeCall(t, &fakeAutoCharge{err: tc.err}, http.MethodPost, cardsURL, tc.payload)

		if response.Code != tc.status || !strings.Contains(response.Body.String(), `"code":"`+tc.code+`"`) ||
			strings.Contains(response.Body.String(), "SECRET_REASON") {
			t.Errorf("%s: %d %s", name, response.Code, response.Body.String())
		}
	}
}

func TestRemovingTheCardIsNoContent(t *testing.T) {
	service := &fakeAutoCharge{}

	response := autoChargeCall(t, service, http.MethodDelete, cardsURL, "")

	if response.Code != http.StatusNoContent || !service.removed {
		t.Errorf("%d, 지웠나 = %v", response.Code, service.removed)
	}
}

func TestWithoutTheServiceTheRoutesAreClosed(t *testing.T) {
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier})
	request := httptest.NewRequest(http.MethodGet, autoChargeURL, nil)
	request.Header.Set("Authorization", "Bearer the-token")
	response := httptest.NewRecorder()

	router.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Errorf("%d", response.Code)
	}
}
