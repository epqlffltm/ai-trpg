// billing-server/internal/order/decide.go

package order

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order/orderdb"
)

// 운영자가 결과를 정하는 길. 결제 대행사도 이 서버도 끝내 결과를 모르는 주문(ListStuck)을 사람이 끝낸다.
// 운영자는 결제 대행사의 상점관리자에서 그 주문의 결제를 확인하고 결과를 정한다.
//
//   - confirming → paid(돈이 나갔다. 크레딧을 넣는다) 또는 failed(돈이 나가지 않았다)
//   - refunding  → refunded(돈이 돌아갔다) 또는 paid(취소되지 않았다. 뺐던 크레딧을 돌려놓는다)
//
// 상태를 바꾸는 길은 결제 대행사가 답했을 때와 같다(pay, fail, markRefunded, restorePaid). 지갑과 원장도 같은 줄이 남는다.
// 모든 변경이 "아직 그 상태일 때만" 바꾸므로, 그사이 알림이나 대사가 먼저 끝냈으면 이 결정은 쓰이지 않는다(ErrDecidedElsewhere).

// Outcome 은 운영자가 정하는 결과다.
type Outcome string

// 운영자가 정할 수 있는 결과.
const (
	OutcomePaid     Outcome = Outcome(StatusPaid)
	OutcomeFailed   Outcome = Outcome(StatusFailed)
	OutcomeRefunded Outcome = Outcome(StatusRefunded)
)

// FailureCodeManual 은 운영자가 failed 로 정한 주문의 거절 이유다.
const FailureCodeManual = "manual"

var (
	// ErrNotUndecided 는 결과를 모르는 주문(confirming, refunding)이 아니라는 오류다. 끝난 주문의 결과는 바꾸지 않는다.
	ErrNotUndecided = errors.New("결과를 모르는 주문(confirming, refunding)만 정할 수 있습니다")
	// ErrOutcomeNotAllowed 는 그 상태에서 정할 수 없는 결과라는 오류다(confirming 을 refunded 로, refunding 을 failed 로).
	ErrOutcomeNotAllowed = errors.New("confirming 은 paid 나 failed 로, refunding 은 refunded 나 paid 로만 정할 수 있습니다")
	// ErrDecisionIncomplete 는 이유나 정한 사람이 비었다는 오류다.
	ErrDecisionIncomplete = errors.New("정한 이유와 정한 사람을 적어야 합니다")
	// ErrDecidedElsewhere 는 그사이 다른 길(알림, 대사, 다시 보낸 요청)이 먼저 다른 결과로 끝냈다는 오류다.
	ErrDecidedElsewhere = errors.New("그사이 다른 요청이 먼저 이 주문을 끝냈습니다. 지금의 상태를 확인해 주세요")
)

// Decision 은 운영자의 결정 하나다.
type Decision struct {
	OrderID uuid.UUID
	Outcome Outcome
	// Reason 은 그렇게 정한 근거다(상점관리자에서 본 것). 로그에 남는다.
	Reason string
	// DecidedBy 는 정한 사람이다. 로그에 남는다.
	DecidedBy string
}

// Decide 는 결과를 모르는 주문의 결과를 운영자가 정한다. 끝난 뒤의 주문을 돌려준다.
// 다른 길이 먼저 같은 결과로 끝냈으면 그대로 돌려주고, 다른 결과로 끝냈으면 ErrDecidedElsewhere 다.
// 작업 전체는 OperationTimeout 안에 끝난다. 넘으면 ErrTimedOut 을 감싼 오류다(detach).
func (s *Service) Decide(ctx context.Context, decision Decision) (Order, error) {
	ctx, cancel := s.detach(ctx)
	defer cancel()
	decided, err := s.decide(ctx, decision)
	return decided, timedOut(ctx, err)
}

// decide 는 Decide 의 본문이다.
func (s *Service) decide(ctx context.Context, decision Decision) (Order, error) {
	if strings.TrimSpace(decision.Reason) == "" || strings.TrimSpace(decision.DecidedBy) == "" {
		return Order{}, ErrDecisionIncomplete
	}
	current, err := s.undecided(ctx, decision.OrderID)
	if err != nil {
		return Order{}, err
	}
	decided, err := s.apply(ctx, current, decision.Outcome)
	if err != nil {
		return decided, err
	}
	if decided.Status != Status(decision.Outcome) {
		return decided, ErrDecidedElsewhere
	}
	logDecision(ctx, current, decision)
	return decided, nil
}

// undecided 는 결과를 모르는 그 주문을 읽는다. 없으면 ErrNotFound, 끝난 주문이면 ErrNotUndecided 다.
func (s *Service) undecided(ctx context.Context, orderID uuid.UUID) (Order, error) {
	row, err := orderdb.New(s.pool).GetOrder(ctx, orderID)
	if errors.Is(err, pgx.ErrNoRows) {
		return Order{}, ErrNotFound
	}
	if err != nil {
		return Order{}, err
	}
	current := toOrder(row)
	if current.Status != StatusConfirming && current.Status != StatusRefunding {
		return current, fmt.Errorf("%w. 지금은 %s 입니다", ErrNotUndecided, current.Status)
	}
	return current, nil
}

// apply 는 주문의 지금 상태와 정한 결과에 맞는 변경을 한다. 결제 대행사가 답했을 때와 같은 길이다.
func (s *Service) apply(ctx context.Context, current Order, outcome Outcome) (Order, error) {
	switch {
	case current.Status == StatusConfirming && outcome == OutcomePaid:
		return s.pay(ctx, current)
	case current.Status == StatusConfirming && outcome == OutcomeFailed:
		return s.fail(ctx, current, FailureCodeManual)
	case current.Status == StatusRefunding && outcome == OutcomeRefunded:
		return s.markRefunded(ctx, current)
	case current.Status == StatusRefunding && outcome == OutcomePaid:
		restored, err := s.restorePaid(ctx, current, FailureCodeManual)
		if errors.Is(err, ErrRefundRefused) {
			// restorePaid 는 되돌렸다는 것을 ErrRefundRefused 로 알린다. 운영자가 고른 결과라 오류가 아니다
			return restored, nil
		}
		return restored, err
	default:
		return current, ErrOutcomeNotAllowed
	}
}

// logDecision 은 운영자의 결정을 남긴다. 결제 번호는 적지 않는다. 주문 번호로 찾는다.
func logDecision(ctx context.Context, before Order, decision Decision) {
	slog.InfoContext(ctx, "운영자가 결과를 모르던 주문의 결과를 정했다",
		slog.String("operation", "order.decide"),
		slog.String("order_id", before.ID.String()),
		slog.String("from_status", string(before.Status)),
		slog.String("outcome", string(decision.Outcome)),
		slog.String("decided_by", decision.DecidedBy),
		slog.String("reason", decision.Reason),
	)
}
