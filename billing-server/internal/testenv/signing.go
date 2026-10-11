// billing-server/internal/testenv/signing.go

package testenv

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"sync"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// 테스트가 인증 서버 노릇을 할 때 쓰는 것들. 진짜 인증 서버와 같은 모양의 키 문서와 토큰을 만든다.

const (
	// Issuer 와 Audience 는 테스트 토큰의 발급자와 대상이다. 실제 설정의 기본값과 같다.
	Issuer   = "ai-trpg-auth"
	Audience = "ai-trpg-billing"
	// UserID 는 테스트 토큰의 주인이다.
	UserID = "0d3f7a52-6f0a-4c1e-9d55-2b8a4c1f7e90"
)

// SigningKey 는 토큰에 서명하는 키 하나다. 인증 서버의 개인키 노릇을 한다.
type SigningKey struct {
	Private *rsa.PrivateKey
	KeyID   string
}

var (
	keysOnce sync.Once
	keyPool  []*rsa.PrivateKey
)

// privateKey 는 미리 만들어 둔 RSA 키 중 n 번째를 돌려준다.
// RSA 키를 만드는 일은 느리다. 테스트마다 만들지 않고 한 번 만든 것을 돌려 쓴다.
func privateKey(t *testing.T, n int) *rsa.PrivateKey {
	t.Helper()
	keysOnce.Do(func() {
		for range 3 {
			key, err := rsa.GenerateKey(rand.Reader, 2048)
			if err != nil {
				panic(err)
			}
			keyPool = append(keyPool, key)
		}
	})
	return keyPool[n]
}

// NewSigningKey 는 서명용 키를 돌려준다. n 이 다르면 다른 키다(0, 1, 2).
func NewSigningKey(t *testing.T, n int, keyID string) SigningKey {
	t.Helper()
	return SigningKey{Private: privateKey(t, n), KeyID: keyID}
}

// JWK 는 이 키의 공개키를 JWKS 문서에 들어가는 모양으로 돌려준다.
func (k SigningKey) JWK() map[string]any {
	public := k.Private.PublicKey
	return map[string]any{
		"kty": "RSA",
		"kid": k.KeyID,
		"use": "sig",
		"alg": "RS256",
		"n":   base64.RawURLEncoding.EncodeToString(public.N.Bytes()),
		"e":   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(public.E)).Bytes()),
	}
}

// JWKS 는 주어진 키들의 공개키가 든 JWKS 문서를 만든다.
func JWKS(t *testing.T, keys ...SigningKey) []byte {
	t.Helper()
	entries := make([]map[string]any, 0, len(keys))
	for _, key := range keys {
		entries = append(entries, key.JWK())
	}
	return MustJSON(t, map[string]any{"keys": entries})
}

// MustJSON 은 값을 JSON 으로 바꾼다. 못 바꾸면 테스트를 실패시킨다.
func MustJSON(t *testing.T, value any) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("JSON 으로 바꾸지 못했다: %v", err)
	}
	return data
}

// AccessClaims 는 인증 서버가 발급하는 access 토큰과 같은 값들을 만든다. now 에 발급해 15분 뒤에 만료된다.
// 돌려받은 맵을 고쳐서 틀린 토큰을 만든다.
func AccessClaims(now time.Time) jwt.MapClaims {
	return jwt.MapClaims{
		"token_type": "access",
		"sub":        UserID,
		"iss":        Issuer,
		"aud":        []string{"ai-trpg-auth", "ai-trpg-game", "ai-trpg-board", Audience},
		"iat":        now.Unix(),
		"exp":        now.Add(15 * time.Minute).Unix(),
		"jti":        "test-token",
	}
}

// Token 은 이 키로 서명한 RS256 토큰을 만든다. 머리말에 kid 를 적는다.
func (k SigningKey) Token(t *testing.T, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = k.KeyID
	signed, err := token.SignedString(k.Private)
	if err != nil {
		t.Fatalf("토큰에 서명하지 못했다: %v", err)
	}
	return signed
}
