// billing-server/internal/signature/signature.go

// Package signature 는 둘만 아는 비밀로 글자에 서명하고, 그 서명을 확인한다(HMAC-SHA256).
//
// 서명은 "t=<보낸 시각>,v1=<서명>" 모양이다. 서명하는 글자는 "<보낸 시각>.<내용>" 이다.
// 시각을 함께 서명하므로, 가로챈 것을 한참 뒤에 다시 보내면 거절된다.
//
// 무엇에 서명하는지(본문만인지, 주소까지인지)는 이 패키지가 정하지 않는다. 쓰는 쪽이 내용을 만들어 넘긴다.
//   - 결제 대행사의 알림: internal/payment
//   - 우리 서버끼리의 요청: internal/serviceauth
package signature

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strconv"
	"strings"
	"time"
)

const (
	// Tolerance 는 서명의 시각이 지금과 벌어져도 되는 가장 긴 시간이다. 앞뒤로 같다.
	Tolerance = 5 * time.Minute
	// MinSecretLength 는 서명에 쓰는 비밀의 가장 짧은 길이다.
	MinSecretLength = 32
)

// ErrInvalid 는 서명이 없거나, 모양이 틀리거나, 맞지 않거나, 너무 오래되었다는 오류다.
// 이유를 나누지 않는다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
var ErrInvalid = errors.New("서명이 맞지 않습니다")

// Sign 은 내용에 서명해 머리말에 실을 글자를 만든다.
func Sign(secret string, sentAt time.Time, payload []byte) string {
	timestamp := strconv.FormatInt(sentAt.Unix(), 10)
	return "t=" + timestamp + ",v1=" + hex.EncodeToString(mac(secret, timestamp, payload))
}

// Verify 는 머리말의 서명이 이 내용의 것이고 방금 만든 것인지 확인한다.
func Verify(secret string, header string, payload []byte, now time.Time) error {
	// 비밀이 비었거나 짧으면 누구나 서명을 만들 수 있다. 설정이 빠진 서버는 서명을 하나도 받지 않는다
	if len(secret) < MinSecretLength {
		return ErrInvalid
	}
	timestamp, signature, ok := split(header)
	if !ok {
		return ErrInvalid
	}
	// 두 서명을 견줄 때 걸리는 시간이 어디서 틀렸는지에 따라 달라지지 않게 한다
	if !hmac.Equal(signature, mac(secret, timestamp, payload)) {
		return ErrInvalid
	}
	if !fresh(timestamp, now) {
		return ErrInvalid
	}
	return nil
}

// mac 은 "<보낸 시각>.<내용>" 을 비밀로 서명한 값이다.
func mac(secret string, timestamp string, payload []byte) []byte {
	hash := hmac.New(sha256.New, []byte(secret))
	hash.Write([]byte(timestamp + "."))
	hash.Write(payload)
	return hash.Sum(nil)
}

// split 은 "t=<시각>,v1=<서명>" 을 시각과 서명으로 나눈다. 그 모양이 아니면 false 다.
func split(header string) (timestamp string, signature []byte, ok bool) {
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

// fresh 는 서명의 시각이 지금에서 Tolerance 안쪽인지 본다.
func fresh(timestamp string, now time.Time) bool {
	seconds, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return false
	}
	age := now.Sub(time.Unix(seconds, 0))
	return age <= Tolerance && age >= -Tolerance
}
