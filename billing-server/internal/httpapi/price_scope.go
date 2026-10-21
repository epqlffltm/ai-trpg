// billing-server/internal/httpapi/price_scope.go

package httpapi

import (
	"strings"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// 부르는 서버마다 쓸 수 있는 가격표 이름의 머리. 서버는 자기 머리의 가격표로만 홀드를 걸고, 가격 목록도 그것만 받는다.
//
//   - 게임 서버: narration(서술 한 번)
//   - chat 서버: chat, story(말 한 번. 두 모드가 한 서버다. docs/architecture/chat-server.md 의 "가격 이름")
//
// 한 서버의 비밀이 새도 다른 서버의 값으로 크레딧을 빼지 못하게 하려는 것이다. 다른 머리의 이름은 없는 가격표와 같은 답이다
// (400 price.unknown). 그런 가격표가 있다는 것도 알리지 않는다.
// 머리를 더하거나 서버를 더하면 이 표를 고친다.
var pricePrefixes = map[string][]string{
	GameServer: {"narration"},
	ChatServer: {"chat", "story"},
}

// mayUsePrice 는 그 서버가 그 이름의 가격표를 쓸 수 있는지 본다. 이름의 첫 칸(첫 점의 앞)이 그 서버의 머리여야 한다.
func mayUsePrice(caller string, code string) bool {
	head, _, found := strings.Cut(code, ".")
	if !found {
		return false
	}
	for _, prefix := range pricePrefixes[caller] {
		if head == prefix {
			return true
		}
	}
	return false
}

// pricesFor 는 가격 목록에서 그 서버가 쓸 수 있는 줄만 고른다. 차례는 그대로다.
func pricesFor(caller string, listings []pricing.Listing) []pricing.Listing {
	kept := make([]pricing.Listing, 0, len(listings))
	for _, listing := range listings {
		if mayUsePrice(caller, listing.Code) {
			kept = append(kept, listing)
		}
	}
	return kept
}
