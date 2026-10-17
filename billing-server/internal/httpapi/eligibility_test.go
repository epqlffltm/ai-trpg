// billing-server/internal/httpapi/eligibility_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const eligibilityURL = httpapi.APIPrefix + "/service/eligibility"

// fakeRecorder 는 정해 둔 대로 답하는 가짜다. 받은 것을 적어 둔다.
type fakeRecorder struct {
	outcome eligibility.Outcome
	err     error

	calls  int
	update eligibility.Update
}

func (f *fakeRecorder) Apply(_ context.Context, update eligibility.Update) (eligibility.Outcome, error) {
	f.calls++
	f.update = update
	return f.outcome, f.err
}

func eligibilityDeps(recorder httpapi.EligibilityRecorder) httpapi.Dependencies {
	return httpapi.Dependencies{
		Eligibility: recorder, AuthServerSecret: authSecret, GameServerSecret: gameSecret, WebhookSecret: webhookSecret,
		Now: func() time.Time { return webhookNow },
	}
}

// reportAs 는 그 비밀을 가진 서버가 서명해 결제 자격을 보낸 것처럼 요청한다.
func reportAs(t *testing.T, deps httpapi.Dependencies, secret string, text string) (int, string) {
	t.Helper()
	response := send(t, deps, request{
		method: http.MethodPost, path: eligibilityURL, body: text, anonymous: true,
		headers: signedBy(secret, eligibilityURL, text),
	})
	return response.Code, body(response)
}

func TestEligibilityIsRecordedAsSent(t *testing.T) {
	recorder := &fakeRecorder{outcome: eligibility.Applied}
	text := `{"user_id":"` + testenv.UserID + `","version":3,"legal_adult_from":"2029-06-01","guardian_consent":true}`

	status, got := reportAs(t, eligibilityDeps(recorder), authSecret, text)

	if status != http.StatusOK || got != `{"status":"applied"}` {
		t.Fatalf("상태 코드 = %d, 본문 = %s", status, got)
	}
	day := time.Date(2029, 6, 1, 0, 0, 0, 0, time.UTC)
	if recorder.update.UserID.String() != testenv.UserID || recorder.update.Version != 3 ||
		recorder.update.LegalAdultFrom == nil || !recorder.update.LegalAdultFrom.Equal(day) || !recorder.update.GuardianConsent {
		t.Errorf("받은 상태 = %+v", recorder.update)
	}
}

func TestAnAdultIsSentWithoutADate(t *testing.T) {
	recorder := &fakeRecorder{outcome: eligibility.Applied}
	text := `{"user_id":"` + testenv.UserID + `","version":1,"legal_adult_from":null,"guardian_consent":false}`

	status, _ := reportAs(t, eligibilityDeps(recorder), authSecret, text)

	if status != http.StatusOK || recorder.update.LegalAdultFrom != nil {
		t.Errorf("상태 코드 = %d, 날짜 = %v. 성년은 날짜가 없다", status, recorder.update.LegalAdultFrom)
	}
}

func TestAStaleVersionIsFinishedToo(t *testing.T) {
	text := `{"user_id":"` + testenv.UserID + `","version":1,"legal_adult_from":null,"guardian_consent":false}`

	status, got := reportAs(t, eligibilityDeps(&fakeRecorder{outcome: eligibility.Stale}), authSecret, text)

	if status != http.StatusOK || got != `{"status":"stale"}` {
		t.Errorf("상태 코드 = %d, 본문 = %s", status, got)
	}
}

func TestOnlyTheAuthServerMayReportEligibility(t *testing.T) {
	// 게임 서버의 서명이나 사용자의 토큰으로는 보호자 동의를 꾸며 넣을 수 없다
	recorder := &fakeRecorder{outcome: eligibility.Applied}
	text := `{"user_id":"` + testenv.UserID + `","version":1,"legal_adult_from":null,"guardian_consent":true}`

	gameStatus, _ := reportAs(t, eligibilityDeps(recorder), gameSecret, text)
	user := send(t, eligibilityDeps(recorder), request{method: http.MethodPost, path: eligibilityURL, body: text})

	if gameStatus != http.StatusUnauthorized || user.Code != http.StatusUnauthorized || recorder.calls != 0 {
		t.Errorf("게임 서버 = %d, 사용자 = %d, 적은 수 = %d", gameStatus, user.Code, recorder.calls)
	}
}

func TestABadEligibilityBodyIsRefused(t *testing.T) {
	user := `"user_id":"` + testenv.UserID + `"`
	bodies := map[string]string{
		"JSON 이 아니다":        `nope`,
		"버전이 없다":            `{` + user + `,"legal_adult_from":null,"guardian_consent":false}`,
		"동의가 없다":            `{` + user + `,"version":1,"legal_adult_from":null}`,
		"날짜의 모양이 틀렸다":       `{` + user + `,"version":1,"legal_adult_from":"2029/06/01","guardian_consent":false}`,
		"버전이 0 이다(서비스가 거절)": `{` + user + `,"version":0,"legal_adult_from":null,"guardian_consent":false}`,
	}
	for name, text := range bodies {
		t.Run(name, func(t *testing.T) {
			recorder := &fakeRecorder{err: eligibility.ErrInvalidUpdate}

			status, got := reportAs(t, eligibilityDeps(recorder), authSecret, text)

			if status != http.StatusBadRequest || !strings.Contains(got, `"code":"eligibility.invalid_request"`) {
				t.Errorf("상태 코드 = %d, 본문 = %s", status, got)
			}
		})
	}
}

func TestAnEligibilityFailureIsAServerError(t *testing.T) {
	text := `{"user_id":"` + testenv.UserID + `","version":1,"legal_adult_from":null,"guardian_consent":false}`

	status, got := reportAs(t, eligibilityDeps(&fakeRecorder{err: errors.New(`relation "payment_eligibility" does not exist`)}), authSecret, text)

	if status != http.StatusInternalServerError || strings.Contains(got, "relation") {
		t.Errorf("상태 코드 = %d, 본문 = %s", status, got)
	}
}

func TestPaymentRefusalsCarryACodeForTheScreen(t *testing.T) {
	// 화면이 본인인증으로 보낼지, 보호자 동의로 보낼지 가른다
	cases := map[error]string{
		eligibility.ErrVerificationRequired:    `"code":"payment.verification_required"`,
		eligibility.ErrGuardianConsentRequired: `"code":"payment.guardian_consent_required"`,
	}
	for err, want := range cases {
		response := send(t, httpapi.Dependencies{Orders: &fakeOrders{err: err}}, request{
			method: http.MethodPost, path: ordersURL, body: `{"product_id":"credits-1000"}`,
		})
		if response.Code != http.StatusForbidden || !strings.Contains(body(response), want) {
			t.Errorf("%v: 상태 코드 = %d, 본문 = %s", err, response.Code, body(response))
		}
	}
}
