// billing-server/internal/obs/contract_test.go

package obs_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/contracts"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// redactionContract 는 shared/contracts/redaction.json 의 모양이다.
type redactionContract struct {
	Names []struct {
		Name      string `json:"name"`
		Sensitive bool   `json:"sensitive"`
	} `json:"names"`
	Texts []struct {
		Text     string `json:"text"`
		Limit    int    `json:"limit"`
		Scrubbed string `json:"scrubbed"`
	} `json:"texts"`
}

// 로그 가리기가 공용 코드, 인증 서버와 같은 칸을 가리고 같은 글로 바꾼다(#786).
func TestRedactionFollowsTheSharedContract(t *testing.T) {
	var contract redactionContract
	contracts.Load(t, "redaction.json", &contract)

	for _, c := range contract.Names {
		t.Run("이름 "+c.Name, func(t *testing.T) {
			if got := obs.IsSensitiveName(c.Name); got != c.Sensitive {
				t.Errorf("가림 = %v, 기대 = %v", got, c.Sensitive)
			}
		})
	}
	for _, c := range contract.Texts {
		t.Run("글 "+c.Text, func(t *testing.T) {
			if got := obs.ScrubText(c.Text, c.Limit); got != c.Scrubbed {
				t.Errorf("가린 글 = %q, 기대 = %q", got, c.Scrubbed)
			}
		})
	}
}
