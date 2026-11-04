// billing-server/internal/payment/charge.go

package payment

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/google/uuid"
)

// 빌링키로 결제하기(자동 충전, #980). 사용자 없이 결제 대행사가 바로 승인한다. 승인 요청과 승인이 한 번이다.
//
// 원본은 토스페이먼츠의 문서다(자동결제, POST /v1/billing/{billingKey}).
// 판단의 기준은 승인과 같다. 돈이 나가지 않았다는 것이 확실할 때만 거절이다. 확실하지 않으면 ErrUnknownOutcome 이다.
// 멱등키로 주문 번호를 보낸다. 답을 받지 못했으면 같은 주문 번호로 같은 요청을 다시 보낸다. 결제 대행사는 처음의 답을 준다.
// 그래서 결과를 모르는 결제는 조회하지 않고 다시 보낸다(취소와 같다).
//
// 다만 멱등키는 처음 쓴 날부터 15일만 쓸 수 있다. 그 뒤에 다시 보내면 무엇이 오는지 문서에 없다.
// 그래서 다시 보내는 것은 정한 기한(autocharge.ResendFor)까지만 하고, 그 뒤에는 주문 번호로 조회한다(LookupCharge).
// 조회(GET)는 멱등키가 없어 기한이 없고, 결제를 새로 만들지 않는다.

// CardCharge 는 빌링키 결제 하나다.
type CardCharge struct {
	// BillingKey 는 카드 등록 때 받은 키다. 로그와 오류에 싣지 않는다.
	BillingKey string
	// CustomerKey 는 그 카드의 고객 키다.
	CustomerKey string
	// OrderID 는 이 서버의 주문 번호다. 멱등키로도 쓴다.
	OrderID uuid.UUID
	// Amount 는 받을 돈이다. 원(KRW)이다.
	Amount int64
	// OrderName 은 결제 대행사의 결제 내역에 보이는 이름이다.
	OrderName string
}

// ChargeResult 는 빌링키 결제의 결과다. 승인이면 PaymentKey 가 있다. 거절이면 Code 가 있다.
type ChargeResult struct {
	Status     Status
	Code       string
	PaymentKey string
}

// CardCharger 는 빌링키로 결제하고, 그 결제를 주문 번호로 조회하는 것의 모양이다. *Toss 와 Fake 가 이 모양이다.
type CardCharger interface {
	ChargeCard(ctx context.Context, charge CardCharge) (ChargeResult, error)
	// LookupCharge 는 그 주문 번호의 결제를 조회한다. 결제를 만들지 않는다.
	//   - 완료(DONE)면 승인이다. PaymentKey 가 있다
	//   - 결제가 없거나(CodeChargeNotFound) 끝내 되지 않았으면(ABORTED, EXPIRED, CANCELED) 거절이다. 돈이 나가지 않았다
	//   - 그 밖(아직 처리 중, 다른 주문의 결제, 답을 받지 못함)은 ErrUnknownOutcome 이거나 StatusPending 이다
	LookupCharge(ctx context.Context, charge CardCharge) (ChargeResult, error)
}

// Cards 는 카드를 등록하고 그 카드로 결제하는 것의 모양이다. *Toss 와 Fake 가 이 모양이다.
type Cards interface {
	CardIssuer
	CardCharger
}

// 가짜 결제 대행사가 빌링키에서 알아듣는 표시. 빌링키의 어디에 들어 있어도 된다(카드 등록의 인증 키에 넣으면 빌링키에 들어간다).
// 표시가 없으면 승인한다.
const (
	// FakeChargeDeclined 가 들어 있으면 거절한다.
	FakeChargeDeclined = "charge_declined"
	// FakeChargeLost 가 들어 있으면 답이 오지 않는다. 다시 보내도 같다.
	FakeChargeLost = "charge_lost"
	// FakeCodeChargeDeclined 는 가짜가 빌링키 결제를 거절하면서 주는 이유다.
	FakeCodeChargeDeclined = "card_charge_declined"
	// FakeLookupPaid 가 들어 있으면 주문 번호로 조회할 때 완료라고 답한다(답이 오지 않던 결제가 사실은 됐다).
	FakeLookupPaid = "lookup_paid"
	// FakeLookupMissing 이 들어 있으면 주문 번호로 조회할 때 그 결제가 없다고 답한다(보낸 것이 닿지 않았다).
	// 둘 다 없으면 조회에도 답이 오지 않는다.
	FakeLookupMissing = "lookup_missing"
)

// CodeChargeNotFound 는 주문 번호로 조회했는데 결제가 없다는 이유다. 돈이 나가지 않았다.
const CodeChargeNotFound = "charge_not_found"

// tossChargeNotFound 는 토스페이먼츠가 결제를 찾지 못했을 때 주는 오류 코드다.
// 이것이 아닌 404 는 모름으로 둔다. 코드를 잘못 읽으면 사람에게 넘어갈 뿐 돈을 잃지 않는다.
const tossChargeNotFound = "NOT_FOUND_PAYMENT"

// ChargeCard 는 빌링키의 표시에 따라 승인하거나, 거절하거나, 답을 주지 않는다. 결제 번호는 주문 번호에서 만든다.
func (Fake) ChargeCard(_ context.Context, charge CardCharge) (ChargeResult, error) {
	switch {
	case strings.Contains(charge.BillingKey, FakeChargeLost):
		return ChargeResult{}, ErrUnknownOutcome
	case strings.Contains(charge.BillingKey, FakeChargeDeclined):
		return ChargeResult{Status: StatusDeclined, Code: FakeCodeChargeDeclined}, nil
	default:
		return ChargeResult{Status: StatusApproved, PaymentKey: fakeChargeKey(charge)}, nil
	}
}

