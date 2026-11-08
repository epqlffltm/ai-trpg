// billing-server/internal/httpapi/autocharge.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 자동 충전의 주소(#980). 모두 로그인이 필요하고, 누구의 것인지는 토큰에서만 정한다.
//
//	GET    /auto-charge             설정과 등록한 카드
//	PUT    /auto-charge             설정을 적는다(켜기, 끄기)
//	POST   /cards/customer-key      카드 등록 창에 넣을 고객 키
//	POST   /cards                   카드 등록 창이 준 인증 키로 카드를 등록한다
//	DELETE /cards                   카드를 지우고 자동 충전을 끈다
//
// 설정은 언제 사는지(mode)를 고른다. 잔액 기준(balance, 골드가 threshold 아래로 떨어지면)이나
// 날짜 기준(date, 매달 charge_day 에, #1167)이다. 결제는 따로 도는 작업(cmd/autocharge)이 한다.

// AutoChargeService 는 자동 충전의 카드와 설정을 다루는 것의 모양이다. *autocharge.Service 가 이 모양이다.
type AutoChargeService interface {
	Get(ctx context.Context, userID uuid.UUID) (autocharge.View, error)
	Update(ctx context.Context, userID uuid.UUID, settings autocharge.Settings, agreedTerms int) (autocharge.View, error)
	CustomerKey(ctx context.Context, userID uuid.UUID) (uuid.UUID, error)
	RegisterCard(ctx context.Context, userID uuid.UUID, authKey string, customerKey uuid.UUID) (autocharge.Card, error)
	RemoveCard(ctx context.Context, userID uuid.UUID) error
}

// autoChargeRequest 는 설정을 적는 요청의 본문이다. 기준 골드는 다른 양처럼 글자다.
// 켤 때는 동의한 자동 결제 동의의 판(terms_version)을 함께 보낸다. 끌 때는 보지 않는다.
// mode 가 없으면 잔액 기준이다(날짜 기준 전의 화면). charge_day 는 날짜 기준의 날이다. 없거나 null 이면 고르지 않은 것이다.
type autoChargeRequest struct {
	Enabled      bool   `json:"enabled"`
	Mode         string `json:"mode"`
	Threshold    string `json:"threshold"`
	ChargeDay    *int   `json:"charge_day"`
	ProductID    string `json:"product_id"`
	MonthlyLimit int64  `json:"monthly_limit"`
	TermsVersion int    `json:"terms_version"`
}

// termsBody 는 자동 결제 동의의 판이다. 지금의 판과 마지막으로 동의한 판(없으면 null)이다.
type termsBody struct {
	Version       int  `json:"version"`
	AgreedVersion *int `json:"agreed_version"`
}

// settingsBody 는 설정의 응답 모양이다. 날을 고른 적이 없으면 charge_day 가 null 이다.
type settingsBody struct {
	Enabled      bool          `json:"enabled"`
	Mode         string        `json:"mode"`
	Threshold    credit.Amount `json:"threshold"`
	ChargeDay    *int          `json:"charge_day"`
	ProductID    string        `json:"product_id"`
	MonthlyLimit int64         `json:"monthly_limit"`
}

// cardBody 는 등록한 카드의 응답 모양이다. 빌링키는 싣지 않는다.
type cardBody struct {
	IssuerCode   string    `json:"issuer_code"`
	Number       string    `json:"number"`
	RegisteredAt time.Time `json:"registered_at"`
}

// autoChargeBody 는 자동 충전의 응답 모양이다. 적은 적이 없으면 settings 가, 카드가 없으면 card 가 null 이다.
type autoChargeBody struct {
	Settings            *settingsBody `json:"settings"`
	ConsecutiveFailures int           `json:"consecutive_failures"`
	Card                *cardBody     `json:"card"`
	Terms               termsBody     `json:"terms"`
}

// customerKeyBody 는 고객 키의 응답 모양이다.
type customerKeyBody struct {
	CustomerKey uuid.UUID `json:"customer_key"`
}

