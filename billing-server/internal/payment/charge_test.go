// billing-server/internal/payment/charge_test.go

// 빌링키 결제(자동 충전, #980)를 시험한다. 토스페이먼츠는 가짜 서버(toss_test.go 의 startToss)가 대신한다.
package payment_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

var (
	_ payment.CardCharger = payment.Fake{}
	_ payment.CardCharger = (*payment.Toss)(nil)
	_ payment.CardCharger = payment.None{}
)

var chargeOrder = uuid.MustParse("0b8f9a6e-6c3b-4a4e-9e71-0c4d6d3a2f10")

func cardCharge() payment.CardCharge {
	return payment.CardCharge{
		BillingKey: "bill/key=", CustomerKey: customerKey, OrderID: chargeOrder, Amount: 5000, OrderName: "크레딧 5,000",
	}
}

func chargedPayment(status string) string {
	return `{"paymentKey":"tviva20261104","orderId":"` + chargeOrder.String() + `","status":"` + status + `","totalAmount":5000}`
}

func TestTossChargesTheCardOnce(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, chargedPayment("DONE"))

	result, err := toss.ChargeCard(context.Background(), cardCharge())

	if err != nil || result.Status != payment.StatusApproved || result.PaymentKey != "tviva20261104" {
		t.Fatalf("결과 = %+v, %v", result, err)
	}
	request := fake.last(t)
	var body map[string]any
	if err := json.Unmarshal(request.body, &body); err != nil {
		t.Fatalf("본문 = %s", request.body)
	}
	// 빌링키는 주소에 들어간다. 주소에 쓸 수 없는 글자는 바꿔 넣는다
	if request.method != http.MethodPost || request.rawPath != "/v1/billing/bill%2Fkey=" {
		t.Errorf("요청 = %s %s", request.method, request.rawPath)
	}
	if body["customerKey"] != customerKey || body["amount"] != float64(5000) || body["orderId"] != chargeOrder.String() ||
		body["orderName"] != "크레딧 5,000" {
		t.Errorf("본문 = %v", body)
	}
	// 다시 보내도 한 번만 나가게 주문 번호를 멱등키로 보낸다
	if request.header.Get("Idempotency-Key") != chargeOrder.String() {
		t.Errorf("멱등키 = %q", request.header.Get("Idempotency-Key"))
	}
}

func TestTossDeclineIsSure(t *testing.T) {
	toss, _, _ := startToss(t, http.StatusBadRequest, `{"code":"REJECT_CARD_COMPANY","message":"카드사가 거절"}`)

	result, err := toss.ChargeCard(context.Background(), cardCharge())

	if err != nil || result.Status != payment.StatusDeclined || result.Code != "REJECT_CARD_COMPANY" {
		t.Errorf("결과 = %+v, %v", result, err)
	}
}

func TestTossAnsweredAbortedIsDeclined(t *testing.T) {
	toss, _, _ := startToss(t, http.StatusOK, chargedPayment("ABORTED"))

	result, err := toss.ChargeCard(context.Background(), cardCharge())

	if err != nil || result.Status != payment.StatusDeclined {
		t.Errorf("결과 = %+v, %v", result, err)
	}
}

func TestTossChargeAnythingElseIsUnknown(t *testing.T) {
	for name, answer := range map[string]struct {
		status int
		body   string
	}{
		"서버 오류":     {http.StatusInternalServerError, `{"code":"FAILED_INTERNAL_SYSTEM_PROCESSING"}`},
		"처리 중":      {http.StatusConflict, `{"code":"ALREADY_PROCESSING_REQUEST"}`},
		"우리 키의 문제":  {http.StatusUnauthorized, `{"code":"UNAUTHORIZED_KEY"}`},
		"읽지 못한 답":   {http.StatusOK, `not json`},
		"다른 주문의 결제": {http.StatusOK, strings.Replace(chargedPayment("DONE"), chargeOrder.String(), uuid.NewString(), 1)},
		"다른 금액":     {http.StatusOK, strings.Replace(chargedPayment("DONE"), "5000", "50000", 1)},
		"결제 번호가 없다": {http.StatusOK, strings.Replace(chargedPayment("DONE"), "tviva20261104", "", 1)},
		"입금을 기다린다":  {http.StatusOK, chargedPayment("WAITING_FOR_DEPOSIT")},
	} {
		toss, _, _ := startToss(t, answer.status, answer.body)

		result, err := toss.ChargeCard(context.Background(), cardCharge())

		if !errors.Is(err, payment.ErrUnknownOutcome) {
			t.Errorf("%s: %+v, %v. 모름이어야 한다", name, result, err)
		}
	}
}

func TestTossInProgressIsPending(t *testing.T) {
	toss, _, _ := startToss(t, http.StatusOK, chargedPayment("IN_PROGRESS"))

	result, err := toss.ChargeCard(context.Background(), cardCharge())

	if err != nil || result.Status != payment.StatusPending {
		t.Errorf("결과 = %+v, %v. 아직 모르는 것이어야 한다", result, err)
	}
}

func TestFakeChargesByTheMark(t *testing.T) {
	ctx := context.Background()
	charge := cardCharge()
	charge.BillingKey = "fake_billing_ok"
	approved, okErr := payment.Fake{}.ChargeCard(ctx, charge)
	charge.BillingKey = "fake_billing_" + payment.FakeChargeDeclined
	declined, declinedErr := payment.Fake{}.ChargeCard(ctx, charge)
	charge.BillingKey = "fake_billing_" + payment.FakeChargeLost
	_, lostErr := payment.Fake{}.ChargeCard(ctx, charge)
	_, noneErr := payment.None{}.ChargeCard(ctx, charge)

	if okErr != nil || approved.Status != payment.StatusApproved || approved.PaymentKey == "" {
		t.Errorf("승인 = %+v, %v", approved, okErr)
	}
	if declinedErr != nil || declined.Status != payment.StatusDeclined || declined.Code != payment.FakeCodeChargeDeclined {
		t.Errorf("거절 = %+v, %v", declined, declinedErr)
	}
	if !errors.Is(lostErr, payment.ErrUnknownOutcome) || !errors.Is(noneErr, payment.ErrNoProvider) {
		t.Errorf("모름 = %v, 없음 = %v", lostErr, noneErr)
	}
}

