// billing-server/internal/httpapi/errors.go

package httpapi

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
)

// errorBody 는 오류 응답의 모양이다. 다른 서버들과 같은 칸 이름(detail)을 쓴다.
type errorBody struct {
	Detail string `json:"detail"`
	// Code 는 부르는 서버가 읽는 오류의 이름이다(price.unknown 같은 것). detail 은 사람이 읽는 글이라 바뀔 수 있다.
	// 우리 서버들이 부르는 주소(/service/...)의 4xx 에 싣는다. 사용자가 부르는 주소에는 화면이 갈래를 나눠야 하는 것에만 싣는다
	// (결제 자격의 403: 본인인증으로 보낼지, 보호자 동의로 보낼지). 5xx 에는 없다(칸이 빠진다).
	// 5xx 는 이름으로 가릴 것이 없다. 같은 요청을 다시 보내면 된다.
	Code string `json:"code,omitempty"`
}

// 우리 서버들이 읽는 오류의 이름. 한번 정하면 바꾸지 않는다. 새 경우가 생기면 이름을 더한다.
// 이름은 "무엇.어떻게" 모양이다. README 의 "오류의 이름" 표에 같은 목록이 있다.
const (
	// codeHoldInvalidRequest 는 홀드 요청의 본문이 틀렸다는 것이다(JSON 이 아니다, user_id 가 없다, 이름표의 모양이 틀렸다).
	codeHoldInvalidRequest = "hold.invalid_request"
	// codePriceUnknown 은 가격표에 그런 이름이 없다는 것이다. 부르는 서버의 버그다.
	codePriceUnknown = "price.unknown"
	// codePriceNotForSale 은 판매를 멈춘 이름이라는 것이다. 부르는 서버의 모델 목록이 옛것이다. 목록을 다시 받으면 된다.
	codePriceNotForSale = "price.not_for_sale"
	// codeCreditInsufficient 는 크레딧이 모자라다는 것이다(402). 골드와 실버를 합쳐도 모자란다. 사용자에게 충전을 권한다.
	codeCreditInsufficient = "credit.insufficient"
	// codeCreditGoldRequired 는 프리미엄이라 골드(산 크레딧)로만 내는데 골드가 모자라다는 것이다(402).
	// 실버(무료 크레딧)가 얼마나 있든 같다. 사용자에게 "프리미엄은 골드로만"을 알린다.
	codeCreditGoldRequired = "credit.gold_required"
	// codeHoldNotFound 는 그 이름표의 홀드가 없다는 것이다.
	codeHoldNotFound = "hold.not_found"
	// codeHoldReferenceReused 는 같은 이름표로 다른 홀드(다른 사용자나 다른 가격표 이름)를 걸려 했다는 것이다.
	codeHoldReferenceReused = "hold.reference_reused"
	// codeHoldAlreadyCaptured 는 이미 확정한 홀드라는 것이다.
	codeHoldAlreadyCaptured = "hold.already_captured"
	// codeHoldAlreadyReleased 는 이미 돌려준 홀드라는 것이다. 만료되어 돌려준 것도 같다.
	codeHoldAlreadyReleased = "hold.already_released"
	// codeEligibilityInvalidRequest 는 결제 자격의 본문이 틀렸다는 것이다(칸이 빠졌다, 날짜의 모양이 틀렸다, 버전이 0 이하다).
	codeEligibilityInvalidRequest = "eligibility.invalid_request"
	// codePaymentVerificationRequired 는 본인인증을 하지 않아 결제할 수 없다는 것이다(403). 화면은 본인인증으로 보낸다.
	codePaymentVerificationRequired = "payment.verification_required"
	// codePaymentGuardianConsentRequired 는 미성년자인데 보호자가 동의하지 않았다는 것이다(403). 화면은 보호자 동의로 보낸다.
	codePaymentGuardianConsentRequired = "payment.guardian_consent_required"
	// codeServiceBadRequest 는 서명을 확인하려고 본문을 읽지 못했다는 것이다(너무 크다).
	codeServiceBadRequest = "service.bad_request"
	// codeServiceBadSignature 는 요청의 서명이 맞지 않다는 것이다(비밀이 다르다, 시각이 너무 어긋났다).
	codeServiceBadSignature = "service.bad_signature"
)

// abort 는 오류로 답하고 요청을 끝낸다. code 가 비면 code 칸이 빠진다.
func abort(c *gin.Context, status int, code string, detail string) {
	c.AbortWithStatusJSON(status, errorBody{Detail: detail, Code: code})
}

// badRequest 는 요청의 값이 틀렸을 때의 응답이다. 무엇을 고치면 되는지 적는다.
func badRequest(c *gin.Context, detail string) {
	abort(c, http.StatusBadRequest, "", detail)
}

// notFound 는 그런 것이 없을 때의 응답이다. 남의 것도 없는 것으로 답한다.
func notFound(c *gin.Context, detail string) {
	abort(c, http.StatusNotFound, "", detail)
}

// conflict 는 요청이 지금의 상태와 맞지 않을 때의 응답이다. 같은 요청을 다시 보내도 되지 않는다.
func conflict(c *gin.Context, detail string) {
	abort(c, http.StatusConflict, "", detail)
}

// unavailable 은 지금은 끝내지 못했지만 다시 보내면 될 때의 응답이다. 원인은 서버의 기록에만 남긴다.
func unavailable(c *gin.Context, detail string) {
	abort(c, http.StatusServiceUnavailable, "", detail)
}

// retryDetail 은 지금은 끝내지 못했지만 같은 요청을 다시 보내면 될 때의 응답이다.
// DB 가 시간 제한으로 끊었거나 요청의 마감에 걸렸다. 어느 쪽이든 그 쿼리는 적히지 않았다.
const retryDetail = "지금은 요청을 끝내지 못했습니다. 잠시 뒤 같은 요청을 다시 보내 주세요."

// internalError 는 서버 쪽의 문제로 처리하지 못했을 때의 응답이다.
// 원인은 서버의 기록에만 남기고 응답에는 싣지 않는다. DB 의 오류에는 테이블 이름과 쿼리가 들어 있다.
// 다시 보내면 되는 것(retryable)은 503 이다. 클라이언트가 이미 떠났으면 서버의 오류로 적지 않는다(499).
func internalError(c *gin.Context, cause error) {
	if clientLeft(c, cause) {
		c.AbortWithStatus(statusClientClosed)
		return
	}
	// 요청을 기록하는 미들웨어(requestLogging)가 이 오류를 요청의 식별자와 함께 적는다
	_ = c.Error(cause)
	if retryable(cause) {
		unavailable(c, retryDetail)
		return
	}
	c.AbortWithStatusJSON(http.StatusInternalServerError, errorBody{
		Detail: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
	})
}

// retryable 은 같은 요청을 다시 보내면 되는 오류인지 본다.
// DB 가 시간 제한으로 끊은 것(#296)과 요청의 마감에 걸린 것(#334)이다.
func retryable(cause error) bool {
	return database.IsTimeout(cause) || pastDeadline(cause)
}
