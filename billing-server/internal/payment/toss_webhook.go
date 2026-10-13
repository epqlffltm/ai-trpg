// billing-server/internal/payment/toss_webhook.go

package payment

import (
	"encoding/json"
	"errors"

	"github.com/google/uuid"
)

// 토스페이먼츠의 알림(웹훅). 원본은 https://docs.tosspayments.com/guides/v2/webhook 과
// https://docs.tosspayments.com/reference/using-api/webhook-events 다.
//
// 다루는 알림은 결제의 상태가 바뀌었다는 것(PAYMENT_STATUS_CHANGED) 하나다. 모든 결제수단에 오고,
// 승인과 취소 어느 쪽의 결과도 이것으로 온다. 본문은 {"eventType", "createdAt", "data": Payment 객체} 다.
//
// 이 알림에는 서명이 없다(서명은 지급대행의 알림에만 붙는다). 그래서 본문에서 주문 번호와 결제 번호만 읽는다.
// 상태(status)는 읽지 않는다. 누구나 이 모양의 본문을 보낼 수 있으므로, 결과는 결제 대행사에 다시 묻는다.

// TossPaymentStatusChanged 는 결제의 상태가 바뀌었다는 알림의 종류다.
const TossPaymentStatusChanged = "PAYMENT_STATUS_CHANGED"

// TossNotificationMaxBytes 는 받는 알림 본문의 가장 큰 크기다. 결제 한 건(Payment 객체)은 몇 KB 다.
const TossNotificationMaxBytes = tossMaxResponseBytes

// ErrUnreadableNotification 은 알림의 본문이 JSON 이 아니거나 모양이 틀렸다는 오류다.
var ErrUnreadableNotification = errors.New("알림의 본문을 읽지 못했습니다")

// Notification 은 알림에서 읽은 것이다. 어느 주문의 어느 결제인지만 담는다.
type Notification struct {
	OrderID    uuid.UUID
	PaymentKey string
}

// tossNotification 은 토스페이먼츠의 알림 본문에서 읽는 것이다.
type tossNotification struct {
	EventType string       `json:"eventType"`
	Data      *tossPayment `json:"data"`
}

// ReadTossNotification 은 토스페이먼츠의 알림 본문을 읽는다.
// 다룰 알림이면 relevant 가 true 다. 다른 종류의 알림이거나 이 서버가 만든 주문 번호(UUID)가 아니면 false 다.
// JSON 이 아니거나, 결제의 상태 알림인데 결제 번호가 없으면 ErrUnreadableNotification 이다.
func ReadTossNotification(raw []byte) (notification Notification, relevant bool, err error) {
	var body tossNotification
	if err := json.Unmarshal(raw, &body); err != nil {
		return Notification{}, false, ErrUnreadableNotification
	}
	if body.EventType != TossPaymentStatusChanged {
		return Notification{}, false, nil
	}
	if body.Data == nil || body.Data.PaymentKey == "" {
		return Notification{}, false, ErrUnreadableNotification
	}
	orderID, err := uuid.Parse(body.Data.OrderID)
	if err != nil {
		// 같은 상점의 다른 시스템이 만든 주문일 수 있다. 이 서버가 다룰 것이 아니다
		return Notification{}, false, nil
	}
	return Notification{OrderID: orderID, PaymentKey: body.Data.PaymentKey}, true, nil
}
