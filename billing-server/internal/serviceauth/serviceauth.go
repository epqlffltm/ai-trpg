// billing-server/internal/serviceauth/serviceauth.go

// Package serviceauth 는 우리 서버끼리 부르는 요청이 정말 그 서버가 보낸 것인지 확인한다.
//
// 게임 서버가 결제 서버를 부를 때는 사용자의 토큰을 쓰지 않는다. 사용자가 없는 자리에서도(라운드를 닫는 작업)
// 불러야 하고, 사용자의 토큰으로 "이 사용자의 크레딧을 빼라"를 할 수 있으면 사용자가 직접 그 주소를 부를 수 있다.
// 그 대신 두 서버만 아는 비밀로 요청에 서명한다.
//
// 서명하는 내용은 "<메서드>\n<주소>\n<본문>" 이다. 주소까지 서명하므로, 홀드를 거는 요청의 서명을 가로채
// 다른 주소에 붙여 쓸 수 없다. 서명하는 방법(HMAC, 시각 포함)은 internal/signature 에 있다.
//
// 비밀을 머리말에 그대로 싣지 않는다(API 키 방식). 그러면 비밀이 요청마다 오가고, 로그나 프록시에 한 번 찍히면 끝이다.
// 서명은 그 요청에만 쓸 수 있고 5분이 지나면 못 쓴다.
package serviceauth

import (
	"errors"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/signature"
)

const (
	// SignatureHeader 는 서명을 싣는 머리말의 이름이다.
	SignatureHeader = "X-Service-Signature"
	// MinSecretLength 는 서명에 쓰는 비밀의 가장 짧은 길이다.
	MinSecretLength = signature.MinSecretLength
	// Tolerance 는 요청의 시각이 지금과 벌어져도 되는 가장 긴 시간이다. 서버끼리의 시계 차이를 봐준다.
	Tolerance = signature.Tolerance
)

// ErrInvalidSignature 는 서명이 없거나, 모양이 틀리거나, 맞지 않거나, 너무 오래되었다는 오류다. 이유를 나누지 않는다.
var ErrInvalidSignature = errors.New("요청의 서명이 맞지 않습니다")

// Sign 은 요청에 서명해 머리말에 실을 글자를 만든다. 부르는 서버가 하는 일이다.
// requestURI 는 주소의 경로와 그 뒤에 붙은 값이다(/api/v1/billing/service/holds?x=1). 호스트는 넣지 않는다.
func Sign(secret string, sentAt time.Time, method string, requestURI string, body []byte) string {
	return signature.Sign(secret, sentAt, payload(method, requestURI, body))
}

// Verify 는 머리말의 서명이 이 요청(메서드, 주소, 본문)의 것이고 방금 보낸 것인지 확인한다.
func Verify(secret string, header string, method string, requestURI string, body []byte, now time.Time) error {
	if err := signature.Verify(secret, header, payload(method, requestURI, body), now); err != nil {
		return ErrInvalidSignature
	}
	return nil
}

// payload 는 서명하는 내용을 만든다. 메서드와 주소에는 줄바꿈이 들어갈 수 없어서 세 부분이 섞이지 않는다.
func payload(method string, requestURI string, body []byte) []byte {
	head := method + "\n" + requestURI + "\n"
	return append([]byte(head), body...)
}
