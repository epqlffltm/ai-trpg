// billing-server/internal/httpapi/stepup_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/stepup"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// 민감한 작업 앞의 본인 확인(stepup.go). 청약철회와 카드 셋(고객 키, 등록, 지우기)에만 붙고,
// 창이 열렸으면 하고, 닫혔으면 403 step_up.required, 끈 사람은 카드만 하고 철회는 403 step_up.disabled,
// 인증 서버에 묻지 못하면 503 이다. 묻는 것에는 토큰의 sub 와 sid 를 넘긴다.

type fakeStepUp struct {
	state   stepup.State
	err     error
	calls   int
	user    uuid.UUID
	session string
}

func (f *fakeStepUp) Check(_ context.Context, userID uuid.UUID, sessionID string) (stepup.State, error) {
	f.calls++
	f.user, f.session = userID, sessionID
	return f.state, f.err
}

const stepUpSession = "0123456789abcdef0123456789abcdef"

// stepUpCall 은 세션이 실린 토큰으로 요청을 보낸다.
func stepUpCall(t *testing.T, deps httpapi.Dependencies, method, path string) *httptest.ResponseRecorder {
	t.Helper()
	deps.DB = &fakeDB{}
	deps.Verifier = &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, testenv.UserID), SessionID: stepUpSession}}
	router := httpapi.NewRouter(deps)
	request := httptest.NewRequest(method, path, strings.NewReader(`{"auth_key":"a","customer_key":"`+uuid.NewString()+`"}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer the-token")
	return serve(t, router, request)
}

func refundPath() string { return ordersURL + "/" + orderID + "/refund" }

func TestAnOpenWindowLetsTheSensitiveActionsThrough(t *testing.T) {
	gate := &fakeStepUp{state: stepup.Open}
	orders := &fakeOrders{order: sampleOrder(t, order.StatusRefunding)}
	cards := &fakeAutoCharge{}
	deps := httpapi.Dependencies{StepUp: gate, Orders: orders, AutoCharge: cards}

	refund := stepUpCall(t, deps, http.MethodPost, refundPath())
	key := stepUpCall(t, deps, http.MethodPost, customerKeyURL)
	removed := stepUpCall(t, deps, http.MethodDelete, cardsURL)

	if refund.Code != http.StatusAccepted || key.Code != http.StatusOK || removed.Code != http.StatusNoContent {
		t.Fatalf("철회 %d, 고객 키 %d, 지우기 %d", refund.Code, key.Code, removed.Code)
	}
	if gate.calls != 3 || gate.user.String() != testenv.UserID || gate.session != stepUpSession {
		t.Errorf("물은 것 = %d번, %v, %q", gate.calls, gate.user, gate.session)
	}
	if orders.calls != 1 || !cards.removed {
		t.Errorf("작업이 돌지 않았다: 철회 %d번, 카드 지움 %v", orders.calls, cards.removed)
	}
}

func TestAClosedWindowAsksForTheCheckFirst(t *testing.T) {
	orders := &fakeOrders{order: sampleOrder(t, order.StatusRefunding)}
	cards := &fakeAutoCharge{}
	deps := httpapi.Dependencies{StepUp: &fakeStepUp{state: stepup.Required}, Orders: orders, AutoCharge: cards}

	for _, call := range []struct{ method, path string }{
		{http.MethodPost, refundPath()}, {http.MethodPost, customerKeyURL}, {http.MethodPost, cardsURL}, {http.MethodDelete, cardsURL},
	} {
		response := stepUpCall(t, deps, call.method, call.path)
		if response.Code != http.StatusForbidden || !strings.Contains(body(response), `"code":"step_up.required"`) {
			t.Errorf("%s %s = %d %s", call.method, call.path, response.Code, body(response))
		}
	}
	if orders.calls != 0 || cards.removed || cards.authKey != "" {
		t.Errorf("확인 없이 작업이 돌았다")
	}
}

func TestADisabledUserManagesCardsButCannotRefundOnScreen(t *testing.T) {
	orders := &fakeOrders{order: sampleOrder(t, order.StatusRefunding)}
	cards := &fakeAutoCharge{}
	deps := httpapi.Dependencies{StepUp: &fakeStepUp{state: stepup.Disabled}, Orders: orders, AutoCharge: cards}

	removed := stepUpCall(t, deps, http.MethodDelete, cardsURL)
	refund := stepUpCall(t, deps, http.MethodPost, refundPath())

	if removed.Code != http.StatusNoContent || !cards.removed {
		t.Errorf("카드 지우기 = %d", removed.Code)
	}
	if refund.Code != http.StatusForbidden || !strings.Contains(body(refund), `"code":"step_up.disabled"`) || orders.calls != 0 {
		t.Errorf("철회 = %d %s", refund.Code, body(refund))
	}
}

func TestWhenTheAuthServerDoesNotAnswerItIsUnavailable(t *testing.T) {
	orders := &fakeOrders{order: sampleOrder(t, order.StatusRefunding)}
	gate := &fakeStepUp{err: errors.Join(stepup.ErrUnavailable, errors.New("닿지 못했다"))}

	response := stepUpCall(t, httpapi.Dependencies{StepUp: gate, Orders: orders}, http.MethodPost, refundPath())

	if response.Code != http.StatusServiceUnavailable || strings.Contains(body(response), `"code"`) || orders.calls != 0 {
		t.Errorf("%d %s", response.Code, body(response))
	}
}

func TestOrdinaryActionsDoNotAsk(t *testing.T) {
	gate := &fakeStepUp{state: stepup.Required}
	cards := &fakeAutoCharge{}

	response := stepUpCall(t, httpapi.Dependencies{StepUp: gate, AutoCharge: cards}, http.MethodGet, autoChargeURL)

	if response.Code != http.StatusOK || gate.calls != 0 {
		t.Errorf("자동 충전 보기 = %d, 물은 수 = %d", response.Code, gate.calls)
	}
}
