// billing-server/internal/order/sweep.go

package order

import (
	"context"
	"errors"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/batch"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// ExpireDue 는 만료 시각이 지난 pending 주문을 오래된 것부터 limit 개까지 expired 로 바꾼다(정리 작업).
// 바꾼 주문의 수를 돌려준다. pending 주문은 돈이 오간 적이 없어서 끝내도 안전하다.
// confirming 주문은 건드리지 않는다. 돈이 나갔을 수 있다. 그것은 대사가 결제 대행사에 물어 끝낸다(ResolveStale).
func (s *Service) ExpireDue(ctx context.Context, limit int) (int, error) {
	expired, err := orderdb.New(s.pool).ExpireDueOrders(ctx, orderdb.ExpireDueOrdersParams{Now: s.clock(), RowLimit: int32(limit)})
	return int(expired), err
}

// StaleReport 는 오래된 confirming·refunding 주문을 결제 대행사에 물어 본 결과다.
type StaleReport struct {
	// Found 는 찾은 오래된 주문의 수다(confirming 과 refunding 을 더한 것).
	Found int
	// Paid 와 Failed 는 이번에 끝낸 confirming 주문의 수다.
	Paid   int
	Failed int
	// Refunded 는 이번에 환불을 끝낸 refunding 주문의 수, RefundRefused 는 결제 대행사가 취소를 거절해 paid 로 되돌린 수다.
	Refunded      int
	RefundRefused int
	// Unknown 은 결제 대행사도 아직 모르거나, 답을 받지 못해 그 상태에 남은 주문의 수다.
	Unknown int
	// Errored 는 다루다 오류가 난 주문의 수다(DB 오류 같은 것). 그 상태에 남고 다음 대사에서 다시 다룬다.
	Errored int
}

// ResolveStale 은 olderThan 보다 오래 confirming·refunding 에 머문 주문을 종류마다 limit 개까지 결제 대행사에 물어 끝낸다(대사).
// 요청한 쪽이 다시 오지 않고 알림도 오지 않은 주문이다.
//   - confirming: 승인을 다시 요청하지 않고 결과만 묻는다(조회). 승인을 또 요청하면 돈이 두 번 나갈 수 있다
//   - refunding: 같은 취소를 다시 보낸다. 취소는 다시 보내도 한 번만 된다
//
// 결제 대행사의 답이 없으면 그 상태 그대로 두고 다음 대사에서 다시 묻는다.
// 한 주문에서 오류가 나도 나머지는 마저 다루고, 오류가 난 수를 오류로 알린다(batch.Each).
func (s *Service) ResolveStale(ctx context.Context, olderThan time.Duration, limit int) (StaleReport, error) {
	queries := orderdb.New(s.pool)
	before := s.clock().Add(-olderThan)
	confirming, err := queries.ListStaleConfirming(ctx, orderdb.ListStaleConfirmingParams{Before: before, RowLimit: int32(limit)})
	if err != nil {
		return StaleReport{}, err
	}
	refunding, err := queries.ListStaleRefunding(ctx, orderdb.ListStaleRefundingParams{Before: before, RowLimit: int32(limit)})
	if err != nil {
		return StaleReport{}, err
	}
	report := StaleReport{Found: len(confirming) + len(refunding)}
	_, confirmErr := batch.Each(ctx, confirming, report.track(s.resolveOne))
	_, refundErr := batch.Each(ctx, refunding, report.track(s.resolveRefund))
	return report, errors.Join(confirmErr, refundErr)
}

// track 은 주문 하나를 끝내는 함수를 batch.Each 가 부를 모양으로 감싸고, 끝난 상태를 결과에 센다.
func (r *StaleReport) track(resolve func(context.Context, Order) (Order, error)) func(context.Context, orderdb.Order) (bool, error) {
	return func(ctx context.Context, row orderdb.Order) (bool, error) {
		started := Status(row.Status)
		finished, err := resolve(ctx, toOrder(row))
		if err != nil {
			r.Errored++
			return false, err
		}
		r.count(started, finished.Status)
		return true, nil
	}
}

// resolveOne 은 confirming 주문 하나를 결제 대행사에 물어 끝낸다. 끝난 뒤의 주문을 돌려준다.
func (s *Service) resolveOne(ctx context.Context, current Order) (Order, error) {
	result, err := s.lookUp(ctx, current)
	return s.settle(ctx, current, result, err)
}

// count 는 끝난 주문 하나를 결과에 센다. 같은 paid 라도 승인이 끝난 것과 환불이 거절된 것을 나눈다.
func (r *StaleReport) count(started Status, finished Status) {
	switch {
	case finished == StatusPaid && started == StatusRefunding:
		r.RefundRefused++
	case finished == StatusPaid:
		r.Paid++
	case finished == StatusFailed:
		r.Failed++
	case finished == StatusRefunded:
		r.Refunded++
	default:
		r.Unknown++
	}
}
