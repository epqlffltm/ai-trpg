// billing-server/internal/httpapi/withdrawal_test.go

package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/withdrawal"
)

// withdrawalBody 는 인증 서버가 보내는 탈퇴의 알림의 본문이다(auth-server 의 accounts/withdrawal_client.py).
const withdrawalBody = `{"withdrawn_at":"2026-10-28T03:00:00.123456+00:00"}`

// withdrawalURL 은 그 사용자의 탈퇴를 받는 주소다.
func withdrawalURL(userID string) string {
	return httpapi.APIPrefix + "/service/users/" + userID + "/withdrawal"
}

// fakeProcessor 는 정해 둔 대로 답하는 가짜다. 받은 사용자를 적어 둔다.
type fakeProcessor struct {
	err error

	calls int
	user  uuid.UUID
}

func (f *fakeProcessor) Process(_ context.Context, userID uuid.UUID) (withdrawal.Outcome, error) {
	f.calls++
	f.user = userID
	return withdrawal.Outcome{}, f.err
}

func withdrawalDeps(processor httpapi.WithdrawalProcessor) httpapi.Dependencies {
	return httpapi.Dependencies{
		Withdrawals: processor, AuthServerSecret: authSecret, GameServerSecret: gameSecret, WebhookSecret: webhookSecret,
		Now: func() time.Time { return webhookNow },
	}
}

// withdrawAs 는 그 비밀을 가진 서버가 서명해 탈퇴를 알린 것처럼 요청한다.
func withdrawAs(t *testing.T, deps httpapi.Dependencies, secret string, userID string, text string) (int, string) {
	t.Helper()
	path := withdrawalURL(userID)
	response := send(t, deps, request{
		method: http.MethodPost, path: path, body: text, anonymous: true,
		headers: signedBy(secret, path, text),
	})
	return response.Code, body(response)
}

func TestAWithdrawalIsProcessed(t *testing.T) {
	processor := &fakeProcessor{}

	status, got := withdrawAs(t, withdrawalDeps(processor), authSecret, testenv.UserID, withdrawalBody)

	if status != http.StatusOK || got != `{"status":"processed"}` {
		t.Fatalf("상태 코드 = %d, 본문 = %s", status, got)
	}
	if processor.calls != 1 || processor.user.String() != testenv.UserID {
		t.Errorf("반영한 사용자 = %s (%d 번)", processor.user, processor.calls)
	}
}

func TestOnlyTheAuthServerCanReportAWithdrawal(t *testing.T) {
	processor := &fakeProcessor{}

	status, _ := withdrawAs(t, withdrawalDeps(processor), gameSecret, testenv.UserID, withdrawalBody)

	if status != http.StatusUnauthorized || processor.calls != 0 {
		t.Errorf("게임 서버의 비밀 = %d (%d 번 반영). 게임 서버는 탈퇴를 알릴 수 없다", status, processor.calls)
	}
}

func TestAUserCannotReportTheirOwnWithdrawal(t *testing.T) {
	processor := &fakeProcessor{}

	response := send(t, withdrawalDeps(processor), request{
		method: http.MethodPost, path: withdrawalURL(testenv.UserID), body: withdrawalBody,
	})

	if response.Code != http.StatusUnauthorized || processor.calls != 0 {
		t.Errorf("사용자의 토큰 = %d (%d 번 반영). 서명이 있어야 한다", response.Code, processor.calls)
	}
}

func TestAWithdrawalWithoutATimeIsRefused(t *testing.T) {
	for name, text := range map[string]string{
		"빠짐":   `{}`,
		"null": `{"withdrawn_at":null}`,
		"모양":   `{"withdrawn_at":"어제"}`,
	} {
		t.Run(name, func(t *testing.T) {
			processor := &fakeProcessor{}

			status, got := withdrawAs(t, withdrawalDeps(processor), authSecret, testenv.UserID, text)

			if status != http.StatusBadRequest || processor.calls != 0 || !strings.Contains(got, "withdrawal.invalid_request") {
				t.Errorf("상태 코드 = %d, 본문 = %s, %d 번 반영", status, got, processor.calls)
			}
		})
	}
}

func TestAWithdrawalOfAMalformedUserIsRefused(t *testing.T) {
	for _, userID := range []string{"not-a-uuid", uuid.Nil.String()} {
		processor := &fakeProcessor{}

		status, got := withdrawAs(t, withdrawalDeps(processor), authSecret, userID, withdrawalBody)

		// 404 가 아니다. 인증 서버는 404 를 "아직 이 주소가 없다"로 보고 다시 보낸다
		if status != http.StatusBadRequest || processor.calls != 0 || !strings.Contains(got, "withdrawal.invalid_request") {
			t.Errorf("%s: 상태 코드 = %d, 본문 = %s", userID, status, got)
		}
	}
}

func TestAFailedWithdrawalIsAServerError(t *testing.T) {
	processor := &fakeProcessor{err: errors.New("DB 가 답하지 않는다")}

	status, got := withdrawAs(t, withdrawalDeps(processor), authSecret, testenv.UserID, withdrawalBody)

	// 200 이 아니면 인증 서버가 다시 보낸다
	if status != http.StatusInternalServerError || strings.Contains(got, "processed") {
		t.Errorf("상태 코드 = %d, 본문 = %s", status, got)
	}
}
