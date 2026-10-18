// billing-server/internal/usernotice/notice.go

// Package usernotice 는 결제와 크레딧의 일을 사용자의 알림함에 알리는 일이다(#385). 알림함은 알림 서버에 있다.
//
// 보호자 알림(internal/guardiannotice)과 같은 방식이다. 정리 작업(cmd/sweeper)이 한 바퀴마다 차례로 한다(Round).
//
//  1. 적기: 최근에 끝난 결제와 청약철회(주문), 준 환영 크레딧(지급 묶음)을 찾아 적는다(user_notices).
//     7일 안에 사라질 무료 크레딧이 남은 사람도 적는다. 사람마다 7일에 한 번이다
//  2. 정리: 오래(StaleAfter, 7일) 보내지 못한 것은 보내지 않기로 하고, 끝난 지 30일(Retention)이 지난 것은 지운다
//  3. 보내기: 적힌 것을 알림 서버에 보낸다. 닿지 못하면 간격을 늘려 다시 보내고, 알림 서버가 받지 않으면(버그) 실패로 둔다
//
// 알릴 일을 결제를 끝내는 코드에서 적지 않고 주문과 지급 묶음에서 찾는 까닭은 보호자 알림과 같다. 결제를 끝내는 길이 여럿이다.
//
// 이 일은 알림이다. 결제와 크레딧을 바꾸지 않는다. 알림 서버가 죽어 있어도 결제는 된다.
package usernotice

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Kind 는 알리는 일의 종류다. DB 의 user_notices.kind 와 알림 서버에 보내는 kind 에 이 글자가 그대로 간다.
type Kind string

const (
	// KindOrderPaid 는 결제가 끝났다는 것이다. 가상계좌는 입금되었을 때다.
	KindOrderPaid Kind = "order.paid"
	// KindOrderRefunded 는 청약철회가 끝났다는 것이다.
	KindOrderRefunded Kind = "order.refunded"
	// KindWelcomeCredits 는 환영 크레딧을 받았다는 것이다.
	KindWelcomeCredits Kind = "credit.welcome"
	// KindCreditsExpiring 은 곧 사라질 무료 크레딧이 남았다는 것이다.
	KindCreditsExpiring Kind = "credit.expiring"
)

const (
	// LookBack 은 적을 때 거슬러 보는 기간이다. 정리 작업이 이만큼 멈춰 있었어도 그 사이의 일을 놓치지 않는다.
	// 보호자 알림(30일)보다 짧다. 사흘 지난 결제의 알림은 늦어서 쓸모가 적고, 이 기능을 처음 켤 때 지난 결제를 몰아 보내지 않는다.
	// Retention 보다 짧아야 한다. 지운 줄을 다시 적지 않는다
	LookBack = 3 * 24 * time.Hour
	// ExpiringWithin 은 사라질 크레딧을 알리는 기간이다. 이 안에 사라질 것이 남았으면 알리고, 알린 뒤 이만큼은 다시 알리지 않는다.
	ExpiringWithin = 7 * 24 * time.Hour
	// StaleAfter 는 보내지 못한 채 이만큼 지나면 보내지 않는 기간이다.
	StaleAfter = 7 * 24 * time.Hour
	// Retention 은 끝난 것(sent, failed, expired)을 두는 기간이다. 사라질 크레딧을 알렸는지 보려면 ExpiringWithin 보다 길어야 한다.
	Retention = 30 * 24 * time.Hour
)

// Notice 는 사용자에게 알릴 일 하나다.
type Notice struct {
	ID int64
	// Key 는 알림 서버가 같은 알림을 알아보는 열쇠다(source_key).
	Key    string
	UserID uuid.UUID
	Kind   Kind
	// Payload 는 알림의 내용(JSON 객체)이다. DB 에 적힌 그대로 보낸다.
	Payload []byte
}

// Delivery 는 알림 하나를 보낸 결과다.
type Delivery int

const (
	// Delivered 는 알림 서버가 받았다는 것이다(새로 넣었거나 이미 있다).
	Delivered Delivery = iota
	// Unavailable 은 닿지 못했거나 다시 보내면 될 답이라는 것이다. 다시 보낸다.
	Unavailable
	// Rejected 는 알림 서버가 받지 않았다는 것이다(같은 열쇠로 다른 알림, 모양이 틀렸다). 버그다. 다시 보내지 않는다.
	Rejected
)

// Sent 는 보낸 결과와 그 까닭의 짧은 이름이다(보내지 못했을 때). 까닭은 DB 의 last_error 와 로그에 남는다.
type Sent struct {
	Delivery Delivery
	Reason   string
}

// Sender 는 알릴 일을 알림 서버에 보내는 것이다. *HTTPSender 가 이 모양이다. 오류를 내지 않고 결과로 돌려준다.
// 같은 일을 두 번 보내도 된다. 알림 서버가 열쇠로 한 번만 둔다.
type Sender interface {
	Send(ctx context.Context, notice Notice) Sent
}

// Result 는 한 바퀴에서 한 일이다.
type Result struct {
	// Queued 는 이번에 새로 적은 수다.
	Queued int
	// Sent 는 알림 서버가 받은 수다.
	Sent int
	// Retried 는 보내지 못해 나중에 다시 보낼 수다.
	Retried int
	// Rejected 는 알림 서버가 받지 않아 실패로 둔 수다.
	Rejected int
	// Expired 는 오래되어 보내지 않기로 한 수다.
	Expired int
	// Purged 는 끝난 지 오래되어 지운 수다.
	Purged int
}

// Any 는 한 일이 있는지다.
func (r Result) Any() bool {
	return r.Queued > 0 || r.Sent > 0 || r.Retried > 0 || r.Rejected > 0 || r.Expired > 0 || r.Purged > 0
}
