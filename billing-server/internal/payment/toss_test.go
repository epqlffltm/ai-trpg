// billing-server/internal/payment/toss_test.go

// 토스페이먼츠의 승인과 조회를 시험한다. 실제 토스페이먼츠를 부르지 않는다.
// 문서에 적힌 모양으로 답하는 가짜 서버(httptest)를 띄우고, 그 답을 어떻게 판단하는지 본다.
package payment_test

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 두 결제 대행사 모두 주문이 아는 모양이다.
var (
	_ payment.Provider = payment.Fake{}
	_ payment.Provider = (*payment.Toss)(nil)
)

// tossSecret 은 시험에 쓰는 시크릿 키다. 실제 키가 아니다.
const tossSecret = "test_gsk_sandbox_0123456789abcdef"

// seen 은 가짜 토스페이먼츠가 받은 요청 하나다.
type seen struct {
	method, path, rawPath string
	header                http.Header
	body                  []byte
}

// fakeToss 는 정해 둔 답을 주는 가짜 토스페이먼츠다. 받은 요청을 적어 둔다.
type fakeToss struct {
	mu       sync.Mutex
	requests []seen
	status   int
	body     string
	// delay 가 있으면 그만큼 기다린 뒤 답한다
	delay time.Duration
}

func (f *fakeToss) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	f.mu.Lock()
	f.requests = append(f.requests, seen{method: r.Method, path: r.URL.Path, rawPath: r.URL.EscapedPath(), header: r.Header.Clone(), body: body})
	status, answer, delay := f.status, f.body, f.delay
	f.mu.Unlock()
	if delay > 0 {
		select {
		case <-time.After(delay):
		case <-r.Context().Done():
			return
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = io.WriteString(w, answer)
}

// last 는 마지막으로 받은 요청이다.
func (f *fakeToss) last(t *testing.T) seen {
	t.Helper()
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.requests) == 0 {
		t.Fatal("토스페이먼츠를 부르지 않았다")
	}
	return f.requests[len(f.requests)-1]
}

// startToss 는 가짜 토스페이먼츠를 띄우고, 그것을 부르는 Toss 를 돌려준다.
func startToss(t *testing.T, status int, body string) (*payment.Toss, *fakeToss, *httptest.Server) {
	t.Helper()
	fake := &fakeToss{status: status, body: body}
	server := httptest.NewServer(fake)
	t.Cleanup(server.Close)
	return payment.NewToss(tossSecret, server.URL, server.Client()), fake, server
}

// newRequest 는 시험의 승인 요청 하나를 만든다.
func newRequest() payment.Request {
	return payment.Request{PaymentKey: "tgen_" + strings.ReplaceAll(uuid.NewString(), "-", ""), OrderID: uuid.New(), Amount: 5000}
}

// paymentJSON 은 토스페이먼츠의 결제 한 건(Payment 객체)을 흉내 낸다. 쓰지 않는 칸도 몇 개 넣는다.
func paymentJSON(paymentKey string, orderID string, status string, amount int64) string {
	return fmt.Sprintf(`{"mId":"tgen_docs","version":"2022-11-16","paymentKey":%q,"orderId":%q,"orderName":"크레딧 5,000",`+
		`"status":%q,"totalAmount":%d,"balanceAmount":%d,"method":"카드","approvedAt":"2026-03-02T18:00:00+09:00"}`,
		paymentKey, orderID, status, amount, amount)
}

// matching 은 그 요청의 결제를 status 로 답하는 본문이다.
func matching(request payment.Request, status string) string {
	return paymentJSON(request.PaymentKey, request.OrderID.String(), status, request.Amount)
}

// errorJSON 은 토스페이먼츠의 오류 응답을 흉내 낸다.
func errorJSON(code string) string {
	return fmt.Sprintf(`{"code":%q,"message":"사람이 읽는 설명"}`, code)
}

