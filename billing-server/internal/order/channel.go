// billing-server/internal/order/channel.go

package order

import (
	"context"
	"errors"
	"fmt"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 주문을 치른 길(channel)마다 결제 대행사를 따로 둔다.
//
// 지금은 웹(web) 하나다. 앱 안의 스토어 결제(구글 플레이)를 붙이면 길이 하나 는다.
// 스토어 결제는 승인의 순서가 달라(앱에서 이미 결제가 끝나고 서버는 확인한 뒤 소비 처리를 한다) payment.Provider 를
// 늘리지 않고 따로 받는다. 그래도 주문, 크레딧, 원장, 대사는 하나로 둔다. 길이 나뉘는 곳은 결제 대행사를 부르는 곳뿐이다.
// 그래서 결제 대행사를 부르는 곳은 모두 askProvider 를 거치고, askProvider 가 주문의 길을 보고 고른다.

// Channel 은 주문을 치른 길이다. DB 의 orders.channel 에 이 글자가 그대로 적힌다.
type Channel string

// ChannelWeb 은 웹에서 결제창을 열어 결제 대행사가 승인하는 길이다.
const ChannelWeb Channel = "web"

// Providers 는 길마다 부를 결제 대행사다.
type Providers map[Channel]payment.Provider

var (
	// ErrNoWebProvider 는 웹의 결제 대행사 없이 주문 서비스를 만들려 했다는 오류다. 서버를 만들 때만 난다.
	ErrNoWebProvider = errors.New("웹의 결제 대행사가 없습니다")
	// ErrNoProviderForChannel 은 주문의 길에 맞는 결제 대행사가 이 서버에 없다는 오류다.
	// 결제 대행사에 묻지 못한 것과 같이 다룬다. 주문은 그 상태 그대로 남는다.
	ErrNoProviderForChannel = errors.New("이 주문의 길에 맞는 결제 대행사가 없습니다")
)

// checkProviders 는 서버를 만들 때 결제 대행사가 빠지지 않았는지 본다. 웹은 늘 있어야 한다.
func checkProviders(providers Providers) error {
	if providers[ChannelWeb] == nil {
		return ErrNoWebProvider
	}
	for channel, provider := range providers {
		if provider == nil {
			return fmt.Errorf("%w: %s", ErrNoProviderForChannel, channel)
		}
	}
	return nil
}

// providerFor 는 주문의 길에 맞는 결제 대행사를 고른다.
func (s *Service) providerFor(current Order) (payment.Provider, error) {
	provider, ok := s.providers[current.Channel]
	if !ok {
		return nil, fmt.Errorf("%w: %q", ErrNoProviderForChannel, current.Channel)
	}
	return provider, nil
}

// askProvider 는 주문의 길에 맞는 결제 대행사를 골라 부르되 ProviderTimeout 까지만 기다린다.
// 맞는 결제 대행사가 없으면 부르지 않고 오류를 돌려준다. 부르는 쪽은 답을 받지 못한 것과 같이 다룬다.
func (s *Service) askProvider(ctx context.Context, current Order, ask func(context.Context, payment.Provider) (payment.Result, error)) (payment.Result, error) {
	provider, err := s.providerFor(current)
	if err != nil {
		return payment.Result{}, err
	}
	ctx, cancel := context.WithTimeout(ctx, ProviderTimeout)
	defer cancel()
	return ask(ctx, provider)
}
