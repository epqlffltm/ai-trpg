// billing-server/internal/order/deposit.go

package order

import (
	"context"
	"log/slog"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// 가상계좌를 받지 않는다(유저의 결정, 2026-10-13). 결제창에서 가상계좌를 고를 수 없게 막지만(개발용 화면은 카드만 연다),
// 결제위젯의 설정이나 다른 클라이언트로 가상계좌가 발급되어 승인이나 조회의 답이 "입금 대기"로 올 수 있다.
// 그 결제를 곧바로 취소하고 주문을 끝낸다. 입금 전의 취소라 환불 계좌가 필요 없고 돈이 오간 적이 없다.
//
// 취소의 답을 받지 못하거나 거절되면(그사이 입금되었을 수 있다) confirming 에 그대로 둔다.
// 다음 승인 요청, 알림, 대사의 조회가 다시 본다. 입금되었으면 승인(paid)으로, 취소되었으면 거절(failed)로 끝난다.

// FailureCodeDepositUnsupported 는 가상계좌라서 취소하고 끝낸 주문의 거절 이유다.
const FailureCodeDepositUnsupported = "VIRTUAL_ACCOUNT_NOT_SUPPORTED"

// depositCancelReason 은 가상계좌를 취소할 때 결제 대행사에 싣는 이유다. 상점관리자에 보인다.
const depositCancelReason = "가상계좌 미지원"

// refuseDeposit 은 입금을 기다리는 가상계좌 결제를 취소하고, 취소되었으면 주문을 failed 로 끝낸다.
func (s *Service) refuseDeposit(ctx context.Context, current Order) (Order, error) {
	request := paymentRequest(current)
	request.CancelReason = depositCancelReason
	result, err := s.askProvider(ctx, current, func(ctx context.Context, provider payment.Provider) (payment.Result, error) {
		return provider.Cancel(ctx, request)
	})
	if err == nil && result.Status == payment.StatusCanceled {
		return s.fail(ctx, current, FailureCodeDepositUnsupported)
	}
	logDepositNotCanceled(ctx, current, result, err)
	return current, nil
}

// logDepositNotCanceled 는 가상계좌를 취소하지 못해 결과를 모르는 채로 둔 것을 남긴다. 결제 번호는 적지 않는다.
func logDepositNotCanceled(ctx context.Context, current Order, result payment.Result, err error) {
	attrs := []any{
		slog.String("operation", "order.confirm"),
		slog.String("error_code", "payment.provider_unavailable"),
		slog.String("order_id", current.ID.String()),
		slog.String("cancel_status", string(result.Status)),
	}
	if err != nil {
		attrs = append(attrs, slog.String("error_message", err.Error()))
	}
	slog.WarnContext(ctx, "가상계좌 결제를 취소하지 못했다. 결과를 모르는 채로 둔다", attrs...)
}
