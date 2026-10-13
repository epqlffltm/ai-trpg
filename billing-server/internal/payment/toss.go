// billing-server/internal/payment/toss.go

package payment

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
)

// 토스페이먼츠의 테스트 모드. 결제위젯에서 인증한 결제를 REST API 로 승인하고 조회한다.
//
// 원본은 토스페이먼츠의 문서다. 결제 승인과 조회(https://docs.tosspayments.com/reference),
// 인증과 멱등키(https://docs.tosspayments.com/reference/using-api/authorization),
// 오류 코드(https://docs.tosspayments.com/reference/error-codes).
//
// 결과를 가르는 기준은 하나다. **돈이 나가지 않았다는 것이 확실할 때만 거절**이다.
// 거절로 잘못 적으면 돈을 받고 크레딧을 안 준다. 확실하지 않으면 ErrUnknownOutcome 을 돌려주고,
// 주문은 confirming 에 남아 조회(Lookup)로 끝난다.
//
//   - 승인: 200 에 status DONE. 결제 번호, 주문 번호, 금액이 이 주문의 것이어야 한다
//   - 거절: 승인 요청에 4xx 오류가 왔고, 다시 해 보라는 뜻의 오류가 아니다(카드 거절, 세션 만료, 잘못된 요청)
//   - 모름: 5xx, 연결 실패, 시간 초과, 우리 키의 문제(401), "처리 중"이나 "이미 처리된 결제", 읽지 못한 답
//
// 조회의 오류는 모두 "모름"이다. 조회가 못 찾았다(404)는 것도 모름이다. 키를 바꿔 다른 상점에 물었을 수 있다.
//
// 취소(청약철회)도 같은 기준이다. 이번에는 거절로 잘못 적으면 돈을 돌려주고 크레딧도 돌려준다.
//   - 취소됨: 200 에 status CANCELED. 또는 "이미 취소된 결제"(ALREADY_CANCELED_PAYMENT, ALREADY_REFUND_PAYMENT)
//   - 거절: 4xx 오류 가운데 다시 해 보라는 뜻의 오류가 아닌 것(취소할 수 없는 결제, 기한이 지남 같은 것)
//   - 모름: 그 밖의 모든 것. 200 인데 다른 주문의 결제이거나 CANCELED 가 아닌 것도 모름이다

// TossAPIURL 은 토스페이먼츠 API 의 주소다. 테스트 키로 부르면 테스트 모드다. 테스트와 라이브의 주소가 같다.
const TossAPIURL = "https://api.tosspayments.com"

// CodePaymentMismatch 는 결제 대행사가 아는 결제가 이 주문의 것이 아닐 때(주문 번호, 금액, 결제 번호가 다를 때)
// 주문에 적는 거절 이유다. 다른 결제의 번호를 들고 와 이 주문을 치르려 한 것이다.
const CodePaymentMismatch = "PAYMENT_MISMATCH"

// tossCancelReason 은 취소 요청에 이유(Request.CancelReason)가 없을 때 싣는 이유다. 토스페이먼츠의 상점관리자와 취소 내역에 보인다.
const tossCancelReason = "청약철회"

// tossAlreadyCanceledCodes 는 이미 취소(환불)된 결제라는 오류 코드다. 취소된 것으로 본다.
// 취소를 다시 보낸 것이 멱등키의 기한(15일)을 넘겼을 때 이 답이 온다.
var tossAlreadyCanceledCodes = map[string]bool{
	"ALREADY_CANCELED_PAYMENT": true,
	"ALREADY_REFUND_PAYMENT":   true,
}

// tossMaxResponseBytes 는 읽는 응답의 가장 큰 크기다. 결제 한 건(Payment 객체)은 몇 KB 다.
const tossMaxResponseBytes = 64 << 10

// 토스페이먼츠의 결제 상태(Payment 의 status) 가운데 이 서버가 결과를 아는 것들.
// WAITING_FOR_DEPOSIT 은 가상계좌의 입금을 기다리는 것(StatusAwaitingDeposit)이다.
// 이 밖의 상태(READY, IN_PROGRESS, PARTIAL_CANCELED, 모르는 값)는 아직 모르는 것(StatusPending)이다.
// PARTIAL_CANCELED 는 일부만 돌려준 결제다. 돈의 일부가 나갔으므로 거절로 적지 않는다. 사람이 본다.
const (
	// tossDone 은 승인되었다는 뜻이다.
	tossDone = "DONE"
	// tossAborted 는 승인이 실패했다는 뜻이다.
	tossAborted = "ABORTED"
	// tossExpired 는 인증한 뒤 승인하지 않아 만료되었다는 뜻이다.
	tossExpired = "EXPIRED"
	// tossCanceled 는 승인한 뒤 모두 취소했다는 뜻이다. 돈이 돌아갔다.
	tossCanceled = "CANCELED"
	// tossWaitingForDeposit 은 가상계좌를 발급했고 입금을 기다린다는 뜻이다. 돈은 아직 나가지 않았다.
	tossWaitingForDeposit = "WAITING_FOR_DEPOSIT"
)

