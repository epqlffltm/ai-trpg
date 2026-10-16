// billing-server/internal/order/channel_test.go

// 주문의 길(channel)과 길마다의 결제 대행사를 확인한다.
package order_test

import (
	"errors"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

func TestOrdersAreMadeOnTheWeb(t *testing.T) {
	f := setUp(t, approving())

	created := f.create()

	var stored string
	if err := f.pool.QueryRow(ctx(t), "SELECT channel FROM orders WHERE id = $1", created.ID).Scan(&stored); err != nil {
		t.Fatalf("주문을 읽지 못했다: %v", err)
	}
	if created.Channel != order.ChannelWeb || stored != string(order.ChannelWeb) {
		t.Errorf("길 = %q, DB 의 길 = %q. web 이어야 한다", created.Channel, stored)
	}
}

func TestNewServiceRefusesMissingProviders(t *testing.T) {
	f := setUp(t, approving())
	cases := map[string]struct {
		providers order.Providers
		want      error
	}{
		"없다":        {nil, order.ErrNoWebProvider},
		"웹이 없다":     {order.Providers{"google_play": f.provider}, order.ErrNoWebProvider},
		"웹이 nil":    {order.Providers{order.ChannelWeb: nil}, order.ErrNoWebProvider},
		"다른 길이 nil": {order.Providers{order.ChannelWeb: f.provider, "google_play": nil}, order.ErrNoProviderForChannel},
	}
	for name, c := range cases {
		if _, err := order.NewService(f.pool, f.clock.Now, c.providers, f.wallet, ttl); !errors.Is(err, c.want) {
			t.Errorf("%s: %v. %v 여야 한다", name, err, c.want)
		}
	}
}

func TestProviderForPicksTheOrdersChannel(t *testing.T) {
	f := setUp(t, approving())

	got, err := order.ProviderFor(f.service, order.Order{Channel: order.ChannelWeb})
	if err != nil || got != f.provider {
		t.Errorf("web: %v, %v. 넘겨준 웹의 결제 대행사여야 한다", got, err)
	}
	// 이 서버에 없는 길의 주문이면 아무 결제 대행사도 부르지 않는다. 웹의 것으로 대신 묻지 않는다
	for _, channel := range []order.Channel{"google_play", ""} {
		if got, err := order.ProviderFor(f.service, order.Order{Channel: channel}); got != nil || !errors.Is(err, order.ErrNoProviderForChannel) {
			t.Errorf("%q: %v, %v. ErrNoProviderForChannel 이어야 한다", channel, got, err)
		}
	}
}