// cardRequest 는 카드를 등록하는 요청의 본문이다. 카드 등록 창이 성공 주소에 붙여 준 두 값이다.
type cardRequest struct {
	AuthKey     string `json:"auth_key"`
	CustomerKey string `json:"customer_key"`
}

// getAutoCharge 는 토큰의 주인의 자동 충전을 돌려주는 핸들러를 만든다.
func getAutoCharge(service AutoChargeService) gin.HandlerFunc {
	return func(c *gin.Context) {
		found, err := service.Get(c.Request.Context(), currentUser(c).UserID)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, toAutoChargeBody(found))
	}
}

// putAutoCharge 는 설정을 적는 핸들러를 만든다.
//   - 적었다 -> 200
//   - 본문이 틀렸거나 값이 틀렸다 -> 400 autocharge.invalid_settings
//   - 켜는데 자동 결제에 동의하지 않았다 -> 400 autocharge.terms_required
//   - 켜는데 옛 판에 동의했다 -> 409 autocharge.terms_outdated
//   - 카드 없이 켜려 했다 -> 409 autocharge.no_card
//   - 지금 결제할 수 없다 -> 403 payment.verification_required, payment.guardian_consent_required
func putAutoCharge(service AutoChargeService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request autoChargeRequest
		if !readJSONWithCode(c, &request, codeAutoChargeInvalidSettings) {
			return
		}
		threshold, err := credit.Parse(request.Threshold)
		if err != nil {
			abort(c, http.StatusBadRequest, codeAutoChargeInvalidSettings, "threshold 는 골드의 양(글자)이어야 합니다.")
			return
		}
		updated, err := service.Update(c.Request.Context(), currentUser(c).UserID, toSettings(request, threshold), request.TermsVersion)
		if err != nil {
			autoChargeError(c, err)
			return
		}
		c.JSON(http.StatusOK, toAutoChargeBody(updated))
	}
}

// createCustomerKey 는 카드 등록 창에 넣을 고객 키를 돌려주는 핸들러를 만든다. 몇 번을 불러도 같은 키다.
func createCustomerKey(service AutoChargeService) gin.HandlerFunc {
	return func(c *gin.Context) {
		key, err := service.CustomerKey(c.Request.Context(), currentUser(c).UserID)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, customerKeyBody{CustomerKey: key})
	}
}

// registerCard 는 카드를 등록하는 핸들러를 만든다.
//   - 등록했다(바꿨다) -> 201
//   - 본문이 틀렸다, 인증 키의 모양이 틀렸다 -> 400 card.invalid_request
//   - 고객 키가 이 사람의 것이 아니다 -> 409 card.customer_key_mismatch. 카드 등록을 처음부터 한다
//   - 결제 대행사가 거절했다 -> 422 card.refused
//   - 결제 대행사의 답을 받지 못했다 -> 503 card.issuer_unavailable
func registerCard(service AutoChargeService) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request cardRequest
		if !readJSONWithCode(c, &request, codeCardInvalidRequest) {
			return
		}
		customerKey, err := uuid.Parse(request.CustomerKey)
		if err != nil {
			abort(c, http.StatusBadRequest, codeCardInvalidRequest, "customer_key 가 틀렸습니다.")
			return
		}
		card, err := service.RegisterCard(c.Request.Context(), currentUser(c).UserID, request.AuthKey, customerKey)
		if err != nil {
			cardError(c, err)
			return
		}
		c.JSON(http.StatusCreated, toCardBody(card))
	}
}

// removeCard 는 카드를 지우고 자동 충전을 끄는 핸들러를 만든다. 카드가 없어도 204 다.
func removeCard(service AutoChargeService) gin.HandlerFunc {
	return func(c *gin.Context) {
		if err := service.RemoveCard(c.Request.Context(), currentUser(c).UserID); err != nil {
			internalError(c, err)
			return
		}
		c.Status(http.StatusNoContent)
	}
}