// tossRetryCodes 는 4xx 로 오지만 결과가 확실하지 않은 오류 코드들이다. 거절로 적지 않는다.
var tossRetryCodes = map[string]bool{
	// 이미 승인된 결제일 수 있다. 조회로 확인한다
	"ALREADY_PROCESSED_PAYMENT": true,
	// 같은 결제를 처리하는 중이다
	"ALREADY_PROCESSING_REQUEST":    true,
	"IDEMPOTENT_REQUEST_PROCESSING": true,
	// 결제 대행사 쪽의 일시적인 오류다
	"PROVIDER_ERROR":                true,
	"FORBIDDEN_CONSECUTIVE_REQUEST": true,
	// 우리 키나 머리말의 문제다. 결제를 보지도 않았다. 설정을 고친 뒤 조회로 끝낸다
	"UNAUTHORIZED_KEY":            true,
	"INVALID_API_KEY":             true,
	"INCORRECT_BASIC_AUTH_FORMAT": true,
	"INVALID_IDEMPOTENCY_KEY":     true,
}

// tossCodePattern 은 받아 적는 오류 코드의 모양이다. 코드는 주문(failure_code)과 로그에 그대로 적힌다.
// 이 모양이 아니면 읽지 못한 답으로 본다.
var tossCodePattern = regexp.MustCompile(`^[A-Z0-9_]{1,64}$`)

// Toss 는 토스페이먼츠의 결제 승인과 조회를 부른다. 서버가 뜰 때 하나 만들어 함께 쓴다.
// 시간 제한은 부르는 쪽이 context 로 건다(order.ProviderTimeout).
type Toss struct {
	// authorization 은 시크릿 키로 만든 Basic 인증 머리말이다. 로그와 오류에 싣지 않는다.
	authorization string
	baseURL       string
	client        *http.Client
}

// NewToss 는 Toss 를 만든다. secretKey 는 시크릿 키(test_gsk_ 나 test_sk_), baseURL 은 보통 TossAPIURL 이다.
// client 가 nil 이면 기본 클라이언트를 쓴다.
func NewToss(secretKey string, baseURL string, client *http.Client) *Toss {
	if client == nil {
		client = &http.Client{}
	}
	return &Toss{authorization: basicAuthorization(secretKey), baseURL: baseURL, client: client}
}

// String 은 Toss 를 글자로 찍을 때의 모양이다. 실수로 찍어도 인증 머리말(시크릿 키)이 나가지 않는다.
// 값과 포인터 어느 쪽을 찍어도 이것을 쓰도록 값으로 받는다.
func (t Toss) String() string {
	return "payment.Toss(" + t.baseURL + ")"
}

// Confirm 은 결제의 승인을 요청한다. 멱등키로 주문 번호를 보낸다. 같은 주문의 승인을 다시 보내도 처음의 답이 온다.
func (t *Toss) Confirm(ctx context.Context, request Request) (Result, error) {
	body, err := json.Marshal(tossConfirmBody{
		PaymentKey: request.PaymentKey, OrderID: request.OrderID.String(), Amount: request.Amount,
	})
	if err != nil {
		return Result{}, err
	}
	answer, err := t.call(ctx, http.MethodPost, "/v1/payments/confirm", body, request.OrderID.String())
	if err != nil {
		return Result{}, err
	}
	return judgeConfirm(request, answer)
}

// Lookup 은 결제 번호로 결제를 조회한다. 그 결제가 이 주문의 것인지도 본다.
func (t *Toss) Lookup(ctx context.Context, request Request) (Result, error) {
	answer, err := t.call(ctx, http.MethodGet, "/v1/payments/"+url.PathEscape(request.PaymentKey), nil, "")
	if err != nil {
		return Result{}, err
	}
	return judgeLookup(request, answer)
}

// Cancel 은 결제의 전액 취소를 요청한다. 멱등키로 "refund-주문 번호"를 보낸다. 같은 주문의 취소를 다시 보내도 처음의 답이 온다.
func (t *Toss) Cancel(ctx context.Context, request Request) (Result, error) {
	body, err := json.Marshal(tossCancelBody{CancelReason: cancelReason(request)})
	if err != nil {
		return Result{}, err
	}
	path := "/v1/payments/" + url.PathEscape(request.PaymentKey) + "/cancel"
	answer, err := t.call(ctx, http.MethodPost, path, body, "refund-"+request.OrderID.String())
	if err != nil {
		return Result{}, err
	}
	return judgeCancel(request, answer)
}

