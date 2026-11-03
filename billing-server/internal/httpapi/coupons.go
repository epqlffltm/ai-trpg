// billing-server/internal/httpapi/coupons.go

package httpapi

import (
	"context"
	"errors"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 쿠폰의 주소(#979).
//
//	POST /coupons/redeem  코드를 넣어 실버를 받는다(로그인)
//
// 누가 받는지는 토큰에서만 정한다. 본문에는 코드만 받는다. 쿠폰을 만들고 멈추는 것은 운영자의 명령이다(cmd/coupons).

// CouponRedeemer 는 쿠폰을 받는 것의 모양이다. *coupon.Service 가 이 모양이다.
type CouponRedeemer interface {
	Redeem(ctx context.Context, userID uuid.UUID, code string) (coupon.Redemption, error)
}

// couponRequest 는 쿠폰을 넣는 요청의 본문이다.
type couponRequest struct {
	Code string `json:"code"`
}

// couponBody 는 받은 쿠폰의 응답 모양이다.
type couponBody struct {
	// Code 는 받은 쿠폰의 코드다(대문자로 바꾼 것).
	Code   string        `json:"code"`
	Silver credit.Amount `json:"silver"`
	// ExpiresAt 은 이번에 받은 실버가 사라지는 시각이다.
	ExpiresAt time.Time `json:"expires_at"`
}

// couponConflicts 는 있는 쿠폰이지만 받을 수 없는 까닭과 그 오류의 이름이다. 모두 409 다.
var couponConflicts = []struct {
	err  error
	code string
}{
	{coupon.ErrAlreadyRedeemed, codeCouponAlreadyRedeemed},
	{coupon.ErrExhausted, codeCouponExhausted},
	{coupon.ErrEnded, codeCouponEnded},
	{coupon.ErrStopped, codeCouponEnded},
	{coupon.ErrNotStarted, codeCouponNotStarted},
}

// redeemCoupon 은 토큰의 주인에게 넣은 코드의 실버를 주는 핸들러를 만든다.
//   - 줬다 -> 201
//   - 본문이 JSON 이 아니다 -> 400
//   - 그런 코드가 없다(모양이 틀린 것도) -> 404 coupon.not_found
//   - 본인인증 전이다 -> 403 coupon.verification_required
//   - 이미 받았다, 다 찼다, 지났다(멈춘 것도), 아직이다 -> 409 coupon.already_redeemed, exhausted, ended, not_started
//   - 너무 자주 틀렸다 -> 429 coupon.too_many_attempts. Retry-After(초)에 다시 넣을 수 있다
func redeemCoupon(service CouponRedeemer) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request couponRequest
		if !readJSON(c, &request) {
			return
		}
		redemption, err := service.Redeem(c.Request.Context(), currentUser(c).UserID, request.Code)
		if err != nil {
			couponError(c, err)
			return
		}
		c.JSON(http.StatusCreated, couponBody{Code: redemption.Code, Silver: redemption.Silver, ExpiresAt: redemption.ExpiresAt})
	}
}

// couponError 는 쿠폰을 받지 못한 까닭을 응답으로 바꾼다.
func couponError(c *gin.Context, err error) {
	var tooMany *coupon.TooManyAttemptsError
	switch {
	case errors.As(err, &tooMany):
		c.Header("Retry-After", strconv.Itoa(retryAfterSeconds(tooMany.RetryAfter)))
		abort(c, http.StatusTooManyRequests, codeCouponTooManyAttempts, err.Error()+".")
	case errors.Is(err, coupon.ErrVerificationRequired):
		abort(c, http.StatusForbidden, codeCouponVerificationRequired, err.Error()+".")
	case errors.Is(err, coupon.ErrNotFound):
		abort(c, http.StatusNotFound, codeCouponNotFound, err.Error()+".")
	default:
		for _, known := range couponConflicts {
			if errors.Is(err, known.err) {
				abort(c, http.StatusConflict, known.code, err.Error()+".")
				return
			}
		}
		internalError(c, err)
	}
}

// retryAfterSeconds 는 다시 넣을 수 있을 때까지를 올림한 초다. 1 초보다 짧아도 1 이다.
func retryAfterSeconds(wait time.Duration) int {
	return max(1, int(math.Ceil(wait.Seconds())))
}
