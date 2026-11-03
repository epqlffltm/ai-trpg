// billing-server/internal/httpapi/invite.go

package httpapi

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 초대 보상을 주는 주소(#990). 인증 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	POST /service/grants/invite
//
// 초대받은 사람이 휴대폰 본인인증을 마치면 인증 서버가 보상 하나에 두 번 부른다. 초대한 사람에게 한 번, 초대받은 사람에게 한 번이다.
// 누구에게 줄지, 한 사람이 몇 번 받을지(초대한 사람의 상한, 초대받은 사람은 사람마다 한 번)는 인증 서버가 정한다. 그쪽이 사람을 안다.
// 이 서버가 지키는 것은 "같은 보상, 같은 사용자에게 한 번"이다. 지급의 이름(InviteGrantKey)으로 지킨다.
// 응답은 환영 크레딧과 같은 모양이다(welcomeBody).

// 초대 보상을 받는 사람.
const (
	// inviteRoleInviter 는 초대한 사람이다. 상한까지 여러 번 받는다. 보상마다 지급의 이름이 다르다.
	inviteRoleInviter = "inviter"
	// inviteRoleInvitee 는 초대받은 사람이다. 한 사용자 번호가 한 번만 받는다.
	inviteRoleInvitee = "invitee"
)

// grantInviteRequest 는 초대 보상을 달라는 요청의 본문이다. 양은 받지 않는다. 서버의 설정이 정한다.
type grantInviteRequest struct {
	// UserID 는 받을 사용자다. 인증 서버의 public_id 다.
	UserID uuid.UUID `json:"user_id"`
	// RewardID 는 인증 서버의 보상 하나의 번호다. 초대한 사람이 받는 지급의 이름에 들어간다.
	RewardID uuid.UUID `json:"reward_id"`
	// Role 은 inviter 나 invitee 다.
	Role string `json:"role"`
}

// InviteGrantKey 는 초대 보상이라는 지급의 이름이다. 한 사용자는 같은 이름의 지급을 한 번만 받는다.
// 초대받은 사람은 보상과 상관없이 "invited" 하나다. 초대한 사람은 보상마다 "invite-<보상 번호>" 다.
// 둘 다 지급의 이름 규칙(소문자, 숫자, _, -, 64자 이하)에 맞는다. 보상 번호는 하이픈이 있는 소문자 UUID(36자)다.
func InviteGrantKey(role string, rewardID uuid.UUID) (string, bool) {
	switch role {
	case inviteRoleInvitee:
		return "invited", true
	case inviteRoleInviter:
		return "invite-" + rewardID.String(), true
	default:
		return "", false
	}
}

// grantInvite 는 초대 보상을 주는 핸들러를 만든다. amount 는 한 사람에게 줄 양이다.
//   - 줬다 -> 201
//   - 이미 받았다 -> 200(already_granted). 인증 서버가 응답을 못 받아 다시 보낸 요청일 수 있다
//   - amount 가 0 이다 -> 200(disabled). 설정으로 꺼 둔 것이다
func grantInvite(granter WelcomeGranter, amount credit.Amount) gin.HandlerFunc {
	return func(c *gin.Context) {
		var request grantInviteRequest
		if !readJSON(c, &request) {
			return
		}
		if request.UserID == uuid.Nil || request.RewardID == uuid.Nil {
			badRequest(c, "user_id 와 reward_id 가 있어야 합니다.")
			return
		}
		key, ok := InviteGrantKey(request.Role, request.RewardID)
		if !ok {
			badRequest(c, "role 은 inviter 나 invitee 여야 합니다.")
			return
		}
		if amount == 0 {
			c.JSON(http.StatusOK, welcomeBody{Status: welcomeDisabled})
			return
		}
		grant, err := granter.GrantFreeOnce(c.Request.Context(), request.UserID, amount, key)
		if errors.Is(err, wallet.ErrAlreadyGranted) {
			c.JSON(http.StatusOK, welcomeBody{Status: welcomeAlreadyGranted})
			return
		}
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusCreated, welcomeBody{Status: welcomeGranted, Granted: grant.Amount, ExpiresAt: &grant.ExpiresAt})
	}
}