// tossCancelBody 는 취소 요청의 본문이다. 금액을 적지 않으면 전액 취소다.
type tossCancelBody struct {
	CancelReason string `json:"cancelReason"`
}

// tossConfirmBody 는 승인 요청의 본문이다.
type tossConfirmBody struct {
	PaymentKey string `json:"paymentKey"`
	OrderID    string `json:"orderId"`
	Amount     int64  `json:"amount"`
}

// tossPayment 는 토스페이먼츠의 결제 한 건(Payment 객체)에서 읽는 것이다.
type tossPayment struct {
	PaymentKey  string `json:"paymentKey"`
	OrderID     string `json:"orderId"`
	Status      string `json:"status"`
	TotalAmount int64  `json:"totalAmount"`
}

// tossError 는 토스페이먼츠의 오류 응답이다. message 는 읽지 않는다. 사람이 읽는 글이라 로그와 주문에 싣지 않는다.
type tossError struct {
	Code string `json:"code"`
}

// tossAnswer 는 토스페이먼츠가 준 답이다. 상태 코드와 본문만 들고 판단은 따로 한다.
type tossAnswer struct {
	status int
	body   []byte
}

// call 은 토스페이먼츠를 한 번 부르고 답을 받는다. 답을 받지 못했으면 ErrUnknownOutcome 이다.
func (t *Toss) call(ctx context.Context, method string, path string, body []byte, idempotencyKey string) (tossAnswer, error) {
	request, err := t.newRequest(ctx, method, path, body, idempotencyKey)
	if err != nil {
		return tossAnswer{}, err
	}
	response, err := t.client.Do(request)
	if err != nil {
		return tossAnswer{}, unknownOutcome(withoutURL(err))
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, tossMaxResponseBytes))
	if err != nil {
		return tossAnswer{}, unknownOutcome(withoutURL(err))
	}
	return tossAnswer{status: response.StatusCode, body: raw}, nil
}

// newRequest 는 토스페이먼츠에 보낼 요청을 만든다. 본문이 있으면 JSON 이고, 멱등키가 있으면 머리말에 싣는다.
func (t *Toss) newRequest(ctx context.Context, method string, path string, body []byte, idempotencyKey string) (*http.Request, error) {
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	request, err := http.NewRequestWithContext(ctx, method, t.baseURL+path, reader)
	if err != nil {
		return nil, errors.New("토스페이먼츠에 보낼 요청을 만들지 못했습니다")
	}
	request.Header.Set("Authorization", t.authorization)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	return request, nil
}

// judgeConfirm 은 승인 요청의 답을 결과로 바꾼다. 거절은 확실한 4xx 만이다.
func judgeConfirm(request Request, answer tossAnswer) (Result, error) {
	if answer.succeeded() {
		return readPayment(request, answer.body)
	}
	code := answer.errorCode()
	if refusedForSure(answer.status, code) {
		return Result{Status: StatusDeclined, Code: code}, nil
	}
	return Result{}, unknownAnswer(answer.status, code)
}

// judgeLookup 은 조회의 답을 결과로 바꾼다. 오류는 모두 모르는 것이다.
func judgeLookup(request Request, answer tossAnswer) (Result, error) {
	if answer.succeeded() {
		return readPayment(request, answer.body)
	}
	return Result{}, unknownAnswer(answer.status, answer.errorCode())
}

// judgeCancel 은 취소 요청의 답을 결과로 바꾼다. 거절은 확실한 4xx 만이다.
func judgeCancel(request Request, answer tossAnswer) (Result, error) {
	if answer.succeeded() {
		return readCanceled(request, answer.body)
	}
	code := answer.errorCode()
	if tossAlreadyCanceledCodes[code] {
		return Result{Status: StatusCanceled}, nil
	}
	if refusedForSure(answer.status, code) {
		return Result{Status: StatusDeclined, Code: code}, nil
	}
	return Result{}, unknownAnswer(answer.status, code)
}

// readCanceled 는 취소의 답으로 온 결제 한 건을 읽는다. CANCELED 면 취소된 것이고 그 밖에는 아직 모르는 것이다.
// 다른 주문의 결제가 오면 모름이다. 거절로 적으면 이미 돌려준 돈 위에 크레딧까지 돌려줄 수 있다.
func readCanceled(request Request, raw []byte) (Result, error) {
	var found tossPayment
	if err := json.Unmarshal(raw, &found); err != nil || found.Status == "" {
		return Result{}, unknownOutcome(errors.New("토스페이먼츠의 답을 읽지 못했습니다"))
	}
	if !found.belongsTo(request) {
		return Result{}, unknownOutcome(errors.New("취소의 답이 이 주문의 결제가 아닙니다"))
	}
	if found.Status == tossCanceled {
		return Result{Status: StatusCanceled}, nil
	}
	return Result{Status: StatusPending}, nil
}

