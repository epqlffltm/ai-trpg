// billing-server/internal/auth/tokens.go

// Package auth 는 인증 서버가 발급한 access 토큰을 검증한다.
//
// 인증 서버의 DB 를 보지 않는다. 공개키로 서명을 확인하고, 토큰 안에 적힌 값만 본다.
// 인증 서버에서 세션을 끊은 것(비밀번호 변경, 계정 정지 등)은 인증 서버가 내주는 끊긴 세션의 목록으로 안다(#274).
// 목록은 30초마다 받으므로, 끊은 뒤 30초쯤은 옛 토큰이 통한다. 게임 서버(game-server/app/auth/tokens.py)와 같은 규칙이다.
//
// 확인하는 것:
//   - 서명 방식이 RS256 인가. 토큰이 스스로 적어 온 방식을 믿지 않는다.
//   - 인증 서버의 키로 서명됐는가.
//   - 만료되지 않았는가(exp).
//   - 인증 서버가 발급했는가(iss).
//   - 이 서버에 쓰라고 발급됐는가(aud).
//   - access 토큰인가. refresh 토큰도 같은 키로 서명되므로 종류를 따로 본다.
//   - 끊긴 세션의 것이 아닌가. 토큰의 세션 버전(ver)이 목록의 것보다 낮으면 끊기기 전에 발급된 토큰이다.
//
// 서명을 확인하는 일은 직접 쓰지 않고 라이브러리(golang-jwt)에 맡긴다. 여기서 정하는 것은 무엇을 받아들일지다.
package auth

import (
	"context"
	"crypto/rsa"
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
)

const (
	// algorithm 은 이 서버가 받는 서명 방식이다. 하나만 적는다.
	// 토큰 머리말의 alg 를 그대로 믿으면, 서명이 없는 토큰(none)이나
	// 공개키를 비밀키처럼 써서 만든 토큰(HS256)이 통과한다.
	algorithm = "RS256"
	// accessTokenType 은 access 토큰의 token_type 값이다. 인증 서버(simplejwt)가 넣는다.
	accessTokenType = "access"
	// ClockSkew 는 서버끼리 시계가 조금 어긋나는 것을 봐주는 시간이다.
	// 0 이면 인증 서버의 시계가 1초만 빨라도 방금 발급한 토큰이 "아직 유효하지 않다"로 거부된다.
	ClockSkew = 10 * time.Second
)

// ErrInvalidToken 은 토큰을 받아들일 수 없다는 오류다.
// 이유를 나누지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
var ErrInvalidToken = errors.New("토큰을 받아들일 수 없다")

// Claims 는 검증을 마친 토큰에서 꺼낸 값이다. 이 값이 있다는 것이 검증을 통과했다는 뜻이다.
type Claims struct {
	// UserID 는 인증 서버의 public_id 다. 결제 서버는 사용자를 이 값으로만 가리킨다.
	UserID uuid.UUID
	// ExpiresAt 은 토큰이 만료되는 시각(exp)이다.
	ExpiresAt time.Time
}

// KeySource 는 키 ID 로 공개키를 찾아 주는 것의 모양이다. *jwks.Cache 가 이 모양이다.
type KeySource interface {
	Key(ctx context.Context, kid string) (*rsa.PublicKey, error)
}

// SessionChecker 는 그 사용자(sub)의 그 세션 버전의 토큰이 끊긴 세션의 것인지 알려 주는 것의 모양이다.
// *revocations.Cache 가 이 모양이다. 테스트는 revocations.List 를 넣는다.
type SessionChecker interface {
	Revoked(sub string, version int) bool
}

// tokenClaims 는 토큰 안의 값 중에서 이 서버가 읽는 것이다.
// iss, aud, exp, sub 같은 표준 값은 RegisteredClaims 에 들어 있다.
type tokenClaims struct {
	TokenType string `json:"token_type"`
	// Version 은 세션 버전(ver)이다. 없으면 0 으로 본다(인증 서버 README 의 약속)
	Version int `json:"ver"`
	jwt.RegisteredClaims
}

// Verifier 는 access 토큰을 검증한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.
type Verifier struct {
	keys     KeySource
	sessions SessionChecker
	parser   *jwt.Parser
}

// NewVerifier 는 검증기를 만든다.
// sessions 는 끊긴 세션을 알려 준다. issuer 는 토큰을 발급한 서버의 이름(iss), audience 는 이 서버의 이름(aud)이다.
// now 는 지금 시각을 알려 준다. 테스트가 만료를 기다리지 않고 시간을 돌릴 수 있게 밖에서 받는다.
func NewVerifier(keys KeySource, sessions SessionChecker, issuer string, audience string, now func() time.Time) *Verifier {
	parser := jwt.NewParser(
		jwt.WithValidMethods([]string{algorithm}),
		jwt.WithIssuer(issuer),
		jwt.WithAudience(audience),
		// exp 가 없는 토큰을 "만료가 없다"로 받지 않는다
		jwt.WithExpirationRequired(),
		jwt.WithLeeway(ClockSkew),
		jwt.WithTimeFunc(now),
	)
	return &Verifier{keys: keys, sessions: sessions, parser: parser}
}

// Verify 는 access 토큰을 검증하고 그 안의 값을 돌려준다.
//
// 토큰이 틀렸으면 ErrInvalidToken 이다.
// 키를 구할 수 없어 맞는지 틀린지 알 수 없으면 jwks.ErrUnavailable 이다. 둘은 다른 응답이 된다.
func (v *Verifier) Verify(ctx context.Context, token string) (Claims, error) {
	var claims tokenClaims
	_, err := v.parser.ParseWithClaims(token, &claims, v.findKey(ctx))
	if errors.Is(err, jwks.ErrUnavailable) {
		return Claims{}, jwks.ErrUnavailable
	}
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	verified, err := toClaims(claims)
	if err != nil {
		return Claims{}, err
	}
	// 끊긴 세션의 토큰도 이유를 나누지 않고 받을 수 없는 토큰이다. 사용자는 다시 로그인한다
	if v.sessions.Revoked(claims.Subject, claims.Version) {
		return Claims{}, ErrInvalidToken
	}
	return verified, nil
}

// findKey 는 라이브러리가 서명을 확인하기 전에 부르는 함수를 만든다. 토큰의 머리말에서 kid 를 읽어 키를 찾는다.
// 이 시점의 머리말은 아직 믿을 수 없다. 키를 고르는 데만 쓴다.
// 라이브러리는 이 함수를 부르기 전에 서명 방식이 RS256 인지 먼저 본다. 다른 방식의 토큰으로는 키를 찾게 만들 수 없다.
func (v *Verifier) findKey(ctx context.Context) jwt.Keyfunc {
	return func(token *jwt.Token) (any, error) {
		kid, ok := token.Header["kid"].(string)
		if !ok || kid == "" {
			return nil, ErrInvalidToken
		}
		return v.keys.Key(ctx, kid)
	}
}

// toClaims 는 서명과 표준 값의 확인을 마친 토큰에서 이 서버가 쓰는 것만 꺼낸다.
// access 토큰이 아니거나 사용자 ID 를 읽을 수 없으면 거부한다.
func toClaims(claims tokenClaims) (Claims, error) {
	if claims.TokenType != accessTokenType {
		return Claims{}, ErrInvalidToken
	}
	userID, err := uuid.Parse(claims.Subject)
	if err != nil {
		return Claims{}, ErrInvalidToken
	}
	// exp 가 있다는 것은 라이브러리가 이미 확인했다(WithExpirationRequired)
	return Claims{UserID: userID, ExpiresAt: claims.ExpiresAt.Time}, nil
}
