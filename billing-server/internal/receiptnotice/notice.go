// billing-server/internal/receiptnotice/notice.go

// Package receiptnotice 는 결제한 본인에게 결제와 청약철회를 메일로 알리는 일이다(#553).
//
// 결제 영수증은 결제 대행사(토스페이먼츠)가 결제창에 적은 이메일로 보낸다. 이 메일은 그 영수증에 없는 것을 싣는다.
// 받은 크레딧, 청약철회의 기한과 하는 길이다. 다툼이 생겼을 때 사용자의 손에 남는 거래 확인이다(알림함은 30일 뒤 지워진다).
//
// 이 서버는 사용자의 이메일을 모른다. 알릴 일을 인증 서버에 보내고, 인증 서버가 그 계정의 메일로 알린다.
// 보호자 결제 알림(internal/guardiannotice, #352)과 같은 길이다. 정리 작업(cmd/sweeper)이 한 바퀴마다 둘을 차례로 한다(Round).
//
//  1. 적기: 최근에 결제와 청약철회가 끝난 주문을 찾아 적는다(receipt_notices). 미성년자의 것도 적는다(본인에게도 간다)
//  2. 보내기: 적힌 것을 인증 서버에 보낸다. 실패하면 간격을 늘려 다시 보낸다. 버리지 않는다
//
// 이 일은 알림이다. 결제를 막거나 되돌리지 않는다.
package receiptnotice

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// Kind 는 알리는 일의 종류다. DB 의 receipt_notices.kind 와 인증 서버에 보내는 kind 에 이 글자가 그대로 간다.
type Kind string

const (
	// KindPaid 는 결제가 끝났다는 것이다. 가상계좌는 입금되었을 때다.
	KindPaid Kind = "paid"
	// KindRefunded 는 청약철회(환불)가 끝났다는 것이다.
	KindRefunded Kind = "refunded"
)

// Notice 는 결제한 본인에게 알릴 일 하나다.
type Notice struct {
	OrderID   uuid.UUID
	Kind      Kind
	UserID    uuid.UUID
	ProductID string
	// Price 는 원(KRW)이다.
	Price   int64
	Credits int64
	// PaidAt 은 결제가 끝난 시각이다. 청약철회의 기한은 이 시각부터 센다.
	PaidAt time.Time
	// OccurredAt 은 결제나 청약철회가 끝난 시각이다.
	OccurredAt time.Time
}

// RefundableUntil 은 청약철회를 받는 마지막 시각이다(결제한 시각 + order.RefundWindow). 주문을 만들 때와 같은 규칙이다.
func (n Notice) RefundableUntil() time.Time {
	return n.PaidAt.Add(order.RefundWindow)
}

// String 은 오류와 로그에 쓰는 짧은 이름이다. 사용자는 넣지 않는다.
func (n Notice) String() string {
	return fmt.Sprintf("%s/%s", n.OrderID, n.Kind)
}

// Sender 는 알릴 일을 인증 서버에 보내는 것이다. 받았다는 답이 아니면 오류다. *HTTPSender 가 이 모양이다.
// 같은 일을 두 번 보내도 된다. 인증 서버가 주문과 종류로 한 번만 보낸다.
type Sender interface {
	Send(ctx context.Context, notice Notice) error
}

// Result 는 한 바퀴에서 한 일이다.
type Result struct {
	// Queued 는 이번에 새로 적은 수다.
	Queued int
	// Sent 는 인증 서버가 받은 수다.
	Sent int
	// Retried 는 보내지 못해 나중에 다시 보낼 수다.
	Retried int
}

// Any 는 한 일이 있는지다.
func (r Result) Any() bool {
	return r.Queued > 0 || r.Sent > 0 || r.Retried > 0
}