func TestTossConfirmSendsTheDocumentedRequest(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	fake.body = matching(request, "DONE")

	if _, err := toss.Confirm(context.Background(), request); err != nil {
		t.Fatalf("승인 요청이 실패했다: %v", err)
	}

	got := fake.last(t)
	if got.method != http.MethodPost || got.path != "/v1/payments/confirm" {
		t.Errorf("요청 = %s %s, 기대 = POST /v1/payments/confirm", got.method, got.path)
	}
	// 시크릿 키 뒤에 콜론을 붙여 base64 로 바꾼다
	wantAuth := "Basic " + base64.StdEncoding.EncodeToString([]byte(tossSecret+":"))
	if auth := got.header.Get("Authorization"); auth != wantAuth {
		t.Errorf("Authorization = %q, 기대 = %q", auth, wantAuth)
	}
	if contentType := got.header.Get("Content-Type"); contentType != "application/json" {
		t.Errorf("Content-Type = %q", contentType)
	}
	// 멱등키는 주문 번호다. 같은 주문의 승인을 다시 보내면 처음의 답이 온다
	if key := got.header.Get("Idempotency-Key"); key != request.OrderID.String() {
		t.Errorf("Idempotency-Key = %q, 기대 = 주문 번호 %q", key, request.OrderID)
	}
	var body map[string]any
	if err := json.Unmarshal(got.body, &body); err != nil {
		t.Fatalf("본문이 JSON 이 아니다: %s", got.body)
	}
	want := map[string]any{"paymentKey": request.PaymentKey, "orderId": request.OrderID.String(), "amount": float64(request.Amount)}
	if fmt.Sprint(body) != fmt.Sprint(want) {
		t.Errorf("본문 = %v, 기대 = %v", body, want)
	}
}

