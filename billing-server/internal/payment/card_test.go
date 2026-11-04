// billing-server/internal/payment/card_test.go

// 카드 등록(빌링키 발급, #980)을 시험한다. 토스페이먼츠는 가짜 서버(toss_test.go 의 startToss)가 대신한다.
package payment_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 두 결제 대행사와 자리 채움 모두 카드를 등록하는 모양이다.
var (
	_ payment.CardIssuer = payment.Fake{}
	_ payment.CardIssuer = (*payment.Toss)(nil)
	_ payment.CardIssuer = payment.None{}
)

const customerKey = "6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11"

func cardRequest() payment.CardRequest {
	return payment.CardRequest{AuthKey: "auth_key_1", CustomerKey: customerKey}
}

const issuedBilling = `{"mId":"tosspayments","customerKey":"` + customerKey + `","authenticatedAt":"2026-11-04T10:00:00+09:00",
"method":"카드","billingKey":"Z_t5vOvQxrj4499PeiJcjen28-V2RyqgYTwN44Rdzk0=",
"card":{"issuerCode":"61","acquirerCode":"31","number":"43301234****123*","cardType":"신용","ownerType":"개인"}}`

func TestTossIssuesACard(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, issuedBilling)

	card, err := toss.IssueCard(context.Background(), cardRequest())

	if err != nil {
		t.Fatalf("등록하지 못했다: %v", err)
	}
	if card.BillingKey != "Z_t5vOvQxrj4499PeiJcjen28-V2RyqgYTwN44Rdzk0=" || card.IssuerCode != "61" || card.Number != "43301234****123*" {
		t.Errorf("카드 = %+v", card)
	}
	request := fake.last(t)
	var body map[string]string
	if err := json.Unmarshal(request.body, &body); err != nil {
		t.Fatalf("본문 = %s", request.body)
	}
	if request.method != http.MethodPost || request.path != "/v1/billing/authorizations/issue" ||
		body["authKey"] != "auth_key_1" || body["customerKey"] != customerKey {
		t.Errorf("요청 = %s %s %v", request.method, request.path, body)
	}
}

func TestTossRefusalIsSure(t *testing.T) {
	toss, _, _ := startToss(t, http.StatusBadRequest, `{"code":"INVALID_CARD_NUMBER","message":"카드 번호가 틀렸습니다"}`)

	_, err := toss.IssueCard(context.Background(), cardRequest())

	var refused *payment.RefusedError
	if !errors.As(err, &refused) || refused.Code != "INVALID_CARD_NUMBER" {
		t.Errorf("오류 = %v. 거절이어야 한다", err)
	}
}

func TestTossAnythingElseIsUnknown(t *testing.T) {
	for name, answer := range map[string]struct {
		status int
		body   string
	}{
		"서버 오류":        {http.StatusInternalServerError, `{"code":"FAILED_INTERNAL_SYSTEM_PROCESSING"}`},
		"우리 키의 문제":     {http.StatusUnauthorized, `{"code":"UNAUTHORIZED_KEY"}`},
		"읽지 못한 답":      {http.StatusOK, `not json`},
		"다른 고객의 빌링키":   {http.StatusOK, strings.Replace(issuedBilling, customerKey, "someone-else", 1)},
		"빌링키가 없다":      {http.StatusOK, strings.Replace(issuedBilling, `"billingKey":"Z_t5vOvQxrj4499PeiJcjen28-V2RyqgYTwN44Rdzk0="`, `"billingKey":""`, 1)},
		"가리지 않은 카드 번호": {http.StatusOK, strings.Replace(issuedBilling, "43301234****123*", "4330123412341234", 1)},
	} {
		toss, _, _ := startToss(t, answer.status, answer.body)

		_, err := toss.IssueCard(context.Background(), cardRequest())

		if !errors.Is(err, payment.ErrUnknownOutcome) {
			t.Errorf("%s: 오류 = %v. 모름이어야 한다", name, err)
		}
	}
}

func TestFakeIssuesByThePrefix(t *testing.T) {
	ctx := context.Background()
	card, okErr := payment.Fake{}.IssueCard(ctx, payment.CardRequest{AuthKey: payment.FakeCardApproved + "a1", CustomerKey: customerKey})
	_, refusedErr := payment.Fake{}.IssueCard(ctx, payment.CardRequest{AuthKey: payment.FakeCardRefused + "a1"})
	_, lostErr := payment.Fake{}.IssueCard(ctx, payment.CardRequest{AuthKey: payment.FakeCardLost + "a1"})
	_, noneErr := payment.None{}.IssueCard(ctx, cardRequest())

	if okErr != nil || card.BillingKey != "fake_billing_a1" || !strings.Contains(card.Number, "*") {
		t.Errorf("등록 = %+v, %v", card, okErr)
	}
	var refused *payment.RefusedError
	if !errors.As(refusedErr, &refused) || refused.Code != payment.FakeCodeCardRefused {
		t.Errorf("거절 = %v", refusedErr)
	}
	if !errors.Is(lostErr, payment.ErrUnknownOutcome) || !errors.Is(noneErr, payment.ErrNoProvider) {
		t.Errorf("모름 = %v, 없음 = %v", lostErr, noneErr)
	}
}
