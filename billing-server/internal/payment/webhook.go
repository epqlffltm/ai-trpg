// billing-server/internal/payment/webhook.go

package payment

import (
	"errors"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/signature"
)

// 결제 대행사가 보내는 알림(웹훅)이 진짜인지 확인하는 서명.
//
// 알림을 받는 주소는 로그인 없이 열려 있다. 결제 대행사는 사용자의 토큰이 없다.
// 그 대신 둘만 아는 비밀로 본문에 서명한다. 서명이 맞지 않는 알림은 읽지도 않는다.
//
// 서명하는 방법은 internal/signature 에 있다. 여기서는 알림의 본문 전체에 서명한다.

const (
	// SignatureHeader 는 서명을 싣는 머리말의 이름이다.
	SignatureHeader = "X-Payment-Signature"
	// SignatureTolerance 는 알림의 시각이 지금과 벌어져도 되는 가장 긴 시간이다. 앞뒤로 같다.
	SignatureTolerance = signature.Tolerance
	// MinSecretLength 는 서명에 쓰는 비밀의 가장 짧은 길이다.
	MinSecretLength = signature.MinSecretLength
)

// ErrInvalidSignature 는 서명이 없거나, 모양이 틀리거나, 맞지 않거나, 너무 오래되었다는 오류다.
// 이유를 나누지 않는다. 무엇이 틀렸는지 알려 주면 서명을 꾸며 내는 쪽에 도움이 된다.
var ErrInvalidSignature = errors.New("알림의 서명이 맞지 않습니다")

// Sign 은 본문에 서명해 머리말에 실을 글자를 만든다. 결제 대행사 쪽이 하는 일이다.
func Sign(secret string, sentAt time.Time, body []byte) string {
	return signature.Sign(secret, sentAt, body)
}

// VerifySignature 는 머리말의 서명이 이 본문의 것이고 방금 보낸 것인지 확인한다.
func VerifySignature(secret string, header string, body []byte, now time.Time) error {
	if err := signature.Verify(secret, header, body, now); err != nil {
		return ErrInvalidSignature
	}
	return nil
}
