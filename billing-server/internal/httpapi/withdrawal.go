// billing-server/internal/httpapi/withdrawal.go

package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/withdrawal"
)

// 탈퇴를 받는 주소. 인증 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/users/{id}/withdrawal
//
// 인증 서버는 유예(7일)가 지난 계정을 비운 뒤 서버마다 알린다(#603, docs/architecture/withdrawal.md 의 "알리는 길").
// 200 과 {"status": "processed"} 를 받을 때까지 다시 보낸다. 그래서 이 주소는 몇 번을 받아도 결과가 같고,
// 이미 반영한 사용자나 이 서버가 모르는 사용자도 200 이다. 할 일은 internal/withdrawal 이 한다.

// withdrawalProcessed 는 반영을 마쳤다는 답이다. 인증 서버는 이 글자를 받아야 보내기를 멈춘다.
const withdrawalProcessed = "processed"

// WithdrawalProcessor 는 탈퇴를 반영하는 것의 모양이다. *withdrawal.Service 가 이 모양이다.
type WithdrawalProcessor interface {
	Process(ctx context.Context, userID uuid.UUID) (withdrawal.Outcome, error)
}

// withdrawalRequest 는 탈퇴의 알림의 본문이다. 빠뜨린 칸을 알아보려고 포인터로 받는다.
type withdrawalRequest struct {
	// WithdrawnAt 은 인증 서버가 계정을 비운 시각이다(RFC 3339). 반영하는 일은 이 값을 쓰지 않는다. 빠지면 틀린 알림이다.
	WithdrawnAt *time.Time `json:"withdrawn_at"`
}

// withdrawalBody 는 응답의 모양이다.
type withdrawalBody struct {
	// Status 는 늘 processed 다.
	Status string `json:"status"`
}

// processWithdrawal 은 탈퇴를 반영하는 핸들러를 만든다. 반영했든, 이미 했든, 할 것이 없었든 200 이다.
func processWithdrawal(processor WithdrawalProcessor) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID, ok := withdrawalUser(c)
		if !ok {
			return
		}
		var request withdrawalRequest
		if !readJSONWithCode(c, &request, codeWithdrawalInvalidRequest) {
			return
		}
		if request.WithdrawnAt == nil {
			abort(c, http.StatusBadRequest, codeWithdrawalInvalidRequest, "withdrawn_at 이 있어야 합니다.")
			return
		}
		if _, err := processor.Process(c.Request.Context(), userID); err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, withdrawalBody{Status: withdrawalProcessed})
	}
}

// withdrawalUser 는 주소의 사용자 번호를 읽는다. 틀렸으면 400 으로 답하고 false 다.
// 서버끼리의 주소라서 404 가 아니다. 인증 서버는 404 를 "아직 이 주소가 없는 옛 판"으로 보고 다시 보낸다.
func withdrawalUser(c *gin.Context) (uuid.UUID, bool) {
	userID, err := uuid.Parse(c.Param("id"))
	if err != nil || userID == uuid.Nil {
		abort(c, http.StatusBadRequest, codeWithdrawalInvalidRequest, "주소의 사용자 번호가 틀렸습니다.")
		return uuid.Nil, false
	}
	return userID, true
}