func TestTossConfirmJudgesTheAnswer(t *testing.T) {
	approved := payment.Result{Status: payment.StatusApproved}
	pending := payment.Result{Status: payment.StatusPending}
	declined := func(code string) payment.Result { return payment.Result{Status: payment.StatusDeclined, Code: code} }
	other := newRequest()
	cases := []struct {
		name   string
		status int
		// body 는 요청을 받아 답의 본문을 만든다
		body func(payment.Request) string
		// want 는 기대하는 결과다. unknown 이면 결과 대신 ErrUnknownOutcome 이어야 한다
		want    payment.Result
		unknown bool
	}{
		{"승인", 200, func(r payment.Request) string { return matching(r, "DONE") }, approved, false},
		{"가상계좌는 입금 전이라 아직 모른다", 200, func(r payment.Request) string { return matching(r, "WAITING_FOR_DEPOSIT") }, pending, false},
		{"다른 주문의 결제", 200, func(r payment.Request) string {
			return paymentJSON(r.PaymentKey, other.OrderID.String(), "DONE", r.Amount)
		}, declined(payment.CodePaymentMismatch), false},
		{"금액이 다른 결제", 200, func(r payment.Request) string {
			return paymentJSON(r.PaymentKey, r.OrderID.String(), "DONE", r.Amount+1)
		}, declined(payment.CodePaymentMismatch), false},
		{"결제 번호가 다른 결제", 200, func(r payment.Request) string {
			return paymentJSON(other.PaymentKey, r.OrderID.String(), "DONE", r.Amount)
		}, declined(payment.CodePaymentMismatch), false},
		{"카드 거절", 403, func(payment.Request) string { return errorJSON("REJECT_CARD_PAYMENT") }, declined("REJECT_CARD_PAYMENT"), false},
		{"인증 뒤 시간이 지남", 404, func(payment.Request) string { return errorJSON("NOT_FOUND_PAYMENT_SESSION") }, declined("NOT_FOUND_PAYMENT_SESSION"), false},
		{"잘못된 요청", 400, func(payment.Request) string { return errorJSON("INVALID_REQUEST") }, declined("INVALID_REQUEST"), false},
		{"이미 처리된 결제", 400, func(payment.Request) string { return errorJSON("ALREADY_PROCESSED_PAYMENT") }, payment.Result{}, true},
		{"처리 중", 400, func(payment.Request) string { return errorJSON("ALREADY_PROCESSING_REQUEST") }, payment.Result{}, true},
		{"일시적인 오류", 400, func(payment.Request) string { return errorJSON("PROVIDER_ERROR") }, payment.Result{}, true},
		{"너무 잦은 요청", 403, func(payment.Request) string { return errorJSON("FORBIDDEN_CONSECUTIVE_REQUEST") }, payment.Result{}, true},
		{"우리 키가 틀림", 401, func(payment.Request) string { return errorJSON("UNAUTHORIZED_KEY") }, payment.Result{}, true},
		{"401 은 코드와 상관없이 모름", 401, func(payment.Request) string { return errorJSON("SOMETHING_NEW") }, payment.Result{}, true},
		{"Basic 인증의 모양이 틀림", 403, func(payment.Request) string { return errorJSON("INCORRECT_BASIC_AUTH_FORMAT") }, payment.Result{}, true},
		{"멱등 요청을 처리 중", 409, func(payment.Request) string { return errorJSON("IDEMPOTENT_REQUEST_PROCESSING") }, payment.Result{}, true},
		{"409 는 코드와 상관없이 모름", 409, func(payment.Request) string { return errorJSON("SOMETHING_NEW") }, payment.Result{}, true},
		{"429", 429, func(payment.Request) string { return errorJSON("TOO_MANY_REQUESTS") }, payment.Result{}, true},
		{"코드가 없는 4xx", 400, func(payment.Request) string { return `<html>Bad Request</html>` }, payment.Result{}, true},
		{"모양이 틀린 코드", 400, func(payment.Request) string { return errorJSON("bad code!") }, payment.Result{}, true},
		{"내부 오류", 500, func(payment.Request) string { return errorJSON("FAILED_INTERNAL_SYSTEM_PROCESSING") }, payment.Result{}, true},
		{"결제 처리가 끝나지 않음", 500, func(payment.Request) string { return errorJSON("FAILED_PAYMENT_INTERNAL_SYSTEM_PROCESSING") }, payment.Result{}, true},
		{"빈 502", 502, func(payment.Request) string { return "" }, payment.Result{}, true},
		{"읽지 못하는 200", 200, func(payment.Request) string { return `not json` }, payment.Result{}, true},
		{"2xx 가 아닌 3xx 는 승인이 아니다", 300, func(r payment.Request) string { return matching(r, "DONE") }, payment.Result{}, true},
		{"상태가 없는 200", 200, func(payment.Request) string { return `{"orderId":"x"}` }, payment.Result{}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			toss, fake, _ := startToss(t, tc.status, "")
			request := newRequest()
			fake.body = tc.body(request)

			got, err := toss.Confirm(context.Background(), request)

			if tc.unknown {
				if !errors.Is(err, payment.ErrUnknownOutcome) {
					t.Errorf("결과 = %+v, %v. ErrUnknownOutcome 이어야 한다(돈이 나갔는지 모른다)", got, err)
				}
				return
			}
			if err != nil || got != tc.want {
				t.Errorf("결과 = %+v, %v. 기대 = %+v", got, err, tc.want)
			}
		})
	}
}

