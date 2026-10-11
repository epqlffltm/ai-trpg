// billing-server/internal/jwks/keys.go

// Package jwks 는 인증 서버의 공개키(JWKS)를 가져오고 기억한다.
//
// 이 파일은 받은 문서를 읽어 키로 바꾸는 일만 한다. 가져오는 일은 fetch.go, 기억하는 일은 cache.go 에 있다.
package jwks

import (
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"errors"
	"math/big"
)

const (
	// keyType 은 이 서버가 받는 키의 종류다. 서명 방식(RS256)에 맞는 것만 기억한다.
	keyType = "RSA"
	// MinKeyBits 는 받아들이는 키의 가장 짧은 길이다. 이보다 짧은 RSA 키는 깨질 수 있다.
	// 인증 서버가 실수로 짧은 키를 내놓아도 그 키로 서명한 토큰을 믿지 않는다.
	MinKeyBits = 2048
	// maxExponent 는 받아들이는 지수의 가장 큰 값이다. Go 의 rsa.PublicKey 가 지수를 int 로 든다.
	maxExponent = 1<<31 - 1
)

// ErrFetch 는 인증 서버에서 쓸 수 있는 키 목록을 받지 못했다는 오류다.
// 이유(연결 실패, 상태 코드, 형식)는 로그에만 남기고 밖으로는 이것 하나로 알린다.
var ErrFetch = errors.New("JWKS 를 가져오지 못했다")

// KeySet 은 키 ID(kid)로 찾는 공개키들이다.
type KeySet map[string]*rsa.PublicKey

// document 는 JWKS 문서의 모양이다. 키 하나하나는 아직 읽지 않고 그대로 둔다.
// 한꺼번에 읽으면 키 하나의 칸이 이상할 때 문서 전체를 읽지 못한다.
type document struct {
	Keys []json.RawMessage `json:"keys"`
}

// entry 는 JWKS 문서 안의 키 하나다. n 과 e 는 큰 수를 base64url 로 적은 것이다.
type entry struct {
	KeyType  string `json:"kty"`
	KeyID    string `json:"kid"`
	Modulus  string `json:"n"`
	Exponent string `json:"e"`
}

// ParseKeySet 은 JWKS 문서에서 서명 검증에 쓸 키를 골라 kid 로 찾을 수 있게 담는다.
//
// kid 가 없는 키, RSA 가 아닌 키, 읽을 수 없는 키, 너무 짧은 키는 건너뛴다.
// 하나가 이상하다고 전부를 버리면, 인증 서버가 새 종류의 키를 더했을 때 검증이 통째로 멈춘다.
// 쓸 수 있는 키가 하나도 없으면 ErrFetch 다.
func ParseKeySet(data []byte) (KeySet, error) {
	var doc document
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, ErrFetch
	}

	keys := KeySet{}
	for _, raw := range doc.Keys {
		var one entry
		if err := json.Unmarshal(raw, &one); err != nil {
			continue
		}
		if one.KeyType != keyType || one.KeyID == "" {
			continue
		}
		key, ok := toPublicKey(one)
		if !ok {
			continue
		}
		keys[one.KeyID] = key
	}

	if len(keys) == 0 {
		return nil, ErrFetch
	}
	return keys, nil
}

// toPublicKey 는 문서의 키 하나를 RSA 공개키로 바꾼다. 읽을 수 없거나 받아들일 수 없는 키면 false 다.
func toPublicKey(one entry) (*rsa.PublicKey, bool) {
	modulus, ok := decodeNumber(one.Modulus)
	if !ok || modulus.BitLen() < MinKeyBits {
		return nil, false
	}
	exponent, ok := decodeNumber(one.Exponent)
	// 지수는 1 보다 큰 홀수여야 한다. 1 이면 서명이 곧 원문이라 누구나 서명을 만들 수 있다
	if !ok || !exponent.IsInt64() || exponent.Int64() <= 1 || exponent.Int64() > maxExponent || exponent.Bit(0) == 0 {
		return nil, false
	}
	return &rsa.PublicKey{N: modulus, E: int(exponent.Int64())}, true
}

// decodeNumber 는 base64url(채움 문자 없음)로 적힌 큰 수를 읽는다.
func decodeNumber(text string) (*big.Int, bool) {
	raw, err := base64.RawURLEncoding.DecodeString(text)
	if err != nil || len(raw) == 0 {
		return nil, false
	}
	return new(big.Int).SetBytes(raw), true
}