func TestTossLooksUpTheChargeByTheOrderWithoutAKey(t *testing.T) {
	toss, fake, _ := startToss(t, http.StatusOK, chargedPayment("DONE"))

	result, err := toss.LookupCharge(context.Background(), cardCharge())

	if err != nil || result.Status != payment.StatusApproved || result.PaymentKey != "tviva20261104" {
		t.Fatalf("결과 = %+v, %v", result, err)
	}
	request := fake.last(t)
	if request.method != http.MethodGet || request.rawPath != "/v1/payments/orders/"+chargeOrder.String() {
		t.Errorf("요청 = %s %s", request.method, request.rawPath)
	}
	// 조회는 결제를 만들지 않는다. 멱등키가 없다(기한도 없다)
	if request.header.Get("Idempotency-Key") != "" {
		t.Errorf("멱등키 = %q", request.header.Get("Idempotency-Key"))
	}
}

func TestTossLookupSaysNotChargedOnlyWhenItIsSure(t *testing.T) {
	for name, answer := range map[string]struct {
		status   int
		body     string
		wantCode string
	}{
		"결제가 없다":    {http.StatusNotFound, `{"code":"NOT_FOUND_PAYMENT","message":"없음"}`, payment.CodeChargeNotFound},
		"끝내 되지 않았다": {http.StatusOK, chargedPayment("ABORTED"), "ABORTED"},
		"기한이 지났다":   {http.StatusOK, chargedPayment("EXPIRED"), "EXPIRED"},
		"취소되어 돌려줬다": {http.StatusOK, chargedPayment("CANCELED"), "CANCELED"},
	} {
		toss, _, _ := startToss(t, answer.status, answer.body)

		result, err := toss.LookupCharge(context.Background(), cardCharge())

		if err != nil || result.Status != payment.StatusDeclined || result.Code != answer.wantCode {
			t.Errorf("%s: %+v, %v", name, result, err)
		}
	}
}

func TestTossLookupAnythingElseIsUnknown(t *testing.T) {
	for name, answer := range map[string]struct {
		status int
		body   string
	}{
		"다른 까닭의 404": {http.StatusNotFound, `{"code":"NOT_FOUND","message":"주소가 없음"}`},
		"코드 없는 404":  {http.StatusNotFound, `not json`},
		"서버 오류":      {http.StatusInternalServerError, `{"code":"FAILED_INTERNAL_SYSTEM_PROCESSING"}`},
		"우리 키의 문제":   {http.StatusUnauthorized, `{"code":"UNAUTHORIZED_KEY"}`},
		"다른 주문의 결제":  {http.StatusOK, strings.Replace(chargedPayment("DONE"), chargeOrder.String(), uuid.NewString(), 1)},
		"다른 금액":      {http.StatusOK, strings.Replace(chargedPayment("DONE"), "5000", "50000", 1)},
	} {
		toss, _, _ := startToss(t, answer.status, answer.body)

		result, err := toss.LookupCharge(context.Background(), cardCharge())

		if !errors.Is(err, payment.ErrUnknownOutcome) {
			t.Errorf("%s: %+v, %v. 모름이어야 한다", name, result, err)
		}
	}
	toss, _, _ := startToss(t, http.StatusOK, chargedPayment("IN_PROGRESS"))
	if result, err := toss.LookupCharge(context.Background(), cardCharge()); err != nil || result.Status != payment.StatusPending {
		t.Errorf("처리 중: %+v, %v. 아직 모르는 것이어야 한다", result, err)
	}
}

func TestFakeLooksUpByTheMark(t *testing.T) {
	ctx := context.Background()
	charge := cardCharge()
	charge.BillingKey = "fake_billing_" + payment.FakeChargeLost + "_" + payment.FakeLookupPaid
	paid, paidErr := payment.Fake{}.LookupCharge(ctx, charge)
	charged, _ := payment.Fake{}.ChargeCard(ctx, cardCharge())
	charge.BillingKey = "fake_billing_" + payment.FakeChargeLost + "_" + payment.FakeLookupMissing
	missing, missingErr := payment.Fake{}.LookupCharge(ctx, charge)
	charge.BillingKey = "fake_billing_" + payment.FakeChargeLost
	_, lostErr := payment.Fake{}.LookupCharge(ctx, charge)
	_, noneErr := payment.None{}.LookupCharge(ctx, charge)

	// 조회로 찾은 결제 번호는 결제할 때 붙였을 것과 같다
	if paidErr != nil || paid.Status != payment.StatusApproved || paid.PaymentKey == "" || paid.PaymentKey != charged.PaymentKey {
		t.Errorf("완료 = %+v, %v (결제의 번호 %q)", paid, paidErr, charged.PaymentKey)
	}
	if missingErr != nil || missing.Status != payment.StatusDeclined || missing.Code != payment.CodeChargeNotFound {
		t.Errorf("없음 = %+v, %v", missing, missingErr)
	}
	if !errors.Is(lostErr, payment.ErrUnknownOutcome) || !errors.Is(noneErr, payment.ErrNoProvider) {
		t.Errorf("모름 = %v, 없음 = %v", lostErr, noneErr)
	}
}
