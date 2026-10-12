// billing-server/internal/payment/payment.go

// Package payment 는 결제 대행사(PG)와 이야기하는 부분이다.
//
// 주문을 다루는 코드는 Provider 라는 모양만 안다. 그 자리에 둘 가운데 하나를 꽂는다(설정 PAYMENT_PROVIDER).
//   - Fake: 정해 둔 대로 답하는 가짜. 결제 번호의 앞머리가 결과를 정한다. 기본값이다
//   - Toss: 토스페이먼츠의 테스트 모드. 실제 결제창과 승인 API 를 쓰지만 돈은 나가지 않는다(테스트 키만 받는다)
//
// 주문의 코드는 어느 쪽이 꽂혔는지 모른다.
//
// 결제의 흐름은 실제 결제 대행사와 같다.
//  1. 사용자가 결제창에서 인증한다. 결제 대행사가 그 결제에 번호(payment key)를 붙여 클라이언트에 준다.
//  2. 클라이언트가 그 번호를 서버에 넘긴다. 서버가 결제 대행사에 승인을 요청한다(Confirm). 이때 돈이 나간다.
//  3. 응답을 받지 못했으면 서버는 결과를 모른다. 나중에 조회(Lookup)하거나 결제 대행사의 알림(웹훅)으로 안다.
package payment

import (
	"context"
	"errors"

	"github.com/google/uuid"
)

// ErrUnknownOutcome 은 승인을 요청했는데 결과를 받지 못했다는 오류다(시간 초과, 연결 끊김).
// 실패가 아니다. 돈이 나갔을 수도 있고 아닐 수도 있다. 이 오류를 실패로 다루면 돈을 받고 크레딧을 안 주게 된다.
var ErrUnknownOutcome = errors.New("결제 대행사의 답을 받지 못했습니다")

// Status 는 결제 한 건의 상태다.
type Status string

const (
	// StatusApproved 는 승인되었다는 뜻이다. 돈이 나갔다.
	StatusApproved Status = "approved"
	// StatusDeclined 는 거절되었다는 뜻이다. 돈이 나가지 않았다.
	StatusDeclined Status = "declined"
	// StatusPending 은 결제 대행사도 아직 결과를 모른다는 뜻이다. 조회에서만 나온다.
	StatusPending Status = "pending"
)

// Request 는 승인 요청 하나다.
type Request struct {
	// PaymentKey 는 결제 대행사가 결제창에서 붙여 준 번호다.
	PaymentKey string
	// OrderID 는 이 서버의 주문 번호다.
	OrderID uuid.UUID
	// Amount 는 받을 돈이다. 원(KRW)이다. 주문에 적힌 값을 보낸다. 클라이언트가 보낸 값이 아니다.
	Amount int64
}

// Result 는 결제 한 건의 결과다.
type Result struct {
	Status Status
	// Code 는 거절된 이유다. 결제 대행사가 준 글자다. 거절일 때만 있다.
	Code string
}

// Provider 는 결제 대행사의 모양이다.
type Provider interface {
	// Confirm 은 결제의 승인을 요청한다. 결과를 받지 못했으면 ErrUnknownOutcome 이다.
	// 같은 요청을 다시 보내도 돈이 두 번 나가지 않아야 한다.
	Confirm(ctx context.Context, request Request) (Result, error)
	// Lookup 은 결제 번호로 지금의 결과를 묻는다. 승인을 요청하고 답을 못 받았을 때 쓴다.
	// request 에는 그 결제가 치러야 할 주문과 금액을 함께 넘긴다. 결제 대행사가 아는 결제가
	// 다른 주문의 것이거나 금액이 다르면 이 주문의 결제가 아니다. 그때는 거절(StatusDeclined)이다.
	// 결과를 받지 못했으면 ErrUnknownOutcome 이다.
	Lookup(ctx context.Context, request Request) (Result, error)
}
