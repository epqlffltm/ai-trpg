// billing-server/internal/auth/tokens_test.go

package auth_test

import (
	"context"
	"crypto/rsa"
	"encoding/base64"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/revocations"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// now 는 테스트의 지금 시각이다. 토큰의 만료를 이 시각에 견준다.
var now = time.Date(2026, 10, 11, 9, 0, 0, 0, time.UTC)

// fakeKeys 는 정해 둔 키만 아는 가짜 키 저장소다. 무엇을 찾았는지 적어 둔다.
type fakeKeys struct {
	keys  map[string]*rsa.PublicKey
	err   error
	asked []string
}

func (f *fakeKeys) Key(_ context.Context, kid string) (*rsa.PublicKey, error) {
	f.asked = append(f.asked, kid)
	if f.err != nil {
		return nil, f.err
	}
	key, ok := f.keys[kid]
	if !ok {
		return nil, jwks.ErrUnknownKey
	}
	return key, nil
}

// setup 은 서명용 키 하나와, 그 키를 아는 검증기를 만든다.
func setup(t *testing.T) (testenv.SigningKey, *auth.Verifier, *fakeKeys) {
	t.Helper()
	key := testenv.NewSigningKey(t, 0, "key-1")
	keys := &fakeKeys{keys: map[string]*rsa.PublicKey{key.KeyID: &key.Private.PublicKey}}
	verifier := auth.NewVerifier(keys, revocations.List{}, testenv.Issuer, testenv.Audience, func() time.Time { return now })
	return key, verifier, keys
}

// rejected 는 토큰이 ErrInvalidToken 으로 거부되는지 본다.
func rejected(t *testing.T, verifier *auth.Verifier, token string) {
	t.Helper()
	claims, err := verifier.Verify(context.Background(), token)
	if !errors.Is(err, auth.ErrInvalidToken) {
		t.Errorf("오류 = %v, 기대 = ErrInvalidToken", err)
	}
	if claims != (auth.Claims{}) {
		t.Errorf("거부했는데 값이 돌아왔다: %+v", claims)
	}
}

func TestVerifyAcceptsAnAccessToken(t *testing.T) {
	key, verifier, keys := setup(t)

	claims, err := verifier.Verify(context.Background(), key.Token(t, testenv.AccessClaims(now)))
	if err != nil {
		t.Fatalf("멀쩡한 토큰을 거부했다: %v", err)
	}

	if claims.UserID != uuid.MustParse(testenv.UserID) {
		t.Errorf("사용자 = %v, 기대 = %v", claims.UserID, testenv.UserID)
	}
	if !claims.ExpiresAt.Equal(now.Add(15 * time.Minute)) {
		t.Errorf("만료 = %v, 기대 = %v", claims.ExpiresAt, now.Add(15*time.Minute))
	}
	if len(keys.asked) != 1 || keys.asked[0] != "key-1" {
		t.Errorf("찾은 키 = %v, 기대 = [key-1]", keys.asked)
	}
}

func TestVerifyAcceptsASingleAudience(t *testing.T) {
	key, verifier, _ := setup(t)
	claims := testenv.AccessClaims(now)
	// 대상이 목록이 아니라 글자 하나로 올 수도 있다
	claims["aud"] = testenv.Audience

	if _, err := verifier.Verify(context.Background(), key.Token(t, claims)); err != nil {
		t.Errorf("대상이 하나뿐인 토큰을 거부했다: %v", err)
	}
}

func TestVerifyRejectsWrongClaims(t *testing.T) {
	cases := map[string]func(jwt.MapClaims){
		"만료됐다":           func(c jwt.MapClaims) { c["exp"] = now.Add(-time.Minute).Unix() },
		"만료가 없다":         func(c jwt.MapClaims) { delete(c, "exp") },
		"다른 서버가 발급했다":    func(c jwt.MapClaims) { c["iss"] = "someone-else" },
		"발급자가 없다":        func(c jwt.MapClaims) { delete(c, "iss") },
		"다른 서버용이다":       func(c jwt.MapClaims) { c["aud"] = []string{"ai-trpg-auth", "ai-trpg-game"} },
		"대상이 없다":         func(c jwt.MapClaims) { delete(c, "aud") },
		"대상이 비었다":        func(c jwt.MapClaims) { c["aud"] = []string{} },
		"refresh 토큰이다":   func(c jwt.MapClaims) { c["token_type"] = "refresh" },
		"종류가 없다":         func(c jwt.MapClaims) { delete(c, "token_type") },
		"주인이 없다":         func(c jwt.MapClaims) { delete(c, "sub") },
		"주인이 UUID 가 아니다": func(c jwt.MapClaims) { c["sub"] = "42" },
		"주인이 비었다":        func(c jwt.MapClaims) { c["sub"] = "" },
		"아직 쓸 수 없다":      func(c jwt.MapClaims) { c["nbf"] = now.Add(time.Hour).Unix() },
	}
	for name, breakIt := range cases {
		t.Run(name, func(t *testing.T) {
			key, verifier, _ := setup(t)
			claims := testenv.AccessClaims(now)
			breakIt(claims)

			rejected(t, verifier, key.Token(t, claims))
		})
	}
}

func TestVerifyAllowsASmallClockDifference(t *testing.T) {
	key, verifier, _ := setup(t)

	// 인증 서버의 시계가 조금 느려서, 이 서버가 보기에 방금 만료된 토큰
	justExpired := testenv.AccessClaims(now)
	justExpired["exp"] = now.Add(-auth.ClockSkew + time.Second).Unix()
	if _, err := verifier.Verify(context.Background(), key.Token(t, justExpired)); err != nil {
		t.Errorf("시계 차이 안의 토큰을 거부했다: %v", err)
	}

	// 봐주는 시간을 넘으면 거부한다
	tooOld := testenv.AccessClaims(now)
	tooOld["exp"] = now.Add(-auth.ClockSkew - time.Second).Unix()
	rejected(t, verifier, key.Token(t, tooOld))
}

func TestVerifyRejectsBadSignatures(t *testing.T) {
	key, verifier, _ := setup(t)
	good := key.Token(t, testenv.AccessClaims(now))
	parts := strings.Split(good, ".")

	t.Run("다른 키로 서명했다", func(t *testing.T) {
		// kid 는 아는 것을 적었지만 서명한 키가 다르다
		forger := testenv.NewSigningKey(t, 1, key.KeyID)
		rejected(t, verifier, forger.Token(t, testenv.AccessClaims(now)))
	})
	t.Run("내용을 고쳤다", func(t *testing.T) {
		claims := testenv.AccessClaims(now)
		claims["sub"] = "11111111-1111-1111-1111-111111111111"
		forged := strings.Split(key.Token(t, claims), ".")
		// 고친 내용에 원래 토큰의 서명을 붙인다
		rejected(t, verifier, forged[0]+"."+forged[1]+"."+parts[2])
	})
	t.Run("서명을 뗐다", func(t *testing.T) {
		rejected(t, verifier, parts[0]+"."+parts[1]+".")
	})
	t.Run("토큰의 모양이 아니다", func(t *testing.T) {
		for _, junk := range []string{"", "not-a-token", "a.b", "a.b.c.d", "....", parts[0]} {
			rejected(t, verifier, junk)
		}
	})
}

func TestVerifyTrustsOnlyRS256(t *testing.T) {
	key, verifier, keys := setup(t)

	t.Run("서명이 없는 토큰(none)", func(t *testing.T) {
		token := jwt.NewWithClaims(jwt.SigningMethodNone, testenv.AccessClaims(now))
		token.Header["kid"] = key.KeyID
		unsigned, err := token.SignedString(jwt.UnsafeAllowNoneSignatureType)
		if err != nil {
			t.Fatal(err)
		}
		rejected(t, verifier, unsigned)
	})
	t.Run("공개키를 비밀키처럼 쓴 토큰(HS256)", func(t *testing.T) {
		// 공개키는 누구나 안다. 그것을 대칭키로 써서 서명한 토큰이 통과하면 누구나 토큰을 만든다
		token := jwt.NewWithClaims(jwt.SigningMethodHS256, testenv.AccessClaims(now))
		token.Header["kid"] = key.KeyID
		forged, err := token.SignedString(key.Private.PublicKey.N.Bytes())
		if err != nil {
			t.Fatal(err)
		}
		rejected(t, verifier, forged)
	})
	t.Run("다른 RSA 방식(RS512)", func(t *testing.T) {
		token := jwt.NewWithClaims(jwt.SigningMethodRS512, testenv.AccessClaims(now))
		token.Header["kid"] = key.KeyID
		signed, err := token.SignedString(key.Private)
		if err != nil {
			t.Fatal(err)
		}
		rejected(t, verifier, signed)
	})

	// 서명 방식이 다르면 키를 찾아보지도 않는다. 다른 방식의 토큰으로 인증 서버를 부르게 만들 수 없다
	if len(keys.asked) != 0 {
		t.Errorf("서명 방식이 틀린 토큰으로 키를 찾았다: %v", keys.asked)
	}
}

func TestVerifyNeedsAKeyID(t *testing.T) {
	key, verifier, keys := setup(t)
	parts := strings.Split(key.Token(t, testenv.AccessClaims(now)), ".")

	// 머리말에서 kid 를 빼고 다시 서명한다
	for _, header := range []string{`{"alg":"RS256","typ":"JWT"}`, `{"alg":"RS256","kid":""}`, `{"alg":"RS256","kid":7}`} {
		encoded := base64.RawURLEncoding.EncodeToString([]byte(header))
		signature, err := jwt.SigningMethodRS256.Sign(encoded+"."+parts[1], key.Private)
		if err != nil {
			t.Fatal(err)
		}
		rejected(t, verifier, encoded+"."+parts[1]+"."+base64.RawURLEncoding.EncodeToString(signature))
	}
	if len(keys.asked) != 0 {
		t.Errorf("kid 가 없는데 키를 찾았다: %v", keys.asked)
	}
}

func TestVerifyRejectsAnUnknownKeyID(t *testing.T) {
	_, verifier, keys := setup(t)
	stranger := testenv.NewSigningKey(t, 1, "never-seen")

	// 이 서버가 믿는 키로 서명한 토큰이 아니다. 틀린 토큰이다
	rejected(t, verifier, stranger.Token(t, testenv.AccessClaims(now)))
	if len(keys.asked) != 1 || keys.asked[0] != "never-seen" {
		t.Errorf("찾은 키 = %v, 기대 = [never-seen]", keys.asked)
	}
}

func TestVerifyReportsUnavailableKeysSeparately(t *testing.T) {
	key, verifier, keys := setup(t)
	keys.err = jwks.ErrUnavailable

	claims, err := verifier.Verify(context.Background(), key.Token(t, testenv.AccessClaims(now)))

	// 키를 구할 수 없어서 맞는지 틀린지 모른다. 틀렸다(ErrInvalidToken)고 답하면 멀쩡한 사용자가 로그아웃된다
	if !errors.Is(err, jwks.ErrUnavailable) {
		t.Errorf("오류 = %v, 기대 = ErrUnavailable", err)
	}
	if errors.Is(err, auth.ErrInvalidToken) {
		t.Error("키가 없는 것을 틀린 토큰으로 알렸다")
	}
	if claims != (auth.Claims{}) {
		t.Errorf("실패했는데 값이 돌아왔다: %+v", claims)
	}
}

func TestVerifyWorksWithTheRealCache(t *testing.T) {
	// 가짜 키 저장소가 아니라 진짜 캐시와 맞물려 도는지 본다
	key := testenv.NewSigningKey(t, 0, "key-1")
	parsed, err := jwks.ParseKeySet(testenv.JWKS(t, key))
	if err != nil {
		t.Fatal(err)
	}
	cache := jwks.NewCache(staticFetcher{keys: parsed}, func() time.Time { return now })
	verifier := auth.NewVerifier(cache, revocations.List{}, testenv.Issuer, testenv.Audience, func() time.Time { return now })

	if _, err := verifier.Verify(context.Background(), key.Token(t, testenv.AccessClaims(now))); err != nil {
		t.Errorf("멀쩡한 토큰을 거부했다: %v", err)
	}
}

// staticFetcher 는 늘 같은 키 목록을 돌려주는 가짜 인증 서버다.
type staticFetcher struct {
	keys jwks.KeySet
}

func (f staticFetcher) Fetch(context.Context) (jwks.KeySet, error) {
	return f.keys, nil
}

func TestVerifyRejectsATokenOfARevokedSession(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	keys := &fakeKeys{keys: map[string]*rsa.PublicKey{key.KeyID: &key.Private.PublicKey}}
	// 인증 서버에서 이 사용자의 세션을 끊어 버전이 3 이 되었다(#274)
	sessions := revocations.List{revocations.Digest(testenv.UserID): 3}
	verifier := auth.NewVerifier(keys, sessions, testenv.Issuer, testenv.Audience, func() time.Time { return now })

	for version, accepted := range map[int]bool{2: false, 3: true, 4: true} {
		claims := testenv.AccessClaims(now)
		claims["ver"] = version
		_, err := verifier.Verify(context.Background(), key.Token(t, claims))
		if (err == nil) != accepted {
			t.Errorf("ver %d: 오류 = %v, 받아야 하는가 = %v", version, err, accepted)
		}
		if err != nil && !errors.Is(err, auth.ErrInvalidToken) {
			t.Errorf("ver %d: 오류 = %v. ErrInvalidToken 이어야 한다(401)", version, err)
		}
	}

	// ver 가 없는 토큰은 0 으로 본다
	claims := testenv.AccessClaims(now)
	delete(claims, "ver")
	rejected(t, verifier, key.Token(t, claims))
}

func TestVerifyIgnoresOtherUsersRevocations(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	keys := &fakeKeys{keys: map[string]*rsa.PublicKey{key.KeyID: &key.Private.PublicKey}}
	sessions := revocations.List{revocations.Digest("1b4e28ba-2fa1-11d2-883f-0016d3cca427"): 9}
	verifier := auth.NewVerifier(keys, sessions, testenv.Issuer, testenv.Audience, func() time.Time { return now })

	if _, err := verifier.Verify(context.Background(), key.Token(t, testenv.AccessClaims(now))); err != nil {
		t.Errorf("다른 사용자의 끊긴 세션 때문에 거부했다: %v", err)
	}
}