func TestTossLookupSendsTheDocumentedRequest(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	fake.body = matching(request, "DONE")

	if _, err := toss.Lookup(context.Background(), request); err != nil {
		t.Fatalf("조회가 실패했다: %v", err)
	}

	got := fake.last(t)
	if got.method != http.MethodGet || got.path != "/v1/payments/"+request.PaymentKey {
		t.Errorf("요청 = %s %s, 기대 = GET /v1/payments/%s", got.method, got.path, request.PaymentKey)
	}
	if auth := got.header.Get("Authorization"); !strings.HasPrefix(auth, "Basic ") {
		t.Errorf("Authorization = %q", auth)
	}
	// GET 은 멱등키가 필요 없다. 본문도 없다
	if got.header.Get("Idempotency-Key") != "" || len(got.body) != 0 {
		t.Errorf("조회에 멱등키나 본문이 실렸다: %q, %q", got.header.Get("Idempotency-Key"), got.body)
	}
}

func TestTossLookupEscapesThePaymentKey(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	request.PaymentKey = "../orders/x?y"
	fake.body = matching(request, "DONE")

	if _, err := toss.Lookup(context.Background(), request); err != nil {
		t.Fatalf("조회가 실패했다: %v", err)
	}

	// 결제 번호는 주소의 한 칸에만 들어간다. 다른 주소나 쿼리가 되지 않는다
	if got := fake.last(t); got.rawPath != "/v1/payments/..%2Forders%2Fx%3Fy" {
		t.Errorf("주소 = %q", got.rawPath)
	}
}

func TestTossLookupJudgesTheStatus(t *testing.T) {
	cases := []struct {
		status string
		want   payment.Result
	}{
		{"DONE", payment.Result{Status: payment.StatusApproved}},
		{"ABORTED", payment.Result{Status: payment.StatusDeclined, Code: "ABORTED"}},
		{"EXPIRED", payment.Result{Status: payment.StatusDeclined, Code: "EXPIRED"}},
		{"CANCELED", payment.Result{Status: payment.StatusDeclined, Code: "CANCELED"}},
		// 결과가 아직 없거나, 일부만 돌려줘 돈의 일부가 나간 것. 거절로 적지 않는다
		{"READY", payment.Result{Status: payment.StatusPending}},
		{"IN_PROGRESS", payment.Result{Status: payment.StatusPending}},
		{"WAITING_FOR_DEPOSIT", payment.Result{Status: payment.StatusPending}},
		{"PARTIAL_CANCELED", payment.Result{Status: payment.StatusPending}},
		{"SOMETHING_NEW", payment.Result{Status: payment.StatusPending}},
	}
	for _, tc := range cases {
		t.Run(tc.status, func(t *testing.T) {
			toss, fake, _ := startToss(t, http.StatusOK, "")
			request := newRequest()
			fake.body = matching(request, tc.status)

			got, err := toss.Lookup(context.Background(), request)

			if err != nil || got != tc.want {
				t.Errorf("결과 = %+v, %v. 기대 = %+v", got, err, tc.want)
			}
		})
	}
}

func TestTossLookupRefusesAnotherOrdersPayment(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	// 다른 주문을 치른 결제다. 이 주문의 결제 번호로 들고 왔다
	fake.body = paymentJSON(request.PaymentKey, uuid.NewString(), "DONE", request.Amount)

	got, err := toss.Lookup(context.Background(), request)

	if err != nil || got != (payment.Result{Status: payment.StatusDeclined, Code: payment.CodePaymentMismatch}) {
		t.Errorf("결과 = %+v, %v. 이 주문의 결제가 아니라 거절이어야 한다", got, err)
	}
}

func TestTossLookupErrorsAreUnknown(t *testing.T) {
	cases := []struct {
		name   string
		status int
		body   string
	}{
		// 못 찾았다는 것도 거절이 아니다. 키를 바꿔 다른 상점에 물었을 수 있다
		{"못 찾음", 404, errorJSON("NOT_FOUND_PAYMENT")},
		{"잘못된 요청", 400, errorJSON("INVALID_REQUEST")},
		{"키가 틀림", 401, errorJSON("UNAUTHORIZED_KEY")},
		{"내부 오류", 500, errorJSON("FAILED_PAYMENT_INTERNAL_SYSTEM_PROCESSING")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			toss, _, _ := startToss(t, tc.status, tc.body)

			got, err := toss.Lookup(context.Background(), newRequest())

			if !errors.Is(err, payment.ErrUnknownOutcome) {
				t.Errorf("결과 = %+v, %v. ErrUnknownOutcome 이어야 한다", got, err)
			}
		})
	}
}

