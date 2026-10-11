// billing-server/internal/pricing/pricing.go

// Package pricing 은 크레딧을 받는 일의 가격표다. 무엇에 몇 크레딧을 받는지를 이 파일 하나가 정한다.
//
// 부르는 서버(게임 서버)는 금액을 보내지 않는다. "무엇을"(Code)만 말하고 값은 여기서 찾는다.
// 값이 한 곳에 있고, 부르는 서버의 버그가 틀린 금액이 되지 않는다. 상품 목록(internal/catalog)과 같은 생각이다.
//
// 홀드는 걸 때의 값을 스스로 적어 둔다. 여기를 고쳐도 이미 건 홀드는 바뀌지 않는다.
package pricing

import "github.com/epqlffltm/ai-trpg/billing-server/internal/credit"

// Price 는 가격표의 한 줄이다.
type Price struct {
	// Code 는 무엇의 값인지다. "<무엇>.<등급>" 모양이다. 한 번 쓴 이름을 다른 뜻으로 다시 쓰지 않는다.
	Code string
	// Credits 는 한 번에 받는 크레딧이다.
	Credits credit.Amount
}

// NarrationStandard 는 라운드의 AI 서술 한 번이다.
const NarrationStandard = "narration.standard"

// prices 는 가격표 전부다.
// 지금은 모델과 상관없이 서술 한 번의 값이 하나다. 모델마다 값을 다르게 할 때는 줄을 더한다(narration.premium 처럼).
var prices = []Price{
	{Code: NarrationStandard, Credits: 50},
}

// All 은 가격표를 돌려준다. 돌려받은 목록을 고쳐도 원래 가격표는 바뀌지 않는다.
func All() []Price {
	return append([]Price(nil), prices...)
}

// Find 는 이름으로 값을 찾는다. 없으면 두 번째 값이 false 다.
func Find(code string) (Price, bool) {
	for _, price := range prices {
		if price.Code == code {
			return price, true
		}
	}
	return Price{}, false
}
