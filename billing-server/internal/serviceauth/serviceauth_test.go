// billing-server/internal/serviceauth/serviceauth_test.go

package serviceauth_test

import (
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/signature"
)

const (
	secret = "this-is-a-test-secret-of-32-chars!"
	path   = "/api/v1/billing/service/holds"
)

var (
	sentAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	body   = []byte(`{"user_id":"11111111-2222-4333-8444-555555555555","reference":"table:1:round:3","price_code":"narration.standard"}`)
)

func TestASignedRequestVerifies(t *testing.T) {
	header := serviceauth.Sign(secret, sentAt, http.MethodPost, path, body)

	if err := serviceauth.Verify(secret, header, http.MethodPost, path, body, sentAt); err != nil {
		t.Errorf("방금 서명한 요청을 받지 않았다: %v", err)
	}
}

func TestTheSignedTextIsMethodPathAndBodyOnSeparateLines(t *testing.T) {
	// 게임 서버가 같은 글자에 서명해야 한다. 이 모양이 두 서버 사이의 약속이다
	want := signature.Sign(secret, sentAt, []byte("POST\n/api/v1/billing/service/holds\n{}"))

	if got := serviceauth.Sign(secret, sentAt, http.MethodPost, path, []byte("{}")); got != want {
		t.Errorf("서명 = %q, 기대 = %q", got, want)
	}
}

func TestTheSignatureIsTheValueOtherServersCompute(t *testing.T) {
	// 인증 서버(파이썬)의 테스트에 같은 값이 적혀 있다(auth-server/accounts/tests/test_service_signature.py).
	// 한쪽의 계산이 바뀌면 그쪽의 테스트가 깨진다. 두 서버가 서로를 띄우지 않고도 약속을 지키는지 본다
	const want = "t=1772442000,v1=9270f18fd4635b8f4489bf06d6c6f42275f2b08ea19876090cb7c2ea02a62aec"
	welcome := []byte(`{"user_id":"11111111-2222-4333-8444-555555555555"}`)

	got := serviceauth.Sign(secret, sentAt, http.MethodPost, "/api/v1/billing/service/grants/welcome", welcome)

	if got != want {
		t.Errorf("서명 = %q, 기대 = %q", got, want)
	}
}

func TestTheSignatureCoversTheMethodThePathAndTheBody(t *testing.T) {
	header := serviceauth.Sign(secret, sentAt, http.MethodPost, path, body)
	cases := map[string]struct {
		secret string
		method string
		path   string
		body   []byte
	}{
		// 홀드를 거는 요청의 서명을 가로채 반환하는 주소에 붙인다
		"다른 주소":        {secret, http.MethodPost, path + "/release", body},
		"주소 뒤에 값을 붙였다": {secret, http.MethodPost, path + "?user_id=another", body},
		"다른 메서드":       {secret, http.MethodDelete, path, body},
		"본문을 고쳤다":      {secret, http.MethodPost, path, []byte(strings.Replace(string(body), "round:3", "round:4", 1))},
		"본문이 비었다":      {secret, http.MethodPost, path, nil},
		"다른 비밀":        {"another-secret-that-is-32-chars!!", http.MethodPost, path, body},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			err := serviceauth.Verify(tc.secret, header, tc.method, tc.path, tc.body, sentAt)
			if !errors.Is(err, serviceauth.ErrInvalidSignature) {
				t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
			}
		})
	}
}

func TestTheThreePartsCannotTradeCharacters(t *testing.T) {
	// 세 부분 사이의 줄바꿈이 없으면 주소의 끝을 본문의 앞으로 옮겨도 같은 글자가 된다. 주소에는 줄바꿈이 들어갈 수 없다
	header := serviceauth.Sign(secret, sentAt, http.MethodPost, path+"/capture", []byte("{}"))

	err := serviceauth.Verify(secret, header, http.MethodPost, path, []byte("/capture{}"), sentAt)

	if !errors.Is(err, serviceauth.ErrInvalidSignature) {
		t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
	}
}

func TestAPaymentNotificationSignatureIsNotAServiceSignature(t *testing.T) {
	// 같은 비밀을 두 자리에 쓴 서버라도(쓰면 안 되지만) 본문만 서명한 것은 요청의 서명이 되지 못한다
	header := signature.Sign(secret, sentAt, body)

	if err := serviceauth.Verify(secret, header, http.MethodPost, path, body, sentAt); !errors.Is(err, serviceauth.ErrInvalidSignature) {
		t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
	}
}

func TestOldAndMissingSignaturesAreRejected(t *testing.T) {
	header := serviceauth.Sign(secret, sentAt, http.MethodPost, path, body)
	if err := serviceauth.Verify(secret, header, http.MethodPost, path, body, sentAt.Add(serviceauth.Tolerance)); err != nil {
		t.Errorf("5분 된 서명을 받지 않았다: %v", err)
	}
	cases := map[string]struct {
		header string
		now    time.Time
	}{
		"5분 1초 된 서명": {header, sentAt.Add(serviceauth.Tolerance + time.Second)},
		"서명이 없다":     {"", sentAt},
		"토큰을 실었다":    {"Bearer the-token", sentAt},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			err := serviceauth.Verify(secret, tc.header, http.MethodPost, path, body, tc.now)
			if !errors.Is(err, serviceauth.ErrInvalidSignature) {
				t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
			}
		})
	}
}

func TestAShortSecretVerifiesNothing(t *testing.T) {
	weak := strings.Repeat("s", serviceauth.MinSecretLength-1)
	header := serviceauth.Sign(weak, sentAt, http.MethodPost, path, body)

	if err := serviceauth.Verify(weak, header, http.MethodPost, path, body, sentAt); !errors.Is(err, serviceauth.ErrInvalidSignature) {
		t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
	}
}
