// billing-server/internal/httpapi/webhook.go

package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 결제 대행사가 결과를 알려 주는 주소. 승인을 요청하고 답을 받지 못한 주문을 마저 끝내는 보조 수단이다.
//
// 이 주소는 로그인이 필요 없다. 결제 대행사는 사용자의 토큰이 없다. 그 대신 본문의 서명을 확인한다.
// 서명이 맞아도 본문에 적힌 결과를 믿지 않는다. 주문 번호와 결제 번호만 읽고, 결과는 결제 대행사에 다시 묻는다.

// PaymentNotifier 는 결제 대행사의 알림을 처리하는 것의 모양이다. *order.Service 가 이 모양이다.
type PaymentNotifier interface {
	Notify(ctx context.Context, orderID uuid.UUID, paymentKey string) error
}

// webhookRequest 는 알림의 본문에서 읽는 것이다.
type webhookRequest struct {
	OrderID    uuid.UUID `json:"order_id"`
	PaymentKey string    `json:"payment_key"`
}

// webhookBody 는 알림에 대한 응답이다. 받았다는 것만 알린다. 주문이 어떻게 되었는지는 싣지 않는다.
type webhookBody struct {
	Received bool `json:"received"`
}

// paymentWebhook 은 결제 대행사의 알림을 받는 핸들러를 만든다.
//   - 서명이 맞지 않는다 -> 401
//   - 본문을 읽지 못한다 -> 400
//   - 결제 대행사에 결과를 묻지 못했다 -> 503. 결제 대행사가 알림을 다시 보낸다
//   - 그 밖에는 200. 끝낼 것이 없는 알림(모르는 주문, 이미 끝난 주문)도 200 이다. 다시 보낼 까닭이 없다
func paymentWebhook(notifier PaymentNotifier, secret string, now func() time.Time) gin.HandlerFunc {
	return func(c *gin.Context) {
		// 서명은 받은 바이트 그대로에 대한 것이다. JSON 으로 읽기 전의 본문을 확인한다
		raw, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, maxBodyBytes))
		if err != nil {
			badRequest(c, "알림의 본문을 읽지 못했습니다.")
			return
		}
		if err := payment.VerifySignature(secret, c.GetHeader(payment.SignatureHeader), raw, now()); err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, errorBody{Detail: "알림의 서명이 맞지 않습니다."})
			return
		}
		var request webhookRequest
		if err := json.Unmarshal(raw, &request); err != nil || request.OrderID == uuid.Nil || request.PaymentKey == "" {
			badRequest(c, "알림의 본문에 order_id 와 payment_key 가 있어야 합니다.")
			return
		}
		if err := notifier.Notify(c.Request.Context(), request.OrderID, request.PaymentKey); err != nil {
			_ = c.Error(err)
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, errorBody{Detail: "지금은 알림을 처리할 수 없습니다. 다시 보내 주세요."})
			return
		}
		c.JSON(http.StatusOK, webhookBody{Received: true})
	}
}
