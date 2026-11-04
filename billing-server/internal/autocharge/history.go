// billing-server/internal/autocharge/history.go

package autocharge

import (
	"context"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// HistorySize 는 최근 자동 결제 내역에서 돌려주는 충전할 일의 수다.
const HistorySize = 20

// 사용자에게 보이는 충전할 일의 상태. 보내기 전(pending)과 보낸 뒤 답을 기다리는 것(charging)은 사용자에게 같다.
const (
	HistoryProcessing = "processing"
	HistoryPaid       = "paid"
	HistoryDeclined   = "declined"
	HistorySkipped    = "skipped"
)

// HistoryItem 은 충전할 일 하나다. 카드, 결제 대행사의 답과 거절 코드는 싣지 않는다.
type HistoryItem struct {
	// ID 는 충전할 일의 번호다. 결제되었으면 같은 번호의 주문이 있다
	ID        uuid.UUID
	ProductID string
	Price     int64
	Credits   credit.Amount
	// Status 는 HistoryProcessing, HistoryPaid, HistoryDeclined, HistorySkipped 중 하나다
	Status string
	// Reason 은 보내기 전에 그만둔 까닭(Skip*)이다. Status 가 HistorySkipped 일 때만 있다
	Reason string
	// TurnedOff 는 이 일이 실패해 자동 충전을 껐는지다
	TurnedOff  bool
	CreatedAt  time.Time
	FinishedAt *time.Time
}

// History 는 그 사람의 충전할 일을 늦게 적힌 것부터 HistorySize 개 돌려준다. 없으면 빈 목록이다.
func (s *Service) History(ctx context.Context, userID uuid.UUID) ([]HistoryItem, error) {
	rows, err := autochargedb.New(s.pool).ListRecentRequests(ctx, autochargedb.ListRecentRequestsParams{
		UserID: userID, RowLimit: HistorySize,
	})
	if err != nil {
		return nil, err
	}
	items := make([]HistoryItem, 0, len(rows))
	for _, row := range rows {
		items = append(items, historyItemOf(row))
	}
	return items, nil
}

// historyItemOf 는 DB 의 줄을 사용자에게 보일 모양으로 바꾼다.
func historyItemOf(row autochargedb.ListRecentRequestsRow) HistoryItem {
	item := HistoryItem{
		ID: row.ID, ProductID: row.ProductID, Price: row.Price, Credits: row.Credits,
		Status: historyStatus(row.Status), TurnedOff: row.TurnedOff, CreatedAt: row.CreatedAt,
	}
	if item.Status == HistorySkipped {
		item.Reason = row.SkipReason
	}
	if row.FinishedAt.Valid {
		finished := row.FinishedAt.Time
		item.FinishedAt = &finished
	}
	return item
}

// historyStatus 는 DB 의 상태를 사용자에게 보일 상태로 바꾼다.
func historyStatus(status string) string {
	switch status {
	case statusPaid:
		return HistoryPaid
	case statusDeclined:
		return HistoryDeclined
	case statusPending, statusCharging:
		return HistoryProcessing
	default:
		return HistorySkipped
	}
}
