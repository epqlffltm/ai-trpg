// billing-server/internal/hold/shortfall.go

package hold

import (
	"context"
	"errors"
	"log/slog"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 크레딧이 모자라 홀드를 걸지 못한 일을 알린다(#525). 사용자의 알림함에 "크레딧이 모자랍니다"를 넣으려는 것이다.
//
// 걸지 못한 홀드는 줄이 남지 않는다(트랜잭션이 되돌려진다). 그래서 정리 작업이 나중에 찾을 수 없고, 걸지 못한 그 자리에서 알린다.
// 홀드는 알림을 모른다. 받는 쪽(*usernotice.Service)이 하루 한 번으로 줄이고 알림함에 보낸다.

// Shortfalls 는 크레딧이 모자라 걸지 못한 일을 받는 것이다. *usernotice.Service 가 이 모양이다.
// priceCode 와 amount 는 걸려던 가격표의 이름과 값이다. goldRequired 는 프리미엄이라 골드(산 크레딧)로만 낼 수 있었다는 것이다.
type Shortfalls interface {
	RecordShort(ctx context.Context, userID uuid.UUID, priceCode string, amount credit.Amount, goldRequired bool) error
}

// WithShortfalls 는 크레딧이 모자라 걸지 못한 일을 shortfalls 에 알리게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) WithShortfalls(shortfalls Shortfalls) {
	s.shortfalls = shortfalls
}

// noteShort 는 모자라 걸지 못한 일(short 는 wallet.ErrInsufficient 인 오류)을 알린다. 붙여 둔 것이 없으면 아무것도 하지 않는다.
// 알리지 못해도 홀드의 답(모자람)은 그대로다. 알림은 덤이라 warning 한 줄만 남긴다.
func (s *Service) noteShort(ctx context.Context, userID uuid.UUID, price pricing.Price, short error) {
	if s.shortfalls == nil {
		return
	}
	err := s.shortfalls.RecordShort(ctx, userID, price.Code, price.Credits, errors.Is(short, wallet.ErrPaidInsufficient))
	if err != nil {
		slog.WarnContext(ctx, "크레딧이 모자란 것을 알림함에 적지 못했다",
			slog.String("kind", "credit.short"),
			slog.String("price_code", price.Code),
			slog.String("error_message", err.Error()),
		)
	}
}
