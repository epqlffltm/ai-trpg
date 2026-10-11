// billing-server/internal/payment/webhook_test.go

package payment_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

const secret = "this-is-a-test-secret-of-32-chars!"

var (
	sentAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	body   = []byte(`{"order_id":"11111111-2222-4333-8444-555555555555","payment_key":"fake_ok_1"}`)
)

func TestASignedBodyVerifies(t *testing.T) {
	header := payment.Sign(secret, sentAt, body)

	if err := payment.VerifySignature(secret, header, body, sentAt); err != nil {
		t.Errorf("방금 서명한 본문을 받지 않았다: %v", err)
	}
	if !strings.HasPrefix(header, "t=1772442000,v1=") {
		t.Errorf("서명의 모양 = %q", header)
	}
}

func TestTheSignatureCoversTheBodyTheTimeAndTheSecret(t *testing.T) {
	header := payment.Sign(secret, sentAt, body)
	later := payment.Sign(secret, sentAt.Add(time.Second), body)
	cases := map[string]struct {
		secret string
		header string
		body   []byte
	}{
		"본문을 한 글자 고쳤다":   {secret, header, []byte(strings.Replace(string(body), "fake_ok_1", "fake_ok_2", 1))},
		"본문이 비었다":        {secret, header, nil},
		"비밀이 다르다":        {"another-secret-that-is-32-chars!!", header, body},
		"시각만 바꿔 붙였다":     {secret, strings.Replace(header, "t=1772442000", "t=1772442001", 1), body},
		"다른 시각의 서명을 붙였다": {secret, "t=1772442000," + later[strings.Index(later, "v1="):], body},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			err := payment.VerifySignature(tc.secret, tc.header, tc.body, sentAt)
			if !errors.Is(err, payment.ErrInvalidSignature) {
				t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
			}
		})
	}
}

func TestAShortSecretVerifiesNothing(t *testing.T) {
	// 설정이 빠져 비밀이 비어 있으면, 같은 빈 비밀로 누구나 서명을 만들 수 있다. 그런 서명도 받지 않는다
	for _, weak := range []string{"", "short", strings.Repeat("s", payment.MinSecretLength-1)} {
		header := payment.Sign(weak, sentAt, body)
		if err := payment.VerifySignature(weak, header, body, sentAt); !errors.Is(err, payment.ErrInvalidSignature) {
			t.Errorf("길이 %d 의 비밀: 오류 = %v. ErrInvalidSignature 이어야 한다", len(weak), err)
		}
	}
}

func TestMalformedSignaturesAreRejected(t *testing.T) {
	good := payment.Sign(secret, sentAt, body)
	signature := good[strings.Index(good, "v1=")+3:]
	headers := map[string]string{
		"비었다":           "",
		"서명만":           "v1=" + signature,
		"시각만":           "t=1772442000",
		"순서가 바뀌었다":      "v1=" + signature + ",t=1772442000",
		"시각이 숫자가 아니다":   "t=yesterday,v1=" + signature,
		"서명이 16진수가 아니다": "t=1772442000,v1=not-hex",
		"서명이 비었다":       "t=1772442000,v1=",
		"서명이 잘렸다":       "t=1772442000,v1=" + signature[:10],
		"다른 판":          "t=1772442000,v0=" + signature,
		"빈칸이 끼었다":       "t=1772442000, v1=" + signature,
	}
	for name, header := range headers {
		t.Run(name, func(t *testing.T) {
			if err := payment.VerifySignature(secret, header, body, sentAt); !errors.Is(err, payment.ErrInvalidSignature) {
				t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
			}
		})
	}
}

func TestOldAndFutureSignaturesAreRejected(t *testing.T) {
	header := payment.Sign(secret, sentAt, body)
	cases := []struct {
		name string
		now  time.Time
		ok   bool
	}{
		{"방금", sentAt, true},
		{"허용 시간의 끝", sentAt.Add(payment.SignatureTolerance), true},
		{"허용 시간을 1초 넘겼다", sentAt.Add(payment.SignatureTolerance + time.Second), false},
		{"하루 뒤에 다시 보냈다", sentAt.Add(24 * time.Hour), false},
		{"시계가 조금 느리다", sentAt.Add(-payment.SignatureTolerance), true},
		{"한참 미래의 시각으로 서명했다", sentAt.Add(-payment.SignatureTolerance - time.Second), false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := payment.VerifySignature(secret, header, body, tc.now)
			if tc.ok && err != nil {
				t.Errorf("받아야 하는데 거절했다: %v", err)
			}
			if !tc.ok && !errors.Is(err, payment.ErrInvalidSignature) {
				t.Errorf("오류 = %v. ErrInvalidSignature 이어야 한다", err)
			}
		})
	}
}
