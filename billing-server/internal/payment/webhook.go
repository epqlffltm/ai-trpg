// billing-server/internal/payment/webhook.go

package payment

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strconv"
	"strings"
	"time"
)

// 결제 대행사가 보내는 알림(웹훅)이 진짜인지 확인하는 서명.
//
// 알림을 받는 주소는 로그인 없이 열려 있다. 결제 대행사는 사용자의 토큰이 없다.
// 그 대신 둘만 아는 비밀로 본문에 서명한다. 서명이 맞지 않는 알림은 읽지도 않는다.
//
// 서명은 "t=<보낸 시각>,v1=<서명>" 모양이다. 서명하는 글자는 "<보낸 시각>.<본문>" 이다.
// 시각을 함께 서명하므로, 가로챈 알림을 한참 뒤에 다시 보내면 거절된다.

const (
	// SignatureHeader 는 서명을 싣는 머리말의 이름이다.
	SignatureHeader = "X-Payment-Signature"
	// SignatureTolerance 는 알림의 시각이 지금과 벌어져도 되는 가장 긴 시간이다. 앞뒤로 같다.
	SignatureTolerance = 5 * time.Minute
	// MinSecretLength 는 서명에 쓰는 비밀의 가장 짧은 길이다.
	MinSecretLength = 32
)

// ErrInvalidSignature 는 서명이 없거나, 모양이 틀리거나, 맞지 않거나, 너무 오래되었다는 오류다.
// 이유를 나누지 않는다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
var ErrInvalidSignature = errors.New("알림의 서명이 맞지 않습니다")

// Sign 은 본문에 서명해 머리말에 실을 글자를 만든다. 결제 대행사 쪽이 하는 일이다.
func Sign(secret string, sentAt time.Time, body []byte) string {
	timestamp := strconv.FormatInt(sentAt.Unix(), 10)
	return "t=" + timestamp + ",v1=" + hex.EncodeToString(mac(secret, timestamp, body))
}

// VerifySignature 는 머리말의 서명이 이 본문의 것이고 방금 보낸 것인지 확인한다.
func VerifySignature(secret string, header string, body []byte, now time.Time) error {
	// 비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다. 설정이 빠진 서버는 알림을 하나도 받지 않는다
	if len(secret) < MinSecretLength {
		return ErrInvalidSignature
	}
	timestamp, signature, ok := splitSignature(header)
	if !ok {
		return ErrInvalidSignature
	}
	// 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다
	if !hmac.Equal(signature, mac(secret, timestamp, body)) {
		return ErrInvalidSignature
	}
	if !fresh(timestamp, now) {
		return ErrInvalidSignature
	}
	return nil
}

// mac 은 "<보낸 시각>.<본문>" 을 비밀로 서명한 값이다(HMAC-SHA256).
func mac(secret string, timestamp string, body []byte) []byte {
	hash := hmac.New(sha256.New, []byte(secret))
	hash.Write([]byte(timestamp + "."))
	hash.Write(body)
	return hash.Sum(nil)
}

// splitSignature 는 "t=<시각>,v1=<서명>" 을 시각과 서명으로 나눈다. 그 모양이 아니면 false 다.
func splitSignature(header string) (timestamp string, signature []byte, ok bool) {
	timePart, signaturePart, found := strings.Cut(header, ",")
	timestamp, hasTime := strings.CutPrefix(timePart, "t=")
	encoded, hasSignature := strings.CutPrefix(signaturePart, "v1=")
	if !found || !hasTime || !hasSignature {
		return "", nil, false
	}
	signature, err := hex.DecodeString(encoded)
	if err != nil {
		return "", nil, false
	}
	return timestamp, signature, true
}

// fresh 는 알림의 시각이 지금에서 SignatureTolerance 안쪽인지 본다.
func fresh(timestamp string, now time.Time) bool {
	seconds, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	age := now.Sub(time.Unix(seconds, 0))
	return age <= SignatureTolerance && age >= -SignatureTolerance
}
