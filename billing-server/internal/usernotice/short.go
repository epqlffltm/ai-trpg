// billing-server/internal/usernotice/short.go

package usernotice

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice/usernoticedb"
)

// RecordShort 는 크레딧이 모자라 홀드를 걸지 못한 일을 적는다(credit.short, #525). 홀드가 부른다(hold.Shortfalls).
// 걸지 못한 홀드는 줄이 남지 않아 정리 작업이 찾을 수 없으므로 그 자리에서 적는다. 보내기는 다른 알림처럼 정리 작업이 한다.
//
// 사람마다 하루(한국 날짜)에 한 번이다. 그날 이미 적었으면 아무것도 하지 않는다. 라운드마다 모자란 사람에게 라운드마다 알리지 않는다.
// 새로 적었으면 queued, 그날 이미 적어 적지 않았으면 duplicate 로 센다(metrics.go). 적지 못한 것(DB 오류)은 세지 않는다.
// priceCode 와 amount 는 걸려던 가격표의 이름과 값이고, goldRequired 는 골드(산 크레딧)로만 낼 수 있었다는 것이다.
func (s *Service) RecordShort(ctx context.Context, userID uuid.UUID, priceCode string, amount credit.Amount, goldRequired bool) error {
	written, err := usernoticedb.New(s.pool).QueueShortNotice(ctx, usernoticedb.QueueShortNoticeParams{
		UserID:       userID,
		Now:          s.clock(),
		PriceCode:    priceCode,
		Amount:       int64(amount),
		GoldRequired: goldRequired,
	})
	if err != nil {
		return err
	}
	s.count(ctx, KindCreditsShort, shortOutcome(written), 1)
	return nil
}

// shortOutcome 은 크레딧 부족을 적은 줄의 수(0 이나 1)를 label outcome 의 값으로 바꾼다.
func shortOutcome(written int64) string {
	if written > 0 {
		return OutcomeQueued
	}
	return OutcomeDuplicate
}
