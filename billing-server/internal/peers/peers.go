// billing-server/internal/peers/peers.go

// Package peers 는 결제 서버를 부르는 우리 서버들의 이름이다.
//
// 서명을 확인한 서버의 이름이 홀드의 "누가 걸었는가"(holds.source)로 적힌다. 관측 규격의 서비스 이름과 같다.
// 주소를 나누는 곳(httpapi)과 서버마다 규칙이 다른 곳(홀드의 만료)이 같은 이름을 쓰게 여기 한 곳에 둔다.
// 이름을 바꾸면 이미 적힌 홀드의 source 와 어긋난다. 바꾸지 않는다.
package peers

const (
	// Game 은 게임 서버다. 라운드의 AI 서술에 홀드를 건다.
	Game = "trpg-server"
	// Auth 는 인증 서버다. 환영 크레딧과 결제 자격을 보낸다.
	Auth = "auth-server"
	// Chat 은 chat 서버다. 캐릭터와 나누는 말 한 번에 홀드를 건다.
	Chat = "chat-server"
	// Story 는 story 서버다. 세계관 안의 세션에서 말 한 번에 홀드를 건다.
	Story = "story-server"
)
