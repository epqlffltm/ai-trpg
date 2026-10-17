// billing-server/internal/httpapi/orders.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// 크레딧을 사는 주소들. 흐름은 실제 결제 대행사를 쓸 때와 같다.
//
//  1. GET  /products             무엇을 얼마에 파는지 본다
//  2. POST /orders               주문을 만든다(Idempotency-Key 머리말이 있어야 한다)
//  3. (결제창에서 인증하고 결제 번호를 받는다. 가짜 결제 대행사에서는 정해진 앞머리의 번호를 지어 쓴다)
//  4. POST /orders/{id}/confirm  결제 번호를 넘겨 승인을 요청한다. 승인되면 크레딧이 들어온다
//  5. GET  /orders/{id}          결과를 모르는 채로 끝났으면 나중에 다시 본다
//  6. POST /orders/{id}/refund   청약철회. 치른 지 7일 안이고 그 주문의 크레딧이 하나도 줄지 않았으면 전액을 취소한다

const (
	// IdempotencyHeader 는 주문을 만들 때 중복 방지 키를 싣는 머리말이다.
	IdempotencyHeader = "Idempotency-Key"
	// maxBodyBytes 는 요청의 본문으로 받는 가장 큰 크기다. 이 주소들의 본문은 수십 바이트다.
	maxBodyBytes = 16 << 10
)

// OrderService 는 주문을 만들고 치르는 것의 모양이다. *order.Service 가 이 모양이다.
type OrderService interface {
	Create(ctx context.Context, userID uuid.UUID, productID string, idempotencyKey string) (order.Order, bool, error)
	Get(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (order.Order, error)
	Confirm(ctx context.Context, userID uuid.UUID, orderID uuid.UUID, paymentKey string) (order.Order, error)
	Refund(ctx context.Context, userID uuid.UUID, orderID uuid.UUID) (order.Order, error)
}

// productBody 는 상품 하나의 응답 모양이다.
type productBody struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	// Price 는 원(KRW)이다. 원에는 소수가 없어서 숫자로 준다.
	Price   int64         `json:"price"`
	Credits credit.Amount `json:"credits"`
}

// productsBody 는 상품 목록의 응답 모양이다.
type productsBody struct {
	Products []productBody `json:"products"`
}

// createOrderRequest 는 주문을 만드는 요청의 본문이다. 값과 크레딧의 양은 받지 않는다. 서버가 상품에서 찾는다.
type createOrderRequest struct {
	ProductID string `json:"product_id"`
}

// confirmOrderRequest 는 승인을 요청하는 본문이다. 금액은 받지 않는다. 주문에 적힌 값을 쓴다.
type confirmOrderRequest struct {
	PaymentKey string `json:"payment_key"`
}

// orderBody 는 주문의 응답 모양이다. 결제 번호는 싣지 않는다. 클라이언트가 이미 알고 있고, 다시 내보낼 까닭이 없다.
type orderBody struct {
	ID        uuid.UUID     `json:"id"`
	ProductID string        `json:"product_id"`
	Price     int64         `json:"price"`
	Credits   credit.Amount `json:"credits"`
	Status    order.Status  `json:"status"`
	// FailureCode 는 거절된 이유다. 거절되지 않았으면 null 이다.
	FailureCode *string   `json:"failure_code"`
	CreatedAt   time.Time `json:"created_at"`
	// ExpiresAt 은 주문의 만료 시각이다. 이때까지 승인을 요청하지 않으면 주문은 expired 로 끝난다.
	ExpiresAt time.Time `json:"expires_at"`
	// PaidAt 은 치른 시각이다. 치르지 않았으면 null 이다.
	PaidAt *time.Time `json:"paid_at"`
	// Refundable 은 지금 청약철회할 수 있는지다. 화면이 환불 단추를 보일지 정한다. 판단은 요청을 받을 때 서버가 다시 한다.
	Refundable bool `json:"refundable"`
	// RefundableUntil 은 청약철회를 받는 마지막 시각이다. 치르지 않았으면 null 이다.
	RefundableUntil *time.Time `json:"refundable_until"`
	// RefundedAt 은 환불된 시각이다. refunded 가 아니면 null 이다.
	RefundedAt *time.Time `json:"refunded_at"`
}

// listProducts 는 파는 상품을 돌려준다.
func listProducts(c *gin.Context) {
	products := catalog.All()
	body := productsBody{Products: make([]productBody, 0, len(products))}
	for _, product := range products {
		body.Products = append(body.Products, productBody{
			ID: product.ID, Name: product.Name, Price: product.Price, Credits: product.Credits,
		})
	}
	c.JSON(http.StatusOK, body)
}

// createOrder 는 토큰의 주인의 주문을 만드는 핸들러를 만든다.
// 새로 만들었으면 201, 같은 키로 이미 만든 주문을 돌려주면 200 이다.
func createOrder(orders OrderService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request createOrderRequest
		if !readJSON(c, &request) {
			return
		}
		created, isNew, err := orders.Create(c.Request.Context(), currentUser(c).UserID, request.ProductID, c.GetHeader(IdempotencyHeader))
		if err != nil {
			orderError(c, err)
			return
		}
		status := http.StatusOK
		if isNew {
			status = http.StatusCreated
		}
		c.JSON(status, toOrderBody(created))
	}
}

