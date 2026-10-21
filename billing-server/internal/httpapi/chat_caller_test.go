// billing-server/internal/httpapi/chat_caller_test.go

// chat 서버가 홀드와 가격 목록을 부르는 것과, 서버마다 쓸 수 있는 가격표의 머리(price_scope.go)를 시험한다.
package httpapi_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// chatSecret 은 테스트의 chat 서버와 결제 서버가 함께 아는 비밀이다.
const chatSecret = "chat-server-test-secret-of-32-chars"

// chatHoldText 는 chat 서버가 말 한 번에 거는 홀드다.
const chatHoldText = `{"user_id":"` + testenv.UserID + `","reference":"conversation:9a1b:turn:4","price_code":"chat.model-a.i0.o0"}`

// chatDeps 는 게임 서버와 chat 서버의 비밀을 둘 다 넣은 서버의 부품이다.
func chatDeps(holds httpapi.HoldService, prices httpapi.PriceLister) httpapi.Dependencies {
	return httpapi.Dependencies{
		Holds: holds, Prices: prices, GameServerSecret: gameSecret, ChatServerSecret: chatSecret,
		Now: func() time.Time { return webhookNow },
	}
}

// signedAs 는 그 비밀을 가진 서버가 서명해 보낸 것처럼 요청을 보낸다.
func signedAs(t *testing.T, deps httpapi.Dependencies, secret string, method string, path string, text string) *httptest.ResponseRecorder {
	t.Helper()
	signature := serviceauth.Sign(secret, webhookNow, method, path, []byte(text))
	return send(t, deps, request{
		method: method, path: path, body: text, anonymous: true,
		headers: map[string]string{serviceauth.SignatureHeader: signature},
	})
}

// mixedListing 은 게임 서버와 chat 서버의 가격표가 섞인 목록이다.
func mixedListing() []pricing.Listing {
	listing := func(code string) pricing.Listing {
		return pricing.Listing{Code: code, Current: &pricing.Price{Code: code, Credits: 10, Tier: pricing.TierStandard, Since: webhookNow}}
	}
	return []pricing.Listing{
		listing("narration.a.i0.o0"), listing("chat.a.i0.o0"), listing("story.a.i0.o0"), listing("chatter.a.i0.o0"),
	}
}

func TestTheChatServerPlacesItsOwnHold(t *testing.T) {
	holds := &fakeHolds{hold: aHold(t), isNew: true}

	response := signedAs(t, chatDeps(holds, nil), chatSecret, http.MethodPost, holdsURL, chatHoldText)

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	// 누가 걸었는지는 서명에서 온다. chat 서버의 홀드는 chat 서버의 것이라 게임 서버가 확정하거나 돌려주지 못한다
	if holds.source != httpapi.ChatServer || holds.priceCode != "chat.model-a.i0.o0" {
		t.Errorf("서비스에 넘긴 값 = %+v", holds)
	}
}

func TestTheChatServerSettlesUnderItsOwnName(t *testing.T) {
	for _, path := range []string{holdsURL + "/capture", holdsURL + "/release", holdsURL + "/extend"} {
		t.Run(path, func(t *testing.T) {
			holds := &fakeHolds{hold: aHold(t)}

			response := signedAs(t, chatDeps(holds, nil), chatSecret, http.MethodPost, path, settleText)

			if response.Code != http.StatusOK || holds.source != httpapi.ChatServer {
				t.Errorf("상태 코드 = %d, 넘긴 서버 = %q", response.Code, holds.source)
			}
		})
	}
}

