// billing-server/internal/autocharge/resolve.go

package autocharge

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// 사람이 결과를 정하기(#980). 결제 대행사가 끝내 답하지 않아 charging 에 남은 일을, 사람이 상점관리자에서 확인하고 정한다(cmd/autocharges).
//
// 정할 수 있는 것은 다시 보내는 기한(ResendFor)이 지난 일뿐이다. 그 전에는 결제 작업이 같은 결제를 다시 보낸다.
// 사람이 "거절"로 정한 뒤에 다시 보낸 것이 승인되면 돈은 나가고 골드는 들어가지 않는다. 기한 뒤에는 조회만 하므로 결제가 새로 생기지 않는다.
//
// 정한 것은 결제 작업의 답과 같은 길로 적는다(settlePaid, settleDeclined). 주문, 골드, 이어서 실패한 수, 알림함이 같다.
// 결제 작업의 조회와 엇갈리면 먼저 적은 쪽이 남는다. 늦은 쪽은 ErrResolvedElsewhere 다.

// Outcome 은 사람이 정하는 결과다.
type Outcome string

const (
	// OutcomePaid 는 상점관리자에서 결제가 완료된 것을 봤다는 것이다. 결제 번호를 함께 적는다.
	OutcomePaid Outcome = "paid"
	// OutcomeDeclined 는 상점관리자에서 결제가 없거나 되지 않은 것을 봤다는 것이다. 돈이 나가지 않았다.
	OutcomeDeclined Outcome = "declined"
)

// FailureCodeResolved 는 사람이 거절로 정한 일의 failure_code 다.
const FailureCodeResolved = "resolved_declined"

// maxPaymentKeyLength 는 결제 번호의 가장 긴 길이다. 토스페이먼츠의 paymentKey 는 200자까지다.
const maxPaymentKeyLength = 200

var (
	// ErrResolutionIncomplete 는 결과, 근거, 정한 사람, (결제됨이면) 결제 번호가 빠졌거나 틀렸다는 오류다.
	ErrResolutionIncomplete = errors.New("결과, 근거(-reason), 정한 사람(-by)이 있어야 하고, 결제됨이면 결제 번호(-payment-key)가, 거절이면 결제 번호가 없어야 합니다")
	// ErrRequestNotFound 는 그 번호의 일이 없다는 오류다.
	ErrRequestNotFound = errors.New("그 번호의 자동 충전이 없습니다")
	// ErrNotCharging 은 보낸 뒤 답을 기다리는(charging) 일이 아니라는 오류다.
	ErrNotCharging = errors.New("결과를 기다리는 자동 충전이 아닙니다")
	// ErrStillResending 은 아직 다시 보내는 기한 안이라 정할 수 없다는 오류다.
	ErrStillResending = errors.New("결제 작업이 아직 다시 보내는 중이라 정할 수 없습니다")
	// ErrResolvedElsewhere 는 그사이 결제 작업이 먼저 결과를 적었다는 오류다.
	ErrResolvedElsewhere = errors.New("그사이 결제 작업이 먼저 결과를 적었습니다. 다시 확인해 주세요")
)

// Resolution 은 사람이 정한 결과 하나다.
type Resolution struct {
	// ID 는 일의 번호다. 결제 대행사의 주문 번호다.
	ID      uuid.UUID
	Outcome Outcome
	// PaymentKey 는 상점관리자에서 본 결제 번호다. 결제됨일 때만 적는다. 주문에 적힌다.
	PaymentKey string
	// Reason 은 근거다. 무엇을 보고 정했는지 적는다.
	Reason string
	// DecidedBy 는 정한 사람이다.
	DecidedBy string
}

// OpenRequest 는 끝나지 않은 일 하나를 사람이 보는 모양이다. 사용자와 카드는 싣지 않는다.
type OpenRequest struct {
	ID        uuid.UUID
	Status    string
	ProductID string
	Price     int64
	Attempts  int32
	// LastError 는 마지막으로 답을 받지 못한 까닭이다(잘라 적은 것).
	LastError string
	CreatedAt time.Time
	// Decidable 은 지금 사람이 정할 수 있는지다(charging 이고 다시 보내는 기한이 지났다).
	Decidable bool
}

// ListOpen 은 끝나지 않은 채 olderThan 넘게 지난 일을 오래된 것부터 limit 개까지 읽는다.
func (s *Service) ListOpen(ctx context.Context, olderThan time.Duration, limit int) ([]OpenRequest, error) {
	now := s.clock()
	rows, err := autochargedb.New(s.pool).ListOpenRequests(ctx, autochargedb.ListOpenRequestsParams{
		Before: now.Add(-olderThan), RowLimit: int32(limit),
	})
	if err != nil {
		return nil, err
	}
	open := make([]OpenRequest, len(rows))
	for i, row := range rows {
		open[i] = openRequestOf(row, now)
	}
	return open, nil
}