func TestTossUnansweredCallsAreUnknownAndLeakNothing(t *testing.T) {
	slow := func(t *testing.T) (*payment.Toss, payment.Request) {
		toss, fake, _ := startToss(t, http.StatusOK, "")
		fake.delay = time.Second
		return toss, newRequest()
	}
	closed := func(t *testing.T) (*payment.Toss, payment.Request) {
		toss, _, server := startToss(t, http.StatusOK, "")
		server.Close()
		return toss, newRequest()
	}
	calls := map[string]func(*payment.Toss, context.Context, payment.Request) (payment.Result, error){
		"승인": (*payment.Toss).Confirm,
		"조회": (*payment.Toss).Lookup,
		"취소": (*payment.Toss).Cancel,
	}
	situations := map[string]func(*testing.T) (*payment.Toss, payment.Request){"시간 초과": slow, "닫힌 서버": closed}
	for situation, prepare := range situations {
		for name, call := range calls {
			t.Run(situation+"/"+name, func(t *testing.T) {
				toss, request := prepare(t)
				ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
				defer cancel()

				_, err := call(toss, ctx, request)

				if !errors.Is(err, payment.ErrUnknownOutcome) {
					t.Fatalf("오류 = %v. ErrUnknownOutcome 이어야 한다", err)
				}
				// 오류는 로그에 실린다. 결제 번호(조회의 주소에 들어 있다)와 시크릿 키가 없어야 한다
				for _, secret := range []string{request.PaymentKey, tossSecret, "/v1/payments"} {
					if strings.Contains(err.Error(), secret) {
						t.Errorf("오류에 %q 가 실렸다: %v", secret, err)
					}
				}
			})
		}
	}
}

func TestTossCancelSendsTheDocumentedRequest(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	fake.body = matching(request, "CANCELED")

	if _, err := toss.Cancel(context.Background(), request); err != nil {
		t.Fatalf("취소 요청이 실패했다: %v", err)
	}

	got := fake.last(t)
	if got.method != http.MethodPost || got.path != "/v1/payments/"+request.PaymentKey+"/cancel" {
		t.Errorf("요청 = %s %s", got.method, got.path)
	}
	if auth := got.header.Get("Authorization"); auth != "Basic "+base64.StdEncoding.EncodeToString([]byte(tossSecret+":")) {
		t.Errorf("Authorization = %q", auth)
	}
	// 멱등키는 승인의 것과 다르다. 같은 주문의 취소를 다시 보내면 처음의 답이 온다
	if key := got.header.Get("Idempotency-Key"); key != "refund-"+request.OrderID.String() {
		t.Errorf("Idempotency-Key = %q", key)
	}
	// 금액을 적지 않는다. 전액 취소다
	if string(got.body) != `{"cancelReason":"청약철회"}` {
		t.Errorf("본문 = %s", got.body)
	}
}

func TestTossCancelEscapesThePaymentKey(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, "")
	request := newRequest()
	request.PaymentKey = "../x?y"
	fake.body = matching(request, "CANCELED")

	if _, err := toss.Cancel(context.Background(), request); err != nil {
		t.Fatalf("취소 요청이 실패했다: %v", err)
	}

	if got := fake.last(t); got.rawPath != "/v1/payments/..%2Fx%3Fy/cancel" {
		t.Errorf("주소 = %q", got.rawPath)
	}
}