func TestAServerCannotUseAnotherServersPrice(t *testing.T) {
	gameUsesChat := strings.Replace(holdText, "narration.standard", "chat.model-a.i0.o0", 1)
	chatUsesGame := strings.Replace(chatHoldText, "chat.model-a.i0.o0", "narration.standard", 1)
	cases := []struct {
		name   string
		secret string
		text   string
	}{
		{"게임 서버가 chat 의 가격표로", gameSecret, gameUsesChat},
		{"chat 서버가 서술의 가격표로", chatSecret, chatUsesGame},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			holds := &fakeHolds{hold: aHold(t), isNew: true}

			response := signedAs(t, chatDeps(holds, nil), tc.secret, http.MethodPost, holdsURL, tc.text)

			// 없는 가격표와 같은 답이다. 그런 가격표가 있다는 것도 알리지 않는다. 홀드를 걸어 보지도 않는다
			if response.Code != http.StatusBadRequest || !strings.Contains(body(response), `"code":"price.unknown"`) || holds.calls != 0 {
				t.Errorf("상태 코드 = %d, 본문 = %s, 부른 수 = %d", response.Code, body(response), holds.calls)
			}
		})
	}
}

func TestEachServerListsOnlyItsOwnPrices(t *testing.T) {
	deps := chatDeps(nil, &fakeLister{listings: mixedListing()})
	cases := []struct {
		name   string
		secret string
		want   []string
		absent []string
	}{
		{"게임 서버", gameSecret, []string{"narration.a.i0.o0"}, []string{"chat.a", "story.a", "chatter.a"}},
		// 머리는 첫 점까지 견준다. chatter 는 chat 이 아니다
		{"chat 서버", chatSecret, []string{"chat.a.i0.o0", "story.a.i0.o0"}, []string{"narration.a", "chatter.a"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			response := signedAs(t, deps, tc.secret, http.MethodGet, pricesURL, "")

			if response.Code != http.StatusOK {
				t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
			}
			for _, code := range tc.want {
				if !strings.Contains(body(response), `"code":"`+code+`"`) {
					t.Errorf("%s 가 없다: %s", code, body(response))
				}
			}
			for _, code := range tc.absent {
				if strings.Contains(body(response), `"code":"`+code) {
					t.Errorf("%s 가 실렸다: %s", code, body(response))
				}
			}
		})
	}
}

func TestTheTwoServersGetDifferentPriceTags(t *testing.T) {
	// ETag 는 그 서버가 받는 목록의 것이다. 한 서버의 태그로 다른 서버의 목록을 304 로 받지 않는다
	deps := chatDeps(nil, &fakeLister{listings: mixedListing()})

	game := signedAs(t, deps, gameSecret, http.MethodGet, pricesURL, "")
	chat := signedAs(t, deps, chatSecret, http.MethodGet, pricesURL, "")

	if game.Header().Get("ETag") == "" || game.Header().Get("ETag") == chat.Header().Get("ETag") {
		t.Errorf("게임 = %q, chat = %q", game.Header().Get("ETag"), chat.Header().Get("ETag"))
	}
}

func TestWithoutAChatSecretNothingPassesAsTheChatServer(t *testing.T) {
	// chat 서버를 띄우지 않는 동안은 비밀이 비어 있다. 빈 비밀로 서명한 요청이 통과하면 누구나 chat 서버인 척할 수 있다
	holds := &fakeHolds{hold: aHold(t), isNew: true}
	deps := chatDeps(holds, nil)
	deps.ChatServerSecret = ""

	for _, secret := range []string{"", chatSecret} {
		response := signedAs(t, deps, secret, http.MethodPost, holdsURL, chatHoldText)

		if response.Code != http.StatusUnauthorized || holds.calls != 0 {
			t.Errorf("비밀 %q: 상태 코드 = %d, 부른 수 = %d", secret, response.Code, holds.calls)
		}
	}
}

func TestTheChatSecretOpensOnlyTheSpendingAddresses(t *testing.T) {
	// 환영 크레딧과 결제 자격은 인증 서버의 것이다. chat 서버의 비밀로 열리지 않는다
	deps := chatDeps(&fakeHolds{}, nil)
	deps.AuthServerSecret = "auth-server-test-secret-of-32-chars"

	for _, path := range []string{httpapi.APIPrefix + "/service/grants/welcome", httpapi.APIPrefix + "/service/eligibility"} {
		response := signedAs(t, deps, chatSecret, http.MethodPost, path, `{}`)

		if response.Code != http.StatusUnauthorized {
			t.Errorf("%s: 상태 코드 = %d", path, response.Code)
		}
	}
}
