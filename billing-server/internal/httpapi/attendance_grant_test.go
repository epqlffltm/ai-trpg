// billing-server/internal/httpapi/attendance_grant_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const attendanceGrantURL = httpapi.APIPrefix + "/service/grants/attendance"

// attendanceText 는 2026-11-08 의 출석 실버를 달라는 본문이다.
func attendanceText(silver string, chest string) string {
	return `{"user_id":"` + testenv.UserID + `","day":"2026-11-08","silver":"` + silver + `","chest_silver":"` + chest + `"}`
}

// keyedGranter 는 지급의 이름마다 한 번만 주는 가짜 지급기다. 받은 이름과 양을 차례로 적는다.
// failOn 의 이름이면 실패한다. given 에 미리 넣은 이름은 이미 받은 것이다.
type keyedGranter struct {
	given  map[string]bool
	failOn string
	keys   []string
	totals []credit.Amount
}

func (g *keyedGranter) GrantFreeOnce(_ context.Context, _ uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error) {
	g.keys = append(g.keys, key)
	if key == g.failOn {
		return wallet.Grant{}, errors.New("boom")
	}
	if g.given == nil {
		g.given = map[string]bool{}
	}
	if g.given[key] {
		return wallet.Grant{}, wallet.ErrAlreadyGranted
	}
	g.given[key] = true
	g.totals = append(g.totals, amount)
	return wallet.Grant{Amount: amount, ExpiresAt: time.Date(2026, 12, 8, 0, 0, 0, 0, time.UTC)}, nil
}

// asAuthAttendance 는 인증 서버가 서명해 보낸 것처럼 출석의 실버를 달라고 요청한다.
func asAuthAttendance(t *testing.T, granter httpapi.WelcomeGranter, text string) *httptest.ResponseRecorder {
	t.Helper()
	return send(t, welcomeDeps(granter, 1000), request{
		method: http.MethodPost, path: attendanceGrantURL, body: text, anonymous: true,
		headers: signedBy(authSecret, attendanceGrantURL, text),
	})
}

func TestAttendanceGivesTheDailySilverAndTheChestUnderTheDaysNames(t *testing.T) {
	granter := &keyedGranter{}

	response := asAuthAttendance(t, granter, attendanceText("140", "300"))

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if got, want := body(response), `{"status":"granted","granted":"440","expires_at":"2026-12-08T00:00:00Z"}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
	if strings.Join(granter.keys, ",") != "attendance-20261108,chest-20261108" {
		t.Errorf("지급의 이름 = %v", granter.keys)
	}
	if len(granter.totals) != 2 || granter.totals[0] != 140 || granter.totals[1] != 300 {
		t.Errorf("준 양 = %v", granter.totals)
	}
}

func TestAnEmptyChestGivesOnlyTheDailySilver(t *testing.T) {
	for name, chest := range map[string]string{"꽝": "0", "비움": ""} {
		t.Run(name, func(t *testing.T) {
			granter := &keyedGranter{}
			text := attendanceText("140", chest)
			if chest == "" {
				text = `{"user_id":"` + testenv.UserID + `","day":"2026-11-08","silver":"140"}`
			}

			response := asAuthAttendance(t, granter, text)

			if response.Code != http.StatusCreated || strings.Join(granter.keys, ",") != "attendance-20261108" {
				t.Errorf("상태 코드 = %d, 지급의 이름 = %v", response.Code, granter.keys)
			}
		})
	}
}

func TestSendingTheSameDayAgainGivesNothingMore(t *testing.T) {
	granter := &keyedGranter{}
	asAuthAttendance(t, granter, attendanceText("140", "300"))

	again := asAuthAttendance(t, granter, attendanceText("140", "300"))

	if again.Code != http.StatusOK || body(again) != `{"status":"already_granted","granted":"0","expires_at":null}` {
		t.Errorf("상태 코드 = %d, 본문 = %s", again.Code, body(again))
	}
	if len(granter.totals) != 2 {
		t.Errorf("두 번 줬다: %v", granter.totals)
	}
}

func TestARetryAfterAFailedChestGivesOnlyTheChest(t *testing.T) {
	granter := &keyedGranter{failOn: "chest-20261108"}
	failed := asAuthAttendance(t, granter, attendanceText("140", "300"))
	granter.failOn = ""

	retried := asAuthAttendance(t, granter, attendanceText("140", "300"))

	if failed.Code != http.StatusInternalServerError {
		t.Errorf("상자를 주다 실패한 상태 코드 = %d", failed.Code)
	}
	if retried.Code != http.StatusCreated || !strings.Contains(body(retried), `"granted":"300"`) {
		t.Errorf("다시 보낸 상태 코드 = %d, 본문 = %s", retried.Code, body(retried))
	}
}

func TestSignedButUnusableAttendanceRequestsAreBadRequests(t *testing.T) {
	texts := map[string]string{
		"JSON 이 아니다":  "user_id=1",
		"사용자가 없다":     `{"day":"2026-11-08","silver":"140"}`,
		"날짜가 틀렸다":     `{"user_id":"` + testenv.UserID + `","day":"2026/11/08","silver":"140"}`,
		"하루 양이 없다":    `{"user_id":"` + testenv.UserID + `","day":"2026-11-08"}`,
		"하루 양이 0":     attendanceText("0", "0"),
		"하루 양이 너무 크다": attendanceText("100001", "0"),
		"상자가 음수":      attendanceText("140", "-1"),
		"상자가 너무 크다":   attendanceText("140", "100001"),
		"양이 글자가 아니다":  `{"user_id":"` + testenv.UserID + `","day":"2026-11-08","silver":140}`,
	}
	for name, text := range texts {
		t.Run(name, func(t *testing.T) {
			granter := &keyedGranter{}

			response := asAuthAttendance(t, granter, text)

			if response.Code != http.StatusBadRequest || len(granter.keys) != 0 {
				t.Errorf("상태 코드 = %d, 지급의 이름 = %v", response.Code, granter.keys)
			}
		})
	}
}

func TestAttendanceSilverNeedsTheAuthServersSignature(t *testing.T) {
	text := attendanceText("140", "0")
	cases := map[string]map[string]string{
		"서명이 없다":          {},
		"게임 서버의 비밀로 서명했다": signedBy(gameSecret, attendanceGrantURL, text),
		"초대 보상의 주소에 서명했다": signedBy(authSecret, inviteURL, text),
	}
	for name, headers := range cases {
		t.Run(name, func(t *testing.T) {
			granter := &keyedGranter{}

			response := send(t, welcomeDeps(granter, 1000), request{
				method: http.MethodPost, path: attendanceGrantURL, body: text, headers: headers, anonymous: true,
			})

			if response.Code != http.StatusUnauthorized || len(granter.keys) != 0 {
				t.Errorf("상태 코드 = %d, 지급의 이름 = %v", response.Code, granter.keys)
			}
		})
	}
}

func TestAUserCannotGiveThemselvesAttendanceSilver(t *testing.T) {
	granter := &keyedGranter{}

	response := send(t, welcomeDeps(granter, 1000), request{
		method: http.MethodPost, path: attendanceGrantURL, body: attendanceText("140", "0"),
	})

	if response.Code != http.StatusUnauthorized || len(granter.keys) != 0 {
		t.Errorf("상태 코드 = %d, 지급의 이름 = %v", response.Code, granter.keys)
	}
}