// openRequestOf 는 일 한 줄을 사람이 보는 모양으로 바꾼다.
func openRequestOf(row autochargedb.AutoChargeRequest, now time.Time) OpenRequest {
	return OpenRequest{
		ID: row.ID, Status: row.Status, ProductID: row.ProductID, Price: row.Price, Attempts: row.Attempts,
		LastError: row.LastError, CreatedAt: row.CreatedAt,
		Decidable: row.Status == statusCharging && PastResend(row.CreatedAt, now),
	}
}

// Resolve 는 사람이 정한 결과를 적는다. 결제 작업이 붙은 Service(WithCharging)에서 부른다.
func (s *Service) Resolve(ctx context.Context, decision Resolution) error {
	if err := checkResolution(decision); err != nil {
		return err
	}
	request, err := s.decidable(ctx, decision.ID)
	if err != nil {
		return err
	}
	settled, err := s.applyResolution(ctx, request, decision)
	if err != nil {
		return err
	}
	if !settled {
		return ErrResolvedElsewhere
	}
	logResolution(ctx, request, decision)
	return nil
}

// checkResolution 은 결정에 빠진 것이 없는지 본다. DB 를 보지 않는다.
func checkResolution(decision Resolution) error {
	if strings.TrimSpace(decision.Reason) == "" || strings.TrimSpace(decision.DecidedBy) == "" {
		return ErrResolutionIncomplete
	}
	key := strings.TrimSpace(decision.PaymentKey)
	switch decision.Outcome {
	case OutcomePaid:
		if key == "" || len(key) > maxPaymentKeyLength || strings.ContainsAny(key, " \t\r\n") {
			return ErrResolutionIncomplete
		}
	case OutcomeDeclined:
		if key != "" {
			return ErrResolutionIncomplete
		}
	default:
		return ErrResolutionIncomplete
	}
	return nil
}

// decidable 은 사람이 정할 수 있는 그 일을 읽는다. charging 이고 다시 보내는 기한이 지나야 한다.
func (s *Service) decidable(ctx context.Context, id uuid.UUID) (autochargedb.AutoChargeRequest, error) {
	request, err := autochargedb.New(s.pool).GetRequest(ctx, id)
	if errors.Is(err, pgx.ErrNoRows) {
		return request, ErrRequestNotFound
	}
	if err != nil {
		return request, err
	}
	if request.Status != statusCharging {
		return request, fmt.Errorf("%w. 지금은 %s 입니다", ErrNotCharging, request.Status)
	}
	if !PastResend(request.CreatedAt, s.clock()) {
		return request, fmt.Errorf("%w. %s 부터 정할 수 있습니다", ErrStillResending, request.CreatedAt.Add(ResendFor).UTC().Format(time.RFC3339))
	}
	return request, nil
}

// applyResolution 은 정한 결과를 결제 작업의 답과 같은 길로 적는다. 적었으면 true 다.
// 결제 번호가 다른 주문에 이미 쓰였으면 order.ErrPaymentKeyUsed 다(잘못 옮겨 적은 것이다). 아무것도 적지 않는다.
func (s *Service) applyResolution(ctx context.Context, request autochargedb.AutoChargeRequest, decision Resolution) (bool, error) {
	if decision.Outcome == OutcomePaid {
		settled, err := s.settlePaid(ctx, request, strings.TrimSpace(decision.PaymentKey))
		if pgErr := (*pgconn.PgError)(nil); errors.As(err, &pgErr) && pgErr.ConstraintName == paymentKeyOnce {
			return false, order.ErrPaymentKeyUsed
		}
		return settled, err
	}
	return s.settleDeclined(ctx, request, FailureCodeResolved)
}

// paymentKeyOnce 는 결제 번호 하나를 주문 하나에만 쓰게 하는 제약의 이름이다(migrations/00002_orders.sql).
const paymentKeyOnce = "orders_payment_key_once"

// logResolution 은 정한 것을 남긴다. 결제 번호와 사용자는 싣지 않는다(주문에 있다).
func logResolution(ctx context.Context, request autochargedb.AutoChargeRequest, decision Resolution) {
	slog.InfoContext(ctx, "운영자가 결과를 모르던 자동 충전의 결과를 정했다",
		slog.String("operation", "autocharge.resolve"),
		slog.String("auto_charge_id", request.ID.String()),
		slog.String("outcome", string(decision.Outcome)),
		slog.String("decided_by", decision.DecidedBy),
		slog.String("reason", decision.Reason),
	)
}