// refusedForSure 는 승인이나 취소 요청의 오류가 "하지 않았다"는 확실한 답인지 본다.
// 4xx 이고, 우리 키의 문제(401)나 처리 중(409)이나 너무 잦은 요청(429)이 아니고, 다시 해 보라는 코드가 아니어야 한다.
// 코드를 읽지 못한 4xx(중간의 프록시가 만든 답일 수 있다)도 거절이 아니다.
func refusedForSure(status int, code string) bool {
	if status < 400 || status >= 500 {
		return false
	}
	if status == http.StatusUnauthorized || status == http.StatusConflict || status == http.StatusTooManyRequests {
		return false
	}
	return code != "" && !tossRetryCodes[code]
}

// readPayment 는 결제 한 건을 읽어 결과로 바꾼다. 이 주문의 결제가 아니면 거절(CodePaymentMismatch)이다.
func readPayment(request Request, raw []byte) (Result, error) {
	var found tossPayment
	if err := json.Unmarshal(raw, &found); err != nil || found.Status == "" {
		return Result{}, unknownOutcome(errors.New("토스페이먼츠의 답을 읽지 못했습니다"))
	}
	if !found.belongsTo(request) {
		return Result{Status: StatusDeclined, Code: CodePaymentMismatch}, nil
	}
	return resultOf(found.Status), nil
}

// belongsTo 는 그 결제가 이 주문의 것인지 본다. 결제 번호, 주문 번호, 금액이 모두 같아야 한다.
func (p tossPayment) belongsTo(request Request) bool {
	return p.PaymentKey == request.PaymentKey && p.OrderID == request.OrderID.String() && p.TotalAmount == request.Amount
}

// resultOf 는 토스페이먼츠의 결제 상태를 이 서버의 결과로 바꾼다. 거절의 이유에는 그 상태를 적는다.
func resultOf(status string) Result {
	switch status {
	case tossDone:
		return Result{Status: StatusApproved}
	case tossAborted, tossExpired, tossCanceled:
		return Result{Status: StatusDeclined, Code: status}
	case tossWaitingForDeposit:
		return Result{Status: StatusAwaitingDeposit}
	default:
		return Result{Status: StatusPending}
	}
}

// cancelReason 은 취소 요청에 실을 이유다. 부르는 쪽이 적지 않았으면 청약철회다.
func cancelReason(request Request) string {
	if request.CancelReason == "" {
		return tossCancelReason
	}
	return request.CancelReason
}

// succeeded 는 답이 2xx 인지 본다.
func (a tossAnswer) succeeded() bool {
	return a.status >= 200 && a.status < 300
}

// errorCode 는 오류 응답의 코드를 읽는다. 읽지 못했거나 모양이 틀리면 빈 글자다.
func (a tossAnswer) errorCode() string {
	var answer tossError
	if err := json.Unmarshal(a.body, &answer); err != nil || !tossCodePattern.MatchString(answer.Code) {
		return ""
	}
	return answer.Code
}

// basicAuthorization 은 시크릿 키로 Basic 인증 머리말을 만든다. 키 뒤에 콜론을 붙이고 base64 로 바꾼다(비밀번호 칸이 빈 것).
func basicAuthorization(secretKey string) string {
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(secretKey+":"))
}

// unknownAnswer 는 결과를 알 수 없는 답의 오류를 만든다. 상태 코드와 오류 코드만 싣는다.
func unknownAnswer(status int, code string) error {
	if code == "" {
		code = "코드 없음"
	}
	return fmt.Errorf("%w: 토스페이먼츠가 %d(%s)로 답했습니다", ErrUnknownOutcome, status, code)
}

// unknownOutcome 은 답을 받지 못한 까닭을 ErrUnknownOutcome 으로 감싼다.
func unknownOutcome(cause error) error {
	return fmt.Errorf("%w: %v", ErrUnknownOutcome, cause)
}

// withoutURL 은 HTTP 클라이언트의 오류에서 주소를 뗀다. 조회의 주소에는 결제 번호가 들어 있어서 로그에 싣지 않는다.
func withoutURL(err error) error {
	var urlErr *url.Error
	if errors.As(err, &urlErr) {
		return urlErr.Err
	}
	return err
}
