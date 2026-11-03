// billing-server/internal/httpapi/invite_test.go

package httpapi_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	inviteURL = httpapi.APIPrefix + "/service/grants/invite"
	rewardID  = "4f1c2a3b-5d6e-4f70-8a9b-0c1d2e3f4a5b"
)

// inviteText 는 그 사람에게 초대 보상을 달라는 본문이다.
func inviteText(role string) string {
	return `{"user_id":"` + testenv.UserID + `","reward_id":"` + rewardID + `","role":"` + role + `"}`
}

// inviteDeps 는 가짜 지급기를 끼운 서버의 부품이다. amount 는 서버의 설정에 적힌 초대 보상의 양이다.
func inviteDeps(granter httpapi.WelcomeGranter, amount credit.Amount) httpapi.Dependencies {
	deps := welcomeDeps(granter, 1000)
	deps.InviteCredits = amount
	return deps
}

// asAuthInvite 는 인증 서버가 서명해 보낸 것처럼 초대 보상을 달라고 요청한다.
func asAuthInvite(t *testing.T, deps httpapi.Dependencies, text string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, deps, request{
		method: http.MethodPost, path: inviteURL, body: text, anonymous: true,
		headers: signedBy(authSecret, inviteURL, text),
	})
}

func TestInviteGivesTheConfiguredCreditsUnderAKeyPerRole(t *testing.T) {
	cases := map[string]string{
		"inviter": "invite-" + rewardID,
		"invitee": "invited",
	}
	for role, key := range cases {
		t.Run(role, func(t *testing.T) {
			granter := &fakeGranter{}

			response := asAuthInvite(t, inviteDeps(granter, 500), inviteText(role))

			if response.Code != http.StatusCreated {
				t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
			}
			if got, want := body(response), `{"status":"granted","granted":"500","expires_at":"2026-03-09T09:00:00Z"}`; got != want {
				t.Errorf("본문 = %s, 기대 = %s", got, want)
			}
			if granter.user.String() != testenv.UserID || granter.amount != 500 || granter.key != key {
				t.Errorf("지급기가 받은 것 = %v, %d, %q", granter.user, granter.amount, granter.key)
			}
		})
	}
}

func TestInviteKeysFitTheGrantKeyRule(t *testing.T) {
	// 지급의 이름은 소문자, 숫자, _, - 로 된 64자 이하다(wallet 의 grantKeyPattern)
	key, ok := httpapi.InviteGrantKey("inviter", uuid.MustParse(rewardID))
	if !ok || len(key) > 64 || strings.ToLower(key) != key {
		t.Errorf("지급의 이름 = %q, %v", key, ok)
	}
}

func TestInviteIgnoresAmountsFromTheRequest(t *testing.T) {
	granter := &fakeGranter{}
	text := `{"user_id":"` + testenv.UserID + `","reward_id":"` + rewardID + `","role":"invitee","amount":"999999"}`

	response := asAuthInvite(t, inviteDeps(granter, 500), text)

	if response.Code != http.StatusCreated || granter.amount != 500 {
		t.Errorf("상태 코드 = %d, 지급기가 받은 양 = %d", response.Code, granter.amount)
	}
}

func TestInviteForAUserWhoAlreadyHasItIsNotAnError(t *testing.T) {
	granter := &fakeGranter{err: wallet.ErrAlreadyGranted}

	response := asAuthInvite(t, inviteDeps(granter, 500), inviteText("invitee"))

	if got, want := body(response), `{"status":"already_granted","granted":"0","expires_at":null}`; response.Code != http.StatusOK || got != want {
		t.Errorf("응답 = %d %s, 기대 = 200 %s", response.Code, got, want)
	}
}

func TestInviteTurnedOffGivesNothing(t *testing.T) {
	granter := &fakeGranter{}

	response := asAuthInvite(t, inviteDeps(granter, 0), inviteText("inviter"))

	if got, want := body(response), `{"status":"disabled","granted":"0","expires_at":null}`; response.Code != http.StatusOK || got != want {
		t.Errorf("응답 = %d %s, 기대 = 200 %s", response.Code, got, want)
	}
	if granter.calls != 0 {
		t.Errorf("꺼 두었는데 지급기를 %d 번 불렀다", granter.calls)
	}
}

func TestInviteFailureIsAnInternalError(t *testing.T) {
	granter := &fakeGranter{err: errors.New(`relation "free_grants" does not exist`)}

	response := asAuthInvite(t, inviteDeps(granter, 500), inviteText("invitee"))

	// 2xx 가 아니어야 인증 서버가 나중에 다시 부른다
	if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "free_grants") {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestSignedButUnusableInviteRequestsAreBadRequests(t *testing.T) {
	texts := map[string]string{
		"JSON 이 아니다":   "user_id=1",
		"사용자가 없다":      `{"reward_id":"` + rewardID + `","role":"invitee"}`,
		"보상이 없다":       `{"user_id":"` + testenv.UserID + `","role":"invitee"}`,
		"받는 사람이 없다":    `{"user_id":"` + testenv.UserID + `","reward_id":"` + rewardID + `"}`,
		"받는 사람이 모르는 값": inviteText("friend"),
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			granter := &fakeGranter{}

			response := asAuthInvite(t, inviteDeps(granter, 500), text)

			if response.Code != http.StatusBadRequest || granter.calls != 0 {
				t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
			}
		})
	}
}

func TestInviteNeedsTheAuthServersSignature(t *testing.T) {
	cases := map[string]map[string]string{
		"서명이 없다":           {},
		"게임 서버의 비밀로 서명했다":  signedBy(gameSecret, inviteURL, inviteText("invitee")),
		"환영 크레딧의 주소에 서명했다": signedBy(authSecret, welcomeURL, inviteText("invitee")),
	}
	for name, headers := range cases {
		t.Run(name, func(t *testing.T) {
			granter := &fakeGranter{}

			response := send(t, inviteDeps(granter, 500), request{
				method: http.MethodPost, path: inviteURL, body: inviteText("invitee"), headers: headers, anonymous: true,
			})

			if response.Code != http.StatusUnauthorized || granter.calls != 0 {
				t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
			}
		})
	}
}

func TestAUserCannotClaimAnInviteRewardDirectly(t *testing.T) {
	granter := &fakeGranter{}

	response := send(t, inviteDeps(granter, 500), request{method: http.MethodPost, path: inviteURL, body: inviteText("invitee")})

	if response.Code != http.StatusUnauthorized || granter.calls != 0 {
		t.Errorf("상태 코드 = %d, 지급기를 부른 횟수 = %d", response.Code, granter.calls)
	}
}
