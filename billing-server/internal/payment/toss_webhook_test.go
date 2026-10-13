// billing-server/internal/payment/toss_webhook_test.go

package payment_test

import (
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// tossOrderID 는 알림의 테스트에 쓰는 주문 번호다.
const tossOrderID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

func TestReadTossNotificationTakesOnlyTheOrderAndThePayment(t *testing.T) {
	// 문서의 모양. data 는 Payment 객체 그대로다. 상태와 금액은 읽지 않는다
	raw := `{"eventType":"PAYMENT_STATUS_CHANGED","createdAt":"2026-03-02T09:00:00.000000",
		"data":{"mId":"tosspayments","paymentKey":"tgen_20260302abcd","orderId":"` + tossOrderID + `",
		"status":"DONE","totalAmount":1000,"method":"카드","cancels":null}}`

	got, relevant, err := payment.ReadTossNotification([]byte(raw))

	want := payment.Notification{OrderID: uuid.MustParse(tossOrderID), PaymentKey: "tgen_20260302abcd"}
	if err != nil || !relevant || got != want {
		t.Errorf("알림 = %+v, %v, %v. 기대 = %+v", got, relevant, err, want)
	}
}

func TestReadTossNotificationIgnoresWhatItDoesNotHandle(t *testing.T) {
	cases := map[string]string{
		"가상계좌의 입금 알림":      `{"createdAt":"2026-03-02T09:00:00.000000","secret":"s","status":"DONE","transactionKey":"t","orderId":"` + tossOrderID + `"}`,
		"취소 상태 알림":         `{"eventType":"CANCEL_STATUS_CHANGED","createdAt":"x","data":{"transactionKey":"t"}}`,
		"지급대행 알림":          `{"eventType":"payout.changed","createdAt":"x","data":{}}`,
		"이 서버의 주문 번호가 아니다": `{"eventType":"PAYMENT_STATUS_CHANGED","data":{"paymentKey":"tgen_1","orderId":"order-2026-0001"}}`,
	}
	for name, raw := range cases {
		t.Run(name, func(t *testing.T) {
			got, relevant, err := payment.ReadTossNotification([]byte(raw))
			if err != nil || relevant {
				t.Errorf("알림 = %+v, %v, %v. 다루지 않는 알림이어야 한다", got, relevant, err)
			}
		})
	}
}

func TestReadTossNotificationRefusesWhatItCannotRead(t *testing.T) {
	cases := map[string]string{
		"JSON 이 아니다":     `eventType=PAYMENT_STATUS_CHANGED`,
		"비었다":            ``,
		"data 가 없다":      `{"eventType":"PAYMENT_STATUS_CHANGED"}`,
		"결제 번호가 없다":      `{"eventType":"PAYMENT_STATUS_CHANGED","data":{"orderId":"` + tossOrderID + `"}}`,
		"data 가 객체가 아니다": `{"eventType":"PAYMENT_STATUS_CHANGED","data":"DONE"}`,
	}
	for name, raw := range cases {
		t.Run(name, func(t *testing.T) {
			_, relevant, err := payment.ReadTossNotification([]byte(raw))
			if !errors.Is(err, payment.ErrUnreadableNotification) || relevant {
				t.Errorf("오류 = %v, relevant = %v. ErrUnreadableNotification 이어야 한다", err, relevant)
			}
		})
	}
}
