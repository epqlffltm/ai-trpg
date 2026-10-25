// billing-server/internal/httpapi/story_caller_test.go

// story 서버가 홀드와 가격 목록을 부르는 것과, story 서버가 쓸 수 있는 가격표의 머리(price_scope.go)를 시험한다.
// 쓰는 도구(signedAs, mixedListing)는 chat_caller_test.go 에 있다.
package httpapi_test

import (
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// storySecret 은 테스트의 story 서버와 결제 서버가 함께 아는 비밀이다.
const storySecret = "story-server-test-secret-of-32-chars"

// storyHoldText 는 story 서버가 세션의 말 한 번에 거는 홀드다.
const storyHoldText = `{"user_id":"` + testenv.UserID + `","reference":"session:5c2e:turn:7","price_code":"story.model-a.i0.o0"}`

// storyDeps 는 게임 서버, chat 서버, story 서버의 비밀을 모두 넣은 서버의 부품이다.
func storyDeps(holds httpapi.HoldService, prices httpapi.PriceLister) httpapi.Dependencies {
	return httpapi.Dependencies{
		Holds: holds, Prices: prices, GameServerSecret: gameSecret, ChatServerSecret: chatSecret, StoryServerSecret: storySecret,
		Now: func() time.Time { return webhookNow },
	}
}

func TestTheStoryServerPlacesItsOwnHold(t *testing.T) {
	holds := &fakeHolds{hold: aHold(t), isNew: true}

	response := signedAs(t, storyDeps(holds, nil), storySecret, http.MethodPost, holdsURL, storyHoldText)

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	// 누가 걸었는지는 서명에서 온다. story 서버의 홀드는 story 서버의 것이라 chat 서버가 확정하거나 돌려주지 못한다
	if holds.source != httpapi.StoryServer || holds.priceCode != "story.model-a.i0.o0" {
		t.Errorf("서비스에 넘긴 값 = %+v", holds)
	}
}

func TestTheStoryServerSettlesUnderItsOwnName(t *testing.T) {
	for _, path := range []string{holdsURL + "/capture", holdsURL + "/release", holdsURL + "/extend"} {
		t.Run(path, func(t *testing.T) {
			holds := &fakeHolds{hold: aHold(t)}

			response := signedAs(t, storyDeps(holds, nil), storySecret, http.MethodPost, path, settleText)

			if response.Code != http.StatusOK || holds.source != httpapi.StoryServer {
				t.Errorf("상태 코드 = %d, 넘긴 서버 = %q", response.Code, holds.source)
			}
		})
	}
}

func TestChatAndStoryCannotUseEachOthersPrice(t *testing.T) {
	storyUsesChat := strings.Replace(storyHoldText, "story.model-a.i0.o0", "chat.model-a.i0.o0", 1)
	chatUsesStory := strings.Replace(chatHoldText, "chat.model-a.i0.o0", "story.model-a.i0.o0", 1)
	storyUsesGame := strings.Replace(storyHoldText, "story.model-a.i0.o0", "narration.standard", 1)
	cases := []struct {
		name   string
		secret string
		text   string
	}{
		{"story 서버가 chat 의 가격표로", storySecret, storyUsesChat},
		{"chat 서버가 story 의 가격표로", chatSecret, chatUsesStory},
		{"story 서버가 서술의 가격표로", storySecret, storyUsesGame},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			holds := &fakeHolds{hold: aHold(t), isNew: true}

			response := signedAs(t, storyDeps(holds, nil), tc.secret, http.MethodPost, holdsURL, tc.text)

			// 없는 가격표와 같은 답이다. 홀드를 걸어 보지도 않는다
			if response.Code != http.StatusBadRequest || !strings.Contains(body(response), `"code":"price.unknown"`) || holds.calls != 0 {
				t.Errorf("상태 코드 = %d, 본문 = %s, 부른 수 = %d", response.Code, body(response), holds.calls)
			}
		})
	}
}

func TestTheStoryServerListsOnlyItsOwnPrices(t *testing.T) {
	response := signedAs(t, storyDeps(nil, &fakeLister{listings: mixedListing()}), storySecret, http.MethodGet, pricesURL, "")

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if !strings.Contains(body(response), `"code":"story.a.i0.o0"`) {
		t.Errorf("story 의 가격표가 없다: %s", body(response))
	}
	for _, code := range []string{"narration.a", "chat.a", "chatter.a"} {
		if strings.Contains(body(response), `"code":"`+code) {
			t.Errorf("%s 가 실렸다: %s", code, body(response))
		}
	}
}

func TestWithoutAStorySecretNothingPassesAsTheStoryServer(t *testing.T) {
	// story 서버를 띄우지 않는 동안은 비밀이 비어 있다. 빈 비밀로 서명한 요청이 통과하면 누구나 story 서버인 척할 수 있다
	holds := &fakeHolds{hold: aHold(t), isNew: true}
	deps := storyDeps(holds, nil)
	deps.StoryServerSecret = ""

	for _, secret := range []string{"", storySecret} {
		response := signedAs(t, deps, secret, http.MethodPost, holdsURL, storyHoldText)

		if response.Code != http.StatusUnauthorized || holds.calls != 0 {
			t.Errorf("비밀 %q: 상태 코드 = %d, 부른 수 = %d", secret, response.Code, holds.calls)
		}
	}
}

func TestTheStorySecretOpensOnlyTheSpendingAddresses(t *testing.T) {
	// 환영 크레딧과 결제 자격은 인증 서버의 것이다. story 서버의 비밀로 열리지 않는다
	deps := storyDeps(&fakeHolds{}, nil)
	deps.AuthServerSecret = "auth-server-test-secret-of-32-chars"

	for _, path := range []string{httpapi.APIPrefix + "/service/grants/welcome", httpapi.APIPrefix + "/service/eligibility"} {
		response := signedAs(t, deps, storySecret, http.MethodPost, path, `{}`)

		if response.Code != http.StatusUnauthorized {
			t.Errorf("%s: 상태 코드 = %d", path, response.Code)
		}
	}
}
