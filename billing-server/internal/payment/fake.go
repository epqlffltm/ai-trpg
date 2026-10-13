// billing-server/internal/payment/fake.go

package payment

import (
	"context"
	"strings"
)

// 가짜 결제 대행사가 알아듣는 결제 번호의 앞머리. 앞머리가 결과를 정한다.
// 실제 결제 대행사의 테스트용 카드 번호와 같은 생각이다. 뒤에는 아무 글자나 붙여 결제마다 다르게 만든다.
const (
	// FakeApproved 로 시작하면 승인된다.
	FakeApproved = "fake_ok_"
	// FakeDeclined 로 시작하면 거절된다.
	FakeDeclined = "fake_declined_"
	// FakeTimeoutApproved 로 시작하면 승인 요청의 답이 오지 않는다. 실제로는 승인되었고, 조회하면 그렇게 나온다.
	FakeTimeoutApproved = "fake_timeout_ok_"
	// FakeTimeoutDeclined 로 시작하면 승인 요청의 답이 오지 않는다. 실제로는 거절되었고, 조회하면 그렇게 나온다.
	FakeTimeoutDeclined = "fake_timeout_declined_"
	// FakeLost 로 시작하면 승인 요청의 답이 오지 않고, 조회해도 결제 대행사가 아직 결과를 모른다.
	FakeLost = "fake_lost_"
)

// 가짜 결제 대행사가 알아듣는 취소의 표시. 결제 번호의 어디에 들어 있어도 된다(fake_ok_cancel_refused_1 처럼).
// 표시가 없으면 취소는 늘 된다.
const (
	// FakeCancelRefused 가 들어 있으면 취소를 거절한다.
	FakeCancelRefused = "cancel_refused"
	// FakeCancelLost 가 들어 있으면 취소 요청에 답이 오지 않는다. 다시 보내도 같다.
	FakeCancelLost = "cancel_lost"
)

// 가짜 결제 대행사가 거절하면서 주는 이유.
const (
	// FakeCodeDeclined 는 카드가 거절되었다는 이유다.
	FakeCodeDeclined = "card_declined"
	// FakeCodeUnknownKey 는 모르는 결제 번호라는 이유다.
	FakeCodeUnknownKey = "unknown_payment_key"
	// FakeCodeCancelRefused 는 취소를 거절했다는 이유다.
	FakeCodeCancelRefused = "cancel_refused"
)

// Fake 는 정해 둔 대로 답하는 가짜 결제 대행사다. 돈을 받지 않는다. 기억하는 것이 없다.
//
// 결제 번호만 보고 답하므로 같은 번호에는 늘 같은 답을 한다. 서버를 다시 띄워도, 여러 대를 띄워도 같다.
type Fake struct{}

// Confirm 은 결제 번호의 앞머리에 따라 승인하거나, 거절하거나, 답을 주지 않는다.
func (Fake) Confirm(_ context.Context, request Request) (Result, error) {
	if answersLate(request.PaymentKey) {
		return Result{}, ErrUnknownOutcome
	}
	return outcome(request.PaymentKey), nil
}

// Lookup 은 결제 번호의 앞머리에 따라 지금의 결과를 돌려준다. 승인 요청과 달리 늘 답한다.
// 가짜는 기억하는 것이 없어서 주문과 금액은 보지 않는다.
func (Fake) Lookup(_ context.Context, request Request) (Result, error) {
	return outcome(request.PaymentKey), nil
}

// Cancel 은 결제 번호에 든 표시에 따라 취소하거나, 거절하거나, 답을 주지 않는다. 기억하는 것이 없어서
// 승인되지 않은 결제인지는 보지 않는다. 그것은 주문(paid 인 주문만 환불한다)이 지킨다.
func (Fake) Cancel(_ context.Context, request Request) (Result, error) {
	switch {
	case strings.Contains(request.PaymentKey, FakeCancelLost):
		return Result{}, ErrUnknownOutcome
	case strings.Contains(request.PaymentKey, FakeCancelRefused):
		return Result{Status: StatusDeclined, Code: FakeCodeCancelRefused}, nil
	default:
		return Result{Status: StatusCanceled}, nil
	}
}

// answersLate 는 그 결제 번호의 승인 요청에 답이 오지 않는지 본다.
func answersLate(paymentKey string) bool {
	for _, prefix := range []string{FakeTimeoutApproved, FakeTimeoutDeclined, FakeLost} {
		if strings.HasPrefix(paymentKey, prefix) {
			return true
		}
	}
	return false
}

// outcome 은 결제 번호의 앞머리가 정한 실제 결과다. 모르는 앞머리는 거절이다.
func outcome(paymentKey string) Result {
	switch {
	case strings.HasPrefix(paymentKey, FakeApproved), strings.HasPrefix(paymentKey, FakeTimeoutApproved):
		return Result{Status: StatusApproved}
	case strings.HasPrefix(paymentKey, FakeDeclined), strings.HasPrefix(paymentKey, FakeTimeoutDeclined):
		return Result{Status: StatusDeclined, Code: FakeCodeDeclined}
	case strings.HasPrefix(paymentKey, FakeLost):
		return Result{Status: StatusPending}
	default:
		return Result{Status: StatusDeclined, Code: FakeCodeUnknownKey}
	}
}
