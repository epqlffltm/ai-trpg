// billing-server/internal/httpapi/eligibility.go

package httpapi

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
)

// 결제 자격을 받는 주소. 인증 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/eligibility
//
// 인증 서버는 본인인증, 보호자 동의, 철회 때마다 그 사용자의 지금 상태를 버전과 함께 보낸다(#336).
// 이 서버는 가진 것보다 높은 버전만 받는다. 결제할 때는 받아 둔 것만 본다(eligibility.Guarded).

// EligibilityRecorder 는 결제 자격을 받아 적는 것의 모양이다. *eligibility.Service 가 이 모양이다.
type EligibilityRecorder interface {
	Apply(ctx context.Context, update eligibility.Update) (eligibility.Outcome, error)
}

// eligibilityRequest 는 결제 자격의 본문이다. 빠뜨린 칸을 알아보려고 포인터로 받는다.
type eligibilityRequest struct {
	UserID uuid.UUID `json:"user_id"`
	// Version 은 인증 서버가 붙인 버전이다. 1 이상이다.
	Version *int64 `json:"version"`
	// LegalAdultFrom 은 성년이 되는 날(YYYY-MM-DD, 한국 날짜)이다. null 이면 이미 성년이다.
	LegalAdultFrom *string `json:"legal_adult_from"`
	// GuardianConsent 는 보호자가 동의했는지다. 빠뜨릴 수 없다.
	GuardianConsent *bool `json:"guardian_consent"`
}

// eligibilityBody 는 응답의 모양이다.
type eligibilityBody struct {
	// Status 는 applied(받아 적었다)나 stale(이미 같거나 높은 버전이 있다)다. 둘 다 인증 서버에는 끝난 일이다.
	Status eligibility.Outcome `json:"status"`
}

// recordEligibility 는 결제 자격을 받아 적는 핸들러를 만든다. 적었든 이미 있었든 200 이다.
func recordEligibility(recorder EligibilityRecorder) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request eligibilityRequest
		if !readJSONWithCode(c, &request, codeEligibilityInvalidRequest) {
			return
		}
		update, err := toEligibilityUpdate(request)
		if err != nil {
			abort(c, http.StatusBadRequest, codeEligibilityInvalidRequest, err.Error()+".")
			return
		}
		outcome, err := recorder.Apply(c.Request.Context(), update)
		if errors.Is(err, eligibility.ErrInvalidUpdate) {
			abort(c, http.StatusBadRequest, codeEligibilityInvalidRequest, err.Error()+".")
			return
		}
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, eligibilityBody{Status: outcome})
	}
}

// errEligibilityShape 는 본문의 칸이 빠졌거나 날짜의 모양이 틀렸다는 오류다.
var errEligibilityShape = errors.New("version, guardian_consent 가 있어야 하고 legal_adult_from 은 YYYY-MM-DD 이거나 null 이어야 합니다")

// toEligibilityUpdate 는 본문을 받은 상태로 바꾼다. 빠진 칸이나 틀린 날짜는 errEligibilityShape 다.
func toEligibilityUpdate(request eligibilityRequest) (eligibility.Update, error) {
	if request.Version == nil || request.GuardianConsent == nil {
		return eligibility.Update{}, errEligibilityShape
	}
	update := eligibility.Update{UserID: request.UserID, Version: *request.Version, GuardianConsent: *request.GuardianConsent}
	if request.LegalAdultFrom != nil {
		day, err := time.Parse(time.DateOnly, *request.LegalAdultFrom)
		if err != nil {
			return eligibility.Update{}, errEligibilityShape
		}
		update.LegalAdultFrom = &day
	}
	return update, nil
}