// LookupCharge 는 빌링키의 표시에 따라 완료, 없음, 답 없음으로 답한다. 결제 번호는 ChargeCard 와 같게 만든다.
func (Fake) LookupCharge(_ context.Context, charge CardCharge) (ChargeResult, error) {
	switch {
	case strings.Contains(charge.BillingKey, FakeLookupPaid):
		return ChargeResult{Status: StatusApproved, PaymentKey: fakeChargeKey(charge)}, nil
	case strings.Contains(charge.BillingKey, FakeLookupMissing):
		return ChargeResult{Status: StatusDeclined, Code: CodeChargeNotFound}, nil
	default:
		return ChargeResult{}, ErrUnknownOutcome
	}
}

// fakeChargeKey 는 가짜가 빌링키 결제에 붙이는 결제 번호다. 주문 번호에서 만든다.
func fakeChargeKey(charge CardCharge) string {
	return "fake_auto_" + strings.ReplaceAll(charge.OrderID.String(), "-", "")
}

// ChargeCard 는 ErrNoProvider 다.
func (None) ChargeCard(context.Context, CardCharge) (ChargeResult, error) {
	return ChargeResult{}, ErrNoProvider
}

// LookupCharge 는 ErrNoProvider 다.
func (None) LookupCharge(context.Context, CardCharge) (ChargeResult, error) {
	return ChargeResult{}, ErrNoProvider
}

// tossChargeBody 는 빌링키 결제 요청의 본문이다.
type tossChargeBody struct {
	CustomerKey string `json:"customerKey"`
	Amount      int64  `json:"amount"`
	OrderID     string `json:"orderId"`
	OrderName   string `json:"orderName"`
}

// ChargeCard 는 빌링키로 결제한다. 멱등키로 주문 번호를 보낸다.
func (t *Toss) ChargeCard(ctx context.Context, charge CardCharge) (ChargeResult, error) {
	body, err := json.Marshal(tossChargeBody{
		CustomerKey: charge.CustomerKey, Amount: charge.Amount, OrderID: charge.OrderID.String(), OrderName: charge.OrderName,
	})
	if err != nil {
		return ChargeResult{}, err
	}
	answer, err := t.call(ctx, http.MethodPost, "/v1/billing/"+url.PathEscape(charge.BillingKey), body, charge.OrderID.String())
	if err != nil {
		return ChargeResult{}, err
	}
	return judgeCharge(charge, answer)
}

// LookupCharge 는 주문 번호로 결제를 조회한다(GET /v1/payments/orders/{orderId}). 멱등키를 보내지 않는다.
func (t *Toss) LookupCharge(ctx context.Context, charge CardCharge) (ChargeResult, error) {
	answer, err := t.call(ctx, http.MethodGet, "/v1/payments/orders/"+url.PathEscape(charge.OrderID.String()), nil, "")
	if err != nil {
		return ChargeResult{}, err
	}
	return judgeChargeLookup(charge, answer)
}

// judgeChargeLookup 은 주문 번호로 조회한 답을 결과로 바꾼다. 없음은 404 와 그 코드일 때만이다.
func judgeChargeLookup(charge CardCharge, answer tossAnswer) (ChargeResult, error) {
	if answer.succeeded() {
		return readCharged(charge, answer.body)
	}
	code := answer.errorCode()
	if answer.status == http.StatusNotFound && code == tossChargeNotFound {
		return ChargeResult{Status: StatusDeclined, Code: CodeChargeNotFound}, nil
	}
	return ChargeResult{}, unknownAnswer(answer.status, code)
}

// judgeCharge 는 빌링키 결제의 답을 결과로 바꾼다. 거절은 확실한 4xx 만이다.
func judgeCharge(charge CardCharge, answer tossAnswer) (ChargeResult, error) {
	if !answer.succeeded() {
		code := answer.errorCode()
		if refusedForSure(answer.status, code) {
			return ChargeResult{Status: StatusDeclined, Code: code}, nil
		}
		return ChargeResult{}, unknownAnswer(answer.status, code)
	}
	return readCharged(charge, answer.body)
}

// readCharged 는 빌링키 결제의 답으로 온 결제 한 건을 읽는다. 이 주문의 결제여야 한다(주문 번호와 금액).
// 다른 주문의 것이면 모름이다. 거절로 적으면 돈이 나갔는데 골드를 안 줄 수 있다.
func readCharged(charge CardCharge, raw []byte) (ChargeResult, error) {
	var payment tossPayment
	if err := json.Unmarshal(raw, &payment); err != nil {
		return ChargeResult{}, unknownOutcome(errors.New("빌링키 결제의 답을 읽지 못했습니다"))
	}
	if payment.OrderID != charge.OrderID.String() || payment.TotalAmount != charge.Amount || payment.PaymentKey == "" {
		return ChargeResult{}, unknownOutcome(errors.New("빌링키 결제의 답이 이 주문의 것이 아닙니다"))
	}
	result := resultOf(payment.Status)
	if result.Status == StatusAwaitingDeposit {
		// 카드 결제에서는 오지 않는다. 오면 사람이 본다
		return ChargeResult{}, unknownOutcome(errors.New("빌링키 결제가 입금을 기다린다고 답했습니다"))
	}
	return ChargeResult{Status: result.Status, Code: result.Code, PaymentKey: payment.PaymentKey}, nil
}
