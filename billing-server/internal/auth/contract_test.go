// billing-server/internal/auth/contract_test.go

package auth_test

import (
	"context"
	"crypto/rsa"
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/contracts"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
)

// tokenContract 는 shared/contracts/access-tokens.json 의 모양이다.
// 성인용(adult_content)과 운영자(is_operator)는 결제 서버가 읽지 않아 보지 않는다.
type tokenContract struct {
	Issuer   string          `json:"issuer"`
	Audience string          `json:"audience"`
	UserID   string          `json:"user_id"`
	JWKS     json.RawMessage `json:"jwks"`
	Accepted []struct {
		Name  string `json:"name"`
		Token string `json:"token"`
	} `json:"accepted"`
	Rejected []struct {
		Name  string `json:"name"`
		Token string `json:"token"`
	} `json:"rejected"`
}

// contractKeys 는 시험 파일의 키 목록만 아는 키 저장소다.
type contractKeys jwks.KeySet

func (k contractKeys) Key(_ context.Context, kid string) (*rsa.PublicKey, error) {
	key, ok := k[kid]
	if !ok {
		return nil, jwks.ErrUnknownKey
	}
	return key, nil
}

// noRevocations 는 끊긴 세션이 없는 목록이다.
type noRevocations struct{}

func (noRevocations) Revoked(string, int) bool { return false }

// access 토큰의 검증이 공용 코드와 같은 토큰을 받고 같은 토큰을 거부한다(#786).
// 시험 파일의 토큰은 2100 년에 만료되고 2020 년에 발급됐다. 지금 시각으로 본다.
func TestTokensFollowTheSharedContract(t *testing.T) {
	var contract tokenContract
	contracts.Load(t, "access-tokens.json", &contract)
	keys, err := jwks.ParseKeySet(contract.JWKS)
	if err != nil {
		t.Fatalf("시험 파일의 키 목록을 읽지 못했다: %v", err)
	}
	verifier := auth.NewVerifier(contractKeys(keys), noRevocations{}, contract.Issuer, contract.Audience, time.Now)

	for _, c := range contract.Accepted {
		t.Run(c.Name, func(t *testing.T) {
			claims, err := verifier.Verify(context.Background(), c.Token)
			if err != nil {
				t.Fatalf("받아야 할 토큰을 거부했다: %v", err)
			}
			if claims.UserID != uuid.MustParse(contract.UserID) {
				t.Errorf("사용자 = %v, 기대 = %v", claims.UserID, contract.UserID)
			}
		})
	}
	for _, c := range contract.Rejected {
		t.Run(c.Name, func(t *testing.T) {
			if _, err := verifier.Verify(context.Background(), c.Token); err == nil {
				t.Error("거부해야 할 토큰을 받았다")
			}
		})
	}
}
