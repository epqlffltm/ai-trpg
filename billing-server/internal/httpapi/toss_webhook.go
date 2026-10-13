// billing-server/internal/httpapi/toss_webhook.go

package httpapi

import (
	"io"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 토스페이먼츠가 결제의 상태가 바뀌었다고 알려 주는 주소. 개발자센터의 웹훅 메뉴에 이 주소를 등록한다.
//
// 토스페이먼츠의 이 알림에는 서명이 없다. 그래서 누구나 부를 수 있다고 보고 만든다.
//   - 본문의 결과(status)를 믿지 않는다. 주문 번호와 결제 번호만 읽는다(payment.ReadTossNotification)
//   - 그 결제 번호로 진행 중인(confirming, refunding) 주문이 있을 때만 토스페이먼츠에 다시 묻는다(order.Notify).
//     주문 번호와 결제 번호를 둘 다 모르는 쪽은 토스페이먼츠를 부르게 할 수도 없다
//
// 토스페이먼츠는 10초 안에 200 을 받지 못하면 같은 알림을 일곱 번까지 다시 보낸다(1분에서 약 3일 뒤까지).
// 다시 받아도 한 번만 처리되므로, 묻다가 늦어지거나 실패하면 다시 보내게 둔다.

// TossWebhookPath 는 토스페이먼츠의 알림을 받는 주소다.
const TossWebhookPath = APIPrefix + "/webhooks/toss"

// tossWebhook 은 토스페이먼츠의 알림을 받는 핸들러를 만든다.
//   - 본문을 읽지 못한다 -> 400
//   - 토스페이먼츠에 결과를 묻지 못했다 -> 503. 토스페이먼츠가 알림을 다시 보낸다
//   - 그 밖에는 200. 다루지 않는 종류의 알림, 끝낼 것이 없는 알림도 200 이다. 다시 보낼 까닭이 없다
func tossWebhook(notifier PaymentNotifier) gin.HandlerFunc {
	return func(c *gin.Context) {
		raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, payment.TossNotificationMaxBytes))
		if err != nil {
			badRequest(c, "알림의 본문을 읽지 못했습니다.")
			return
		}
		notification, relevant, err := payment.ReadTossNotification(raw)
		if err != nil {
			badRequest(c, err.Error()+".")
			return
		}
		if !relevant {
			c.JSON(http.StatusOK, webhookBody{Received: true})
			return
		}
		if err := notifier.Notify(c.Request.Context(), notification.OrderID, notification.PaymentKey); err != nil {
			_ = c.Error(err)
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, errorBody{Detail: "지금은 알림을 처리할 수 없습니다. 다시 보내 주세요."})
			return
		}
		c.JSON(http.StatusOK, webhookBody{Received: true})
	}
}
