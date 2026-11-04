// billing-server/internal/httpapi/autocharge_history.go

package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 자동 충전의 최근 내역(#980). 로그인이 필요하고, 누구의 것인지는 토큰에서만 정한다.
//
//	GET /auto-charge/history   최근 충전할 일(늦게 적힌 것부터 autocharge.HistorySize 개)

// AutoChargeHistory 는 최근 자동 결제 내역을 읽는 것의 모양이다. *autocharge.Service 가 이 모양이다.
type AutoChargeHistory interface {
	History(ctx context.Context, userID uuid.UUID) ([]autocharge.HistoryItem, error)
}

// autoChargeHistoryItemBody 는 충전할 일 하나의 응답 모양이다. 까닭은 그만뒀을 때만, 끝난 시각은 끝났을 때만 있다.
type autoChargeHistoryItemBody struct {
	ID         uuid.UUID     `json:"id"`
	ProductID  string        `json:"product_id"`
	Price      int64         `json:"price"`
	Credits    credit.Amount `json:"credits"`
	Status     string        `json:"status"`
	Reason     *string       `json:"reason"`
	TurnedOff  bool          `json:"turned_off"`
	CreatedAt  time.Time     `json:"created_at"`
	FinishedAt *time.Time    `json:"finished_at"`
}

// autoChargeHistoryBody 는 최근 내역의 응답 모양이다.
type autoChargeHistoryBody struct {
	Items []autoChargeHistoryItemBody `json:"items"`
}

// getAutoChargeHistory 는 토큰의 주인의 최근 자동 결제 내역을 돌려주는 핸들러를 만든다. 없으면 빈 목록이다.
func getAutoChargeHistory(history AutoChargeHistory) gin.HandlerFunc {
	return func(c *gin.Context) {
		items, err := history.History(c.Request.Context(), currentUser(c).UserID)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, toAutoChargeHistoryBody(items))
	}
}

// toAutoChargeHistoryBody 는 내역을 응답의 모양으로 바꾼다.
func toAutoChargeHistoryBody(items []autocharge.HistoryItem) autoChargeHistoryBody {
	body := autoChargeHistoryBody{Items: make([]autoChargeHistoryItemBody, 0, len(items))}
	for _, item := range items {
		body.Items = append(body.Items, toAutoChargeHistoryItemBody(item))
	}
	return body
}

// toAutoChargeHistoryItemBody 는 충전할 일 하나를 응답의 모양으로 바꾼다.
func toAutoChargeHistoryItemBody(item autocharge.HistoryItem) autoChargeHistoryItemBody {
	body := autoChargeHistoryItemBody{
		ID: item.ID, ProductID: item.ProductID, Price: item.Price, Credits: item.Credits,
		Status: item.Status, TurnedOff: item.TurnedOff, CreatedAt: item.CreatedAt,
	}
	if item.Reason != "" {
		reason := item.Reason
		body.Reason = &reason
	}
	body.FinishedAt = item.FinishedAt
	return body
}
