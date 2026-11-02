// billing-server/internal/serviceauth/contract_test.go

package serviceauth_test

import (
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/contracts"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

// signatureContract 는 shared/contracts/service-signature.json 의 모양이다.
type signatureContract struct {
	Secret string `json:"secret"`
	Now    int64  `json:"now"`
	Sign   []struct {
		Name   string `json:"name"`
		Method string `json:"method"`
		Path   string `json:"path"`
		Body   string `json:"body"`
		SentAt int64  `json:"sent_at"`
		Header string `json:"header"`
	} `json:"sign"`
	Verify []struct {
		Name   string  `json:"name"`
		Method string  `json:"method"`
		Path   string  `json:"path"`
		Body   string  `json:"body"`
		Secret *string `json:"secret"`
		Header *string `json:"header"`
		Valid  bool    `json:"valid"`
	} `json:"verify"`
}

// 서버끼리의 서명이 공용 코드, 인증 서버와 같은 값을 만들고 같은 것만 받는다(#786).
func TestTheSignatureFollowsTheSharedContract(t *testing.T) {
	var contract signatureContract
	contracts.Load(t, "service-signature.json", &contract)

	for _, c := range contract.Sign {
		t.Run(c.Name, func(t *testing.T) {
			header := serviceauth.Sign(contract.Secret, time.Unix(c.SentAt, 0), c.Method, c.Path, []byte(c.Body))
			if header != c.Header {
				t.Errorf("서명 = %q, 기대 = %q", header, c.Header)
			}
		})
	}
	for _, c := range contract.Verify {
		t.Run(c.Name, func(t *testing.T) {
			secret := contract.Secret
			if c.Secret != nil {
				secret = *c.Secret
			}
			header := ""
			if c.Header != nil {
				header = *c.Header
			}
			err := serviceauth.Verify(secret, header, c.Method, c.Path, []byte(c.Body), time.Unix(contract.Now, 0))
			if (err == nil) != c.Valid {
				t.Errorf("받음 = %v, 기대 = %v", err == nil, c.Valid)
			}
		})
	}
}