// getOrder 는 토큰의 주인의 주문 하나를 돌려주는 핸들러를 만든다.
func getOrder(orders OrderService) gin.HandlerFunc {
	return func(c *gin.Context) {
		orderID, ok := orderIDParam(c)
		if !ok {
			return
		}
		found, err := orders.Get(c.Request.Context(), currentUser(c).UserID, orderID)
		if err != nil {
			orderError(c, err)
			return
		}
		c.JSON(http.StatusOK, toOrderBody(found))
	}
}

// confirmOrder 는 결제의 승인을 요청하는 핸들러를 만든다.
// 결과가 났으면(승인이든 거절이든) 200, 아직 결과를 모르면 202 다. 어느 쪽이든 본문의 status 가 지금의 상태다.
func confirmOrder(orders OrderService) gin.HandlerFunc {
	return func(c *gin.Context) {
		orderID, ok := orderIDParam(c)
		if !ok {
			return
		}
		var request confirmOrderRequest
		if !readJSON(c, &request) {
			return
		}
		confirmed, err := orders.Confirm(c.Request.Context(), currentUser(c).UserID, orderID, request.PaymentKey)
		if err != nil {
			orderError(c, err)
			return
		}
		status := http.StatusOK
		if confirmed.Status == order.StatusConfirming {
			status = http.StatusAccepted
		}
		c.JSON(status, toOrderBody(confirmed))
	}
}

// refundOrder 는 청약철회를 요청하는 핸들러를 만든다. 본문은 받지 않는다. 전액을 취소하고, 이유는 서버가 정한다.
// 환불되었으면 200, 크레딧은 뺐지만 결제 대행사의 답을 아직 모르면 202 다(나중에 다시 보내거나 주문을 본다).
// 할 수 없는 청약철회(기한이 지났다, 크레딧을 썼다, 치른 주문이 아니다, 결제 대행사가 거절했다)는 409 다.
func refundOrder(orders OrderService) gin.HandlerFunc {
	return func(c *gin.Context) {
		orderID, ok := orderIDParam(c)
		if !ok {
			return
		}
		refunded, err := orders.Refund(c.Request.Context(), currentUser(c).UserID, orderID)
		if err != nil {
			orderError(c, err)
			return
		}
		status := http.StatusOK
		if refunded.Status == order.StatusRefunding {
			status = http.StatusAccepted
		}
		c.JSON(status, toOrderBody(refunded))
	}
}

// orderIDParam 은 주소의 주문 번호를 읽는다. UUID 가 아니면 404 로 답하고 false 를 돌려준다.
// 번호의 모양이 틀린 것과 그런 주문이 없는 것을 나누지 않는다.
func orderIDParam(c *gin.Context) (uuid.UUID, bool) {
	orderID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		notFound(c, order.ErrNotFound.Error())
		return uuid.Nil, false
	}
	return orderID, true
}

// readJSON 은 요청의 본문을 target 에 읽는다. 읽지 못하면 400 으로 답하고 false 를 돌려준다.
func readJSON(c *gin.Context, target any) bool {
	return readJSONWithCode(c, target, "")
}

// readJSONWithCode 는 readJSON 과 같되, 읽지 못했을 때의 400 에 오류의 이름(code)을 싣는다. 우리 서버들이 부르는 주소가 쓴다.
func readJSONWithCode(c *gin.Context, target any, code string) bool {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxBodyBytes)
	if err := c.ShouldBindJSON(target); err != nil {
		abort(c, http.StatusBadRequest, code, "요청의 본문을 JSON 으로 읽지 못했습니다.")
		return false
	}
	return true
}

// orderError 는 주문을 다루다 난 오류를 HTTP 응답으로 바꾼다.
func orderError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, order.ErrInvalidKey), errors.Is(err, order.ErrUnknownProduct), errors.Is(err, order.ErrInvalidPaymentKey):
		badRequest(c, err.Error()+".")
	case errors.Is(err, order.ErrNotFound):
		notFound(c, err.Error()+".")
	case errors.Is(err, order.ErrKeyReused), errors.Is(err, order.ErrPaymentKeyMismatch), errors.Is(err, order.ErrPaymentKeyUsed),
		errors.Is(err, order.ErrExpired), errors.Is(err, order.ErrNotRefundable), errors.Is(err, order.ErrRefundWindowClosed),
		errors.Is(err, order.ErrCreditsUsed), errors.Is(err, order.ErrRefundBusy), errors.Is(err, order.ErrRefundRefused):
		conflict(c, err.Error()+".")
	case errors.Is(err, order.ErrTimedOut):
		unavailable(c, order.ErrTimedOut.Error()+".")
	case errors.Is(err, eligibility.ErrVerificationRequired):
		abort(c, http.StatusForbidden, codePaymentVerificationRequired, err.Error()+".")
	case errors.Is(err, eligibility.ErrGuardianConsentRequired):
		abort(c, http.StatusForbidden, codePaymentGuardianConsentRequired, err.Error()+".")
	default:
		internalError(c, err)
	}
}

// toOrderBody 는 주문을 응답의 모양으로 바꾼다.
func toOrderBody(o order.Order) orderBody {
	body := orderBody{
		ID:        o.ID,
		ProductID: o.ProductID,
		Price:     o.Price,
		Credits:   o.Credits,
		Status:    o.Status,
		CreatedAt: o.CreatedAt,
		ExpiresAt: o.ExpiresAt,
		PaidAt:    o.PaidAt,

		Refundable:      o.Refundable,
		RefundableUntil: o.RefundableUntil,
		RefundedAt:      o.RefundedAt,
	}
	if o.FailureCode != "" {
		body.FailureCode = &o.FailureCode
	}
	return body
}
