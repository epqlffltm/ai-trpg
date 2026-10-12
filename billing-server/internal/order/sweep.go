// billing-server/internal/order/sweep.go

package order

import (
	"context"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/batch"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// ExpireDue 는 만료 시각이 지난 pending 주문을 오래된 것부터 limit 개까지 expired 로 바꾼다(정리 작업).
// 바꾼 주문의 수를 돌려준다. pending 주문은 돈이 오간 적이 없어서 끝내도 안전하다.
// confirming 주문은 건드리지 않는다. 돈이 나갔을 수 있다. 그것은 대사가 결제 대행사에 물어 끝낸다(ResolveStale).
func (s *Service) ExpireDue(ctx context.Context, limit int) (int, error) {
	expired, err := orderdb.New(s.pool).ExpireDueOrders(ctx, orderdb.ExpireDueOrdersParams{Now: s.clock(), RowLimit: int32(limit)})
	return int(expired), err
}

// StaleReport 는 오래된 confirming 주문을 결제 대행사에 물어 본 결과다.
type StaleReport struct {
	// Found 는 찾은 오래된 confirming 주문의 수다.
	Found int
	// Paid 와 Failed 는 이번에 끝낸 주문의 수다.
	Paid   int
	Failed int
	// Unknown 은 결제 대행사도 아직 모르거나, 답을 받지 못해 confirming 에 남은 주문의 수다.
	Unknown int
	// Errored 는 다루다 오류가 난 주문의 수다(DB 오류 같은 것). confirming 에 남고 다음 대사에서 다시 다룬다.
	Errored int
}

// ResolveStale 은 olderThan 보다 오래 confirming 에 머문 주문을 limit 개까지 결제 대행사에 물어 끝낸다(대사).
// 승인을 요청한 쪽이 다시 오지 않고 알림도 오지 않은 주문이다. 승인을 다시 요청하지 않고 결과만 묻는다.
// 결제 대행사의 답이 없으면 confirming 그대로 두고 다음 대사에서 다시 묻는다.
// 한 주문에서 오류가 나도 나머지는 마저 다루고, 오류가 난 수를 오류로 알린다(batch.Each).
func (s *Service) ResolveStale(ctx context.Context, olderThan time.Duration, limit int) (StaleReport, error) {
	rows, err := orderdb.New(s.pool).ListStaleConfirming(ctx, orderdb.ListStaleConfirmingParams{
		Before: s.clock().Add(-olderThan), RowLimit: int32(limit),
	})
	if err != nil {
		return StaleReport{}, err
	}
	report := StaleReport{Found: len(rows)}
	_, err = batch.Each(ctx, rows, func(ctx context.Context, row orderdb.Order) (bool, error) {
		finished, err := s.resolveOne(ctx, toOrder(row))
		if err != nil {
			report.Errored++
			return false, err
		}
		report.count(finished.Status)
		return true, nil
	})
	return report, err
}

// resolveOne 은 confirming 주문 하나를 결제 대행사에 물어 끝낸다. 끝난 뒤의 주문을 돌려준다.
func (s *Service) resolveOne(ctx context.Context, current Order) (Order, error) {
	result, err := s.askProvider(ctx, func(ctx context.Context) (payment.Result, error) {
		return s.provider.Lookup(ctx, current.PaymentKey)
	})
	return s.settle(ctx, current, result, err)
}

// count 는 끝난 주문 하나를 결과에 센다.
func (r *StaleReport) count(status Status) {
	switch status {
	case StatusPaid:
		r.Paid++
	case StatusFailed:
		r.Failed++
	default:
		r.Unknown++
	}
}
