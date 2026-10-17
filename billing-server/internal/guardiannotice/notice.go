// billing-server/internal/guardiannotice/notice.go

// Package guardiannotice 는 미성년자의 결제를 보호자에게 알리는 일이다(#352).
//
// 이 서버는 보호자의 이메일을 모른다. 알릴 일을 인증 서버에 보내고, 인증 서버가 보호자의 메일로 알린다.
// 일은 둘로 나뉜다. 정리 작업(cmd/sweeper)이 한 바퀴마다 둘을 차례로 한다(Round).
//
//  1. 적기: 최근에 결제와 청약철회가 끝난 주문 가운데 결제한 날 미성년자였던 것을 찾아 적는다(guardian_notices)
//  2. 보내기: 적힌 것을 인증 서버에 보낸다. 실패하면 간격을 늘려 다시 보낸다. 버리지 않는다
//
// 알릴 일을 결제를 끝내는 코드에서 적지 않고 주문에서 찾는 까닭: 결제를 끝내는 길이 여럿이다(승인, 가상계좌의 입금,
// 대사, 운영자의 결정). 하나라도 빠뜨리면 그 결제는 알리지 않는다. 주문의 상태는 어느 길로 끝났든 남는다.
//
// 이 일은 알림이다. 결제를 막거나 되돌리지 않는다. 결제를 막는 것은 결제 자격이다(internal/eligibility).
package guardiannotice

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Kind 는 알리는 일의 종류다. DB 의 guardian_notices.kind 와 인증 서버에 보내는 kind 에 이 글자가 그대로 간다.
type Kind string

const (
	// KindPaid 는 결제가 끝났다는 것이다. 가상계좌는 입금되었을 때다.
	KindPaid Kind = "paid"
	// KindRefunded 는 청약철회(환불)가 끝났다는 것이다.
	KindRefunded Kind = "refunded"
)

// Notice 는 보호자에게 알릴 일 하나다.
type Notice struct {
	OrderID   uuid.UUID
	Kind      Kind
	UserID    uuid.UUID
	ProductID string
	// Price 는 원(KRW)이다.
	Price   int64
	Credits int64
	// OccurredAt 은 결제나 청약철회가 끝난 시각이다.
	OccurredAt time.Time
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