func TestTossCancelJudgesTheAnswer(t *testing.T) {
	canceled := payment.Result{Status: payment.StatusCanceled}
	pending := payment.Result{Status: payment.StatusPending}
	declined := func(code string) payment.Result { return payment.Result{Status: payment.StatusDeclined, Code: code} }
	cases := []struct {
		name    string
		status  int
		body    func(payment.Request) string
		want    payment.Result
		unknown bool
	}{
		{"취소됨", 200, func(r payment.Request) string { return matching(r, "CANCELED") }, canceled, false},
		{"200 인데 아직 승인된 채", 200, func(r payment.Request) string { return matching(r, "DONE") }, pending, false},
		{"200 인데 일부만 취소됨", 200, func(r payment.Request) string { return matching(r, "PARTIAL_CANCELED") }, pending, false},
		// 다른 주문의 결제는 모름이다. 거절로 적으면 돌려준 돈 위에 크레딧까지 돌려줄 수 있다
		{"다른 주문의 결제", 200, func(r payment.Request) string {
			return paymentJSON(r.PaymentKey, "other-order", "CANCELED", r.Amount)
		}, payment.Result{}, true},
		{"읽지 못하는 200", 200, func(payment.Request) string { return `not json` }, payment.Result{}, true},
		{"이미 취소됨", 400, func(payment.Request) string { return errorJSON("ALREADY_CANCELED_PAYMENT") }, canceled, false},
		{"이미 환불됨", 400, func(payment.Request) string { return errorJSON("ALREADY_REFUND_PAYMENT") }, canceled, false},
		{"취소할 수 없는 결제", 403, func(payment.Request) string { return errorJSON("NOT_CANCELABLE_PAYMENT") }, declined("NOT_CANCELABLE_PAYMENT"), false},
		{"환불 기한이 지남", 403, func(payment.Request) string { return errorJSON("EXCEED_MAX_REFUND_DUE") }, declined("EXCEED_MAX_REFUND_DUE"), false},
		{"일시적인 오류", 400, func(payment.Request) string { return errorJSON("PROVIDER_ERROR") }, payment.Result{}, true},
		{"너무 잦은 요청", 403, func(payment.Request) string { return errorJSON("FORBIDDEN_CONSECUTIVE_REQUEST") }, payment.Result{}, true},
		{"우리 키가 틀림", 401, func(payment.Request) string { return errorJSON("UNAUTHORIZED_KEY") }, payment.Result{}, true},
		{"멱등 요청을 처리 중", 409, func(payment.Request) string { return errorJSON("IDEMPOTENT_REQUEST_PROCESSING") }, payment.Result{}, true},
		{"환불 처리 실패", 500, func(payment.Request) string { return errorJSON("FAILED_REFUND_PROCESS") }, payment.Result{}, true},
		{"코드가 없는 4xx", 400, func(payment.Request) string { return `<html></html>` }, payment.Result{}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			toss, fake, _ := startToss(t, tc.status, "")
			request := newRequest()
			fake.body = tc.body(request)

			got, err := toss.Cancel(context.Background(), request)

			if tc.unknown {
				if !errors.Is(err, payment.ErrUnknownOutcome) {
					t.Errorf("결과 = %+v, %v. ErrUnknownOutcome 이어야 한다", got, err)
				}
				return
			}
			if err != nil || got != tc.want {
				t.Errorf("결과 = %+v, %v. 기대 = %+v", got, err, tc.want)
			}
		})
	}
}

func TestTossDoesNotPrintTheSecretKey(t *testing.T) {
	toss := payment.NewToss(tossSecret, payment.TossAPIURL, nil)
	encoded := base64.StdEncoding.EncodeToString([]byte(tossSecret + ":"))

	for _, printed := range []string{fmt.Sprint(toss), fmt.Sprintf("%+v", toss), fmt.Sprintf("%v", *toss), fmt.Sprintf("%+v", *toss)} {
		if strings.Contains(printed, tossSecret) || strings.Contains(printed, encoded) {
			t.Errorf("찍은 글자에 시크릿 키가 있다: %s", printed)
		}
	}
}
