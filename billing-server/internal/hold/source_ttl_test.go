// billing-server/internal/hold/source_ttl_test.go

// 부른 서버마다 따로 정한 홀드의 만료(WithSourceTTL)를 시험한다. chat 서버의 홀드는 짧다.
package hold_test

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold"
)

const (
	// chatSource 는 chat 서버의 이름이다(internal/peers).
	chatSource = "chat-server"
	// chatTTL 은 테스트가 chat 서버에 정하는 만료까지의 시간이다.
	chatTTL = 10 * time.Minute
)

// withChatTTL 은 chat 서버의 홀드를 chatTTL 로 두고 그 사용자의 크레딧을 채운다.
func (f fixture) withChatTTL() {
	f.t.Helper()
	if err := f.service.WithSourceTTL(chatSource, chatTTL); err != nil {
		f.t.Fatalf("chat 서버의 기한을 정하지 못했다: %v", err)
	}
	f.fund(0, 10*price)
}

func TestAChatHoldExpiresSooner(t *testing.T) {
	f := setUp(t)
	f.withChatTTL()

	chat, _, err := f.service.Place(ctx(t), chatSource, f.user, newReference(), priceCode)
	if err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	game := f.place(newReference())

	if want := f.clock.Now().Add(chatTTL); !chat.ExpiresAt.Equal(want) {
		t.Errorf("chat 홀드의 만료 = %v, 기대 = %v", chat.ExpiresAt, want)
	}
	// 따로 정하지 않은 서버(게임 서버)는 기본 그대로다
	if want := f.clock.Now().Add(ttl); !game.ExpiresAt.Equal(want) {
		t.Errorf("게임 홀드의 만료 = %v, 기대 = %v", game.ExpiresAt, want)
	}
}

func TestExtendingAChatHoldPushesByItsOwnTTL(t *testing.T) {
	f := setUp(t)
	f.withChatTTL()
	reference := newReference()
	if _, _, err := f.service.Place(ctx(t), chatSource, f.user, reference, priceCode); err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	f.clock.Advance(5 * time.Minute)

	extended, err := f.service.Extend(ctx(t), chatSource, reference)

	if err != nil || !extended.ExpiresAt.Equal(f.clock.Now().Add(chatTTL)) {
		t.Errorf("연장한 만료 = %v, 오류 = %v. 지금부터 %v 뒤여야 한다", extended.ExpiresAt, err, chatTTL)
	}
}

func TestASourceTTLMustBePositive(t *testing.T) {
	f := setUp(t)

	for _, bad := range []time.Duration{0, -time.Minute} {
		if err := f.service.WithSourceTTL(chatSource, bad); !errors.Is(err, hold.ErrInvalidTTL) {
			t.Errorf("%v: 오류 = %v", bad, err)
		}
	}
}