// autoChargeError 는 설정을 적지 못한 까닭을 응답으로 바꾼다.
func autoChargeError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, autocharge.ErrInvalidSettings):
		abort(c, http.StatusBadRequest, codeAutoChargeInvalidSettings, err.Error()+".")
	case errors.Is(err, autocharge.ErrTermsRequired):
		abort(c, http.StatusBadRequest, codeAutoChargeTermsRequired, err.Error()+".")
	case errors.Is(err, autocharge.ErrTermsOutdated):
		abort(c, http.StatusConflict, codeAutoChargeTermsOutdated, err.Error()+".")
	case errors.Is(err, autocharge.ErrNoCard):
		abort(c, http.StatusConflict, codeAutoChargeNoCard, err.Error()+".")
	case errors.Is(err, eligibility.ErrVerificationRequired):
		abort(c, http.StatusForbidden, codePaymentVerificationRequired, err.Error()+".")
	case errors.Is(err, eligibility.ErrGuardianConsentRequired):
		abort(c, http.StatusForbidden, codePaymentGuardianConsentRequired, err.Error()+".")
	default:
		internalError(c, err)
	}
}

// cardError 는 카드를 등록하지 못한 까닭을 응답으로 바꾼다. 결제 대행사의 이유(코드)는 싣지 않는다. 로그에도 남기지 않는다.
func cardError(c *gin.Context, err error) {
	var refused *payment.RefusedError
	switch {
	case errors.Is(err, autocharge.ErrInvalidAuthKey):
		abort(c, http.StatusBadRequest, codeCardInvalidRequest, err.Error()+".")
	case errors.Is(err, autocharge.ErrCustomerKeyMismatch):
		abort(c, http.StatusConflict, codeCardCustomerKeyMismatch, err.Error()+".")
	case errors.As(err, &refused):
		abort(c, http.StatusUnprocessableEntity, codeCardRefused, "카드를 등록하지 못했습니다. 다른 카드로 해 주세요.")
	case errors.Is(err, autocharge.ErrIssuerUnavailable):
		abort(c, http.StatusServiceUnavailable, codeCardIssuerUnavailable, err.Error()+".")
	default:
		internalError(c, err)
	}
}

// toSettings 는 요청의 본문을 설정으로 바꾼다. 값이 맞는지는 서비스가 본다(autocharge.Settings.Validate).
func toSettings(request autoChargeRequest, threshold credit.Amount) autocharge.Settings {
	settings := autocharge.Settings{
		Enabled: request.Enabled, Mode: autocharge.Mode(request.Mode), Threshold: threshold,
		ProductID: request.ProductID, MonthlyLimit: request.MonthlyLimit,
	}
	if settings.Mode == "" {
		settings.Mode = autocharge.ModeBalance
	}
	if request.ChargeDay != nil {
		settings.ChargeDay = *request.ChargeDay
		if settings.ChargeDay == 0 {
			// 0 은 "고르지 않음" 과 같아지므로 틀린 값으로 보낸다
			settings.ChargeDay = -1
		}
	}
	return settings
}

// toAutoChargeBody 는 자동 충전을 응답의 모양으로 바꾼다.
func toAutoChargeBody(view autocharge.View) autoChargeBody {
	body := autoChargeBody{ConsecutiveFailures: view.ConsecutiveFailures, Terms: termsBody{Version: autocharge.TermsVersion}}
	if view.AgreedTermsVersion > 0 {
		agreed := view.AgreedTermsVersion
		body.Terms.AgreedVersion = &agreed
	}
	if view.Settings != nil {
		body.Settings = &settingsBody{
			Enabled: view.Settings.Enabled, Mode: string(view.Settings.Mode), Threshold: view.Settings.Threshold,
			ProductID: view.Settings.ProductID, MonthlyLimit: view.Settings.MonthlyLimit,
		}
		if view.Settings.ChargeDay > 0 {
			day := view.Settings.ChargeDay
			body.Settings.ChargeDay = &day
		}
	}
	if view.Card != nil {
		card := toCardBody(*view.Card)
		body.Card = &card
	}
	return body
}

// toCardBody 는 카드를 응답의 모양으로 바꾼다.
func toCardBody(card autocharge.Card) cardBody {
	return cardBody{IssuerCode: card.IssuerCode, Number: card.Number, RegisteredAt: card.RegisteredAt}
}
