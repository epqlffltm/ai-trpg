// billing-server/internal/jwks/keys_test.go

package jwks_test

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"errors"
	"math/big"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// encode 는 큰 수를 JWKS 가 쓰는 모양(base64url, 채움 문자 없음)으로 적는다.
func encode(number *big.Int) string {
	return base64.RawURLEncoding.EncodeToString(number.Bytes())
}

func TestParseKeySetReadsRSAKeys(t *testing.T) {
	first := testenv.NewSigningKey(t, 0, "key-1")
	second := testenv.NewSigningKey(t, 1, "key-2")

	keys, err := jwks.ParseKeySet(testenv.JWKS(t, first, second))
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}

	if len(keys) != 2 {
		t.Fatalf("키의 수 = %d, 기대 = 2", len(keys))
	}
	if !keys["key-1"].Equal(&first.Private.PublicKey) || !keys["key-2"].Equal(&second.Private.PublicKey) {
		t.Error("읽은 키가 문서의 키와 다르다")
	}
}

func TestParseKeySetSkipsKeysItCannotUse(t *testing.T) {
	good := testenv.NewSigningKey(t, 0, "good")
	weak, err := rsa.GenerateKey(rand.Reader, 1024)
	if err != nil {
		t.Fatal(err)
	}
	modulus := encode(good.Private.N)

	cases := map[string]map[string]any{
		"RSA 가 아니다":     {"kty": "EC", "kid": "ec", "crv": "P-256", "x": "AA", "y": "AA"},
		"RSA 라고 적지 않았다": {"kty": "oct", "kid": "mislabeled", "n": modulus, "e": "AQAB"},
		"kid 가 없다":      {"kty": "RSA", "n": modulus, "e": "AQAB"},
		"kid 가 비었다":     {"kty": "RSA", "kid": "", "n": modulus, "e": "AQAB"},
		"n 이 없다":        {"kty": "RSA", "kid": "no-n", "e": "AQAB"},
		"n 이 깨졌다":       {"kty": "RSA", "kid": "bad-n", "n": "!!!", "e": "AQAB"},
		"e 가 없다":        {"kty": "RSA", "kid": "no-e", "n": modulus},
		"e 가 1 이다":      {"kty": "RSA", "kid": "e-one", "n": modulus, "e": encode(big.NewInt(1))},
		"e 가 짝수다":       {"kty": "RSA", "kid": "e-even", "n": modulus, "e": encode(big.NewInt(65536))},
		"e 가 너무 크다":     {"kty": "RSA", "kid": "e-huge", "n": modulus, "e": encode(new(big.Int).Lsh(big.NewInt(1), 40))},
		"키가 너무 짧다":      {"kty": "RSA", "kid": "weak", "n": encode(weak.N), "e": "AQAB"},
		"키가 null 이다":    nil,
		"칸의 형식이 다르다":    {"kty": "RSA", "kid": "typed", "n": 12345, "e": "AQAB"},
		"글자가 아닌 kid":    {"kty": "RSA", "kid": 7, "n": modulus, "e": "AQAB"},
	}
	for name, bad := range cases {
		t.Run(name, func(t *testing.T) {
			// 하나가 이상해도 나머지는 쓴다. 인증 서버가 새 종류의 키를 더했다고 검증이 통째로 멈추면 안 된다
			document := testenv.MustJSON(t, map[string]any{"keys": []any{bad, good.JWK()}})

			keys, err := jwks.ParseKeySet(document)
			if err != nil {
				t.Fatalf("이상한 키 하나 때문에 문서 전체를 버렸다: %v", err)
			}
			if len(keys) != 1 || keys["good"] == nil {
				t.Errorf("쓸 수 없는 키가 들어왔다: %d개", len(keys))
			}
		})
	}
}

func TestParseKeySetFailsWithoutUsableKeys(t *testing.T) {
	cases := map[string]string{
		"JSON 이 아니다":     `<html>502 Bad Gateway</html>`,
		"빈 문서":           ``,
		"keys 가 없다":      `{}`,
		"keys 가 비었다":     `{"keys": []}`,
		"keys 가 목록이 아니다": `{"keys": "nope"}`,
		"쓸 수 있는 키가 없다":   `{"keys": [{"kty": "EC", "kid": "ec"}]}`,
		"문서가 목록이다":       `[]`,
	}
	for name, document := range cases {
		t.Run(name, func(t *testing.T) {
			keys, err := jwks.ParseKeySet([]byte(document))

			if !errors.Is(err, jwks.ErrFetch) {
				t.Errorf("오류 = %v, 기대 = ErrFetch", err)
			}
			if keys != nil {
				t.Errorf("키가 돌아왔다: %d개", len(keys))
			}
		})
	}
}
