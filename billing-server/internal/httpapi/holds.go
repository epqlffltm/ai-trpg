// billing-server/internal/httpapi/holds.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 홀드를 걸고, 확정하고, 돌려주고, 연장하는 주소들. 게임 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/holds           크레딧을 먼저 빼 둔다
//	POST /service/holds/capture   확정한다. 크레딧은 돌아오지 않는다
//	POST /service/holds/release   돌려준다
//	POST /service/holds/extend    만료 시각을 지금부터 HOLD_TTL 뒤로 민다
//
// 셋 다 이름표(reference)로 홀드를 가리킨다. 결제 서버가 지은 번호가 아니라 부르는 서버가 지은 이름표다.
// 부르는 서버가 응답을 받지 못해도 같은 이름표로 다시 부르면 된다. 홀드의 번호를 받아 적어 둘 필요가 없다.

// HoldService 는 홀드를 다루는 것의 모양이다. *hold.Service 가 이 모양이다.
type HoldService interface {
	Place(ctx context.Context, source string, userID uuid.UUID, reference string, priceCode string) (hold.Hold, bool, error)
	Capture(ctx context.Context, source string, reference string) (hold.Hold, error)
	Release(ctx context.Context, source string, reference string) (hold.Hold, error)
	Extend(ctx context.Context, source string, reference string) (hold.Hold, error)
}

// placeHoldRequest 는 홀드를 거는 요청의 본문이다. 금액은 받지 않는다. 가격표의 이름만 받는다.
type placeHoldRequest struct {
	// UserID 는 크레딧을 낼 사용자다. 인증 서버의 public_id 다.
	UserID    uuid.UUID `json:"user_id"`
	Reference string    `json:"reference"`
	PriceCode string    `json:"price_code"`
}

// settleHoldRequest 는 홀드를 확정하거나 돌려주는 요청의 본문이다.
type settleHoldRequest struct {
	Reference string `json:"reference"`
}

// holdBody 는 홀드의 응답 모양이다.
type holdBody struct {
	ID        uuid.UUID     `json:"id"`
	UserID    uuid.UUID     `json:"user_id"`
	Reference string        `json:"reference"`
	PriceCode string        `json:"price_code"`
	Amount    credit.Amount `json:"amount"`
	Status    hold.Status   `json:"status"`
	CreatedAt time.Time     `json:"created_at"`
	// ExpiresAt 은 만료 시각이다. 이때까지 확정하거나 연장하지 않으면 결제 서버가 돌려준다.
	ExpiresAt time.Time `json:"expires_at"`
	// SettledAt 은 확정하거나 돌려준 시각이다. 아직이면 null 이다.
	SettledAt *time.Time `json:"settled_at"`
	// ReleaseReason 은 돌려준 이유다(requested, expired). 돌려주지 않았으면 null 이다.
	ReleaseReason *hold.ReleaseReason `json:"release_reason"`
}

// placeHold 는 홀드를 거는 핸들러를 만든다. 새로 걸었으면 201, 같은 이름표로 이미 건 홀드를 돌려주면 200 이다.
func placeHold(holds HoldService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request placeHoldRequest
		if !readJSON(c, &request) {
			return
		}
		if request.UserID == uuid.Nil {
			badRequest(c, "user_id 가 있어야 합니다.")
			return
		}
		placed, isNew, err := holds.Place(c.Request.Context(), caller(c), request.UserID, request.Reference, request.PriceCode)
		if err != nil {
			holdError(c, err)
			return
		}
		status := http.StatusOK
		if isNew {
			status = http.StatusCreated
		}
		c.JSON(status, toHoldBody(placed))
	}
}

// captureHold 는 홀드를 확정하는 핸들러를 만든다.
func captureHold(holds HoldService) gin.HandlerFunc {
	// holds.Capture 를 값으로 바로 넘기지 않는다. 요청이 왔을 때 부른다. 라우터를 만드는 순간에는 holds 가 비어 있을 수 있다(테스트)
	return settleHold(func(ctx context.Context, source string, reference string) (hold.Hold, error) {
		return holds.Capture(ctx, source, reference)
	})
}

// releaseHold 는 홀드를 돌려주는 핸들러를 만든다.
func releaseHold(holds HoldService) gin.HandlerFunc {
	return settleHold(func(ctx context.Context, source string, reference string) (hold.Hold, error) {
		return holds.Release(ctx, source, reference)
	})
}

// extendHold 는 홀드의 만료 시각을 미는 핸들러를 만든다. 이미 끝난 홀드면 409 다.
func extendHold(holds HoldService) gin.HandlerFunc {
	return settleHold(func(ctx context.Context, source string, reference string) (hold.Hold, error) {
		return holds.Extend(ctx, source, reference)
	})
}

// settleHold 는 이름표를 읽어 settle(확정, 반환, 연장)에 넘기고 끝난 뒤의 홀드를 돌려주는 핸들러를 만든다.
func settleHold(settle func(ctx context.Context, source string, reference string) (hold.Hold, error)) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request settleHoldRequest
		if !readJSON(c, &request) {
			return
		}
		settled, err := settle(c.Request.Context(), caller(c), request.Reference)
		if err != nil {
			holdError(c, err)
			return
		}
		c.JSON(http.StatusOK, toHoldBody(settled))
	}
}

// holdError 는 홀드를 다루다 난 오류를 HTTP 응답으로 바꾼다.
func holdError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, hold.ErrInvalidReference), errors.Is(err, hold.ErrUnknownPrice):
		badRequest(c, err.Error()+".")
	case errors.Is(err, wallet.ErrInsufficient):
		// 402 는 "값을 치러야 한다"는 상태 코드다. 부르는 서버가 다른 오류와 가려서 사용자에게 충전을 권할 수 있다
		c.AbortWithStatusJSON(http.StatusPaymentRequired, errorBody{Detail: err.Error() + "."})
	case errors.Is(err, hold.ErrNotFound):
		notFound(c, err.Error()+".")
	case errors.Is(err, hold.ErrReferenceReused), errors.Is(err, hold.ErrAlreadyCaptured), errors.Is(err, hold.ErrAlreadyReleased):
		conflict(c, err.Error()+".")
	default:
		internalError(c, err)
	}
}

// toHoldBody 는 홀드를 응답의 모양으로 바꾼다.
func toHoldBody(h hold.Hold) holdBody {
	body := holdBody{
		ID:        h.ID,
		UserID:    h.UserID,
		Reference: h.Reference,
		PriceCode: h.PriceCode,
		Amount:    h.Amount,
		Status:    h.Status,
		CreatedAt: h.CreatedAt,
		ExpiresAt: h.ExpiresAt,
		SettledAt: h.SettledAt,
	}
	if h.ReleaseReason != "" {
		body.ReleaseReason = &h.ReleaseReason
	}
	return body
}
