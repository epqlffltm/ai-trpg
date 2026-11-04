// billing-server/internal/payment/card.go

package payment

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"
)

// 카드 등록(자동 충전, #980). 사용자가 결제 대행사의 카드 등록 창에서 인증하면, 결제 대행사가 인증 키(auth key)를 준다.
// 서버가 그 키와 고객 키(customer key)로 빌링키(billing key)를 받는다. 빌링키와 시크릿 키가 있으면 사용자 없이 결제할 수 있다.
//
// 원본은 토스페이먼츠의 문서다(자동결제, POST /v1/billing/authorizations/issue).
// 판단의 기준은 승인과 같다. 등록을 거절했다는 것이 확실할 때만 거절이다(RefusedError). 확실하지 않으면 ErrUnknownOutcome 이다.
// 등록은 돈이 오가지 않는다. 결과를 모르면 사용자가 다시 등록하면 된다.

// CardRequest 는 카드 등록 하나다.
type CardRequest struct {
	// AuthKey 는 결제 대행사가 카드 등록 창에서 준 인증 키다. 한 번만 쓴다.
	AuthKey string
	// CustomerKey 는 이 서버가 그 사용자에게 붙인 고객 키다.
	CustomerKey string
}

// Card 는 등록한 카드다.
type Card struct {
	// BillingKey 는 결제할 때 쓰는 키다. 응답과 로그에 싣지 않는다.
	BillingKey string
	// IssuerCode 는 카드를 낸 곳의 코드다.
	IssuerCode string
	// Number 는 결제 대행사가 가린 카드 번호다.
	Number string
}

// RefusedError 는 결제 대행사가 카드 등록을 거절했다는 오류다. Code 는 결제 대행사가 준 이유다.
type RefusedError struct {
	Code string
}

func (e *RefusedError) Error() string {
	return "결제 대행사가 카드 등록을 거절했습니다: " + e.Code
}

// CardIssuer 는 카드를 등록해 빌링키를 받는 것의 모양이다. *Toss 와 Fake 가 이 모양이다.
type CardIssuer interface {
	IssueCard(ctx context.Context, request CardRequest) (Card, error)
}

// 가짜 결제 대행사가 알아듣는 인증 키의 앞머리.
const (
	// FakeCardApproved 로 시작하면 등록된다.
	FakeCardApproved = "fake_card_ok_"
	// FakeCardRefused 로 시작하면 거절된다.
	FakeCardRefused = "fake_card_refused_"
	// FakeCardLost 로 시작하면 답이 오지 않는다.
	FakeCardLost = "fake_card_lost_"
	// FakeCodeCardRefused 는 가짜가 카드 등록을 거절하면서 주는 이유다.
	FakeCodeCardRefused = "card_refused"
)

// IssueCard 는 인증 키의 앞머리에 따라 등록하거나, 거절하거나, 답을 주지 않는다. 빌링키는 인증 키에서 만든다.
func (Fake) IssueCard(_ context.Context, request CardRequest) (Card, error) {
	switch {
	case strings.HasPrefix(request.AuthKey, FakeCardApproved):
		suffix := strings.TrimPrefix(request.AuthKey, FakeCardApproved)
		return Card{BillingKey: "fake_billing_" + suffix, IssuerCode: "4V", Number: "43301234****123*"}, nil
	case strings.HasPrefix(request.AuthKey, FakeCardLost):
		return Card{}, ErrUnknownOutcome
	default:
		return Card{}, &RefusedError{Code: FakeCodeCardRefused}
	}
}

// IssueCard 는 ErrNoProvider 다.
func (None) IssueCard(context.Context, CardRequest) (Card, error) { return Card{}, ErrNoProvider }

// tossIssueBody 는 빌링키 발급 요청의 본문이다.
type tossIssueBody struct {
	AuthKey     string `json:"authKey"`
	CustomerKey string `json:"customerKey"`
}

// tossBilling 은 빌링키 발급의 답에서 읽는 것이다.
type tossBilling struct {
	BillingKey  string `json:"billingKey"`
	CustomerKey string `json:"customerKey"`
	Card        struct {
		IssuerCode string `json:"issuerCode"`
		Number     string `json:"number"`
	} `json:"card"`
}

// tossMaskedNumber 는 받아 적는 가린 카드 번호의 모양이다. 숫자와 * 만이다. 가리지 않은 번호가 오면 적지 않는다.
var tossMaskedNumber = regexp.MustCompile(`^[0-9*]{8,25}$`)

// tossIssuerCode 는 받아 적는 카드사 코드의 모양이다.
var tossIssuerCode = regexp.MustCompile(`^[0-9A-Z]{1,8}$`)

// IssueCard 는 인증 키로 빌링키를 받는다. 답의 고객 키가 보낸 것과 다르면 모르는 답이다.
func (t *Toss) IssueCard(ctx context.Context, request CardRequest) (Card, error) {
	body, err := json.Marshal(tossIssueBody{AuthKey: request.AuthKey, CustomerKey: request.CustomerKey})
	if err != nil {
		return Card{}, err
	}
	answer, err := t.call(ctx, http.MethodPost, "/v1/billing/authorizations/issue", body, "")
	if err != nil {
		return Card{}, err
	}
	return judgeIssue(request, answer)
}

// judgeIssue 는 빌링키 발급의 답을 카드로 바꾼다. 거절은 확실한 4xx 만이다.
func judgeIssue(request CardRequest, answer tossAnswer) (Card, error) {
	if !answer.succeeded() {
		code := answer.errorCode()
		if refusedForSure(answer.status, code) {
			return Card{}, &RefusedError{Code: code}
		}
		return Card{}, unknownAnswer(answer.status, code)
	}
	return readBilling(request, answer.body)
}

// readBilling 은 빌링키 발급의 답을 읽는다. 빌링키가 없거나, 다른 고객의 것이거나, 카드 번호가 가려지지 않았으면 모르는 답이다.
func readBilling(request CardRequest, raw []byte) (Card, error) {
	var billing tossBilling
	if err := json.Unmarshal(raw, &billing); err != nil {
		return Card{}, unknownOutcome(errors.New("빌링키 발급의 답을 읽지 못했습니다"))
	}
	if billing.BillingKey == "" || billing.CustomerKey != request.CustomerKey {
		return Card{}, unknownOutcome(errors.New("빌링키 발급의 답이 이 고객의 것이 아닙니다"))
	}
	masked := tossMaskedNumber.MatchString(billing.Card.Number) && strings.Contains(billing.Card.Number, "*")
	if !masked || !tossIssuerCode.MatchString(billing.Card.IssuerCode) {
		return Card{}, unknownOutcome(errors.New("빌링키 발급의 답에 카드의 모양이 틀렸습니다"))
	}
	return Card{BillingKey: billing.BillingKey, IssuerCode: billing.Card.IssuerCode, Number: billing.Card.Number}, nil
}
