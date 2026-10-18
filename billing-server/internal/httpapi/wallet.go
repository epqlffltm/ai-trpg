// billing-server/internal/httpapi/wallet.go

package httpapi

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 지갑을 읽는 주소들. 누구의 지갑인지는 토큰에서만 정한다. 주소나 본문으로 사용자 번호를 받지 않는다.
// 그래서 남의 지갑을 읽는 요청은 만들 수조차 없다.

// DefaultPageSize 는 원장을 읽을 때 limit 을 적지 않으면 돌려주는 줄 수다.
const DefaultPageSize = 20

// WalletReader 는 지갑을 읽는 것의 모양이다. *wallet.Service 가 이 모양이다.
// 읽는 것만 받는다. 이 주소들이 실수로라도 크레딧을 바꿀 수 없다.
type WalletReader interface {
	Balance(ctx context.Context, userID uuid.UUID) (wallet.Balance, error)
	Entries(ctx context.Context, userID uuid.UUID, before int64, limit int) (wallet.Page, error)
}

// walletBody 는 잔액 응답의 모양이다. 양은 숫자가 아니라 글자로 나간다(internal/credit).
type walletBody struct {
	// Paid 는 산 크레딧, Free 는 아직 사라지지 않은 무료 크레딧, Total 은 둘의 합이다.
	Paid  credit.Amount `json:"paid"`
	Free  credit.Amount `json:"free"`
	Total credit.Amount `json:"total"`
	// NextExpiry 는 무료 크레딧 중 가장 먼저 사라지는 것이다. 무료 크레딧이 없으면 null 이다(#430).
	NextExpiry *expiryBody `json:"next_expiry"`
}

// expiryBody 는 같은 시각에 사라지는 무료 크레딧의 응답 모양이다.
type expiryBody struct {
	Amount    credit.Amount `json:"amount"`
	ExpiresAt time.Time     `json:"expires_at"`
}

// entryBody 는 원장 한 줄의 응답 모양이다.
type entryBody struct {
	// ID 는 글자로 나간다. 64비트 정수는 자바스크립트의 숫자에 다 담기지 않는다.
	ID          string        `json:"id"`
	OperationID uuid.UUID     `json:"operation_id"`
	Kind        wallet.Kind   `json:"kind"`
	Reason      wallet.Reason `json:"reason"`
	Amount      credit.Amount `json:"amount"`
	// OrderID 는 이 크레딧이 들어온 주문이다. 주문으로 들어온 줄이 아니면 null 이다.
	OrderID *uuid.UUID `json:"order_id"`
	// HoldID 는 이 줄을 남긴 홀드다. 빠진 줄(hold)과 돌아온 줄(release)이 같은 번호를 갖는다. 아니면 null 이다.
	HoldID    *uuid.UUID `json:"hold_id"`
	CreatedAt time.Time  `json:"created_at"`
}

// entriesBody 는 원장 응답의 모양이다.
type entriesBody struct {
	Entries []entryBody `json:"entries"`
	// NextBefore 는 다음 쪽을 읽을 때 before 에 넣을 값이다. 더 읽을 것이 없으면 null 이다.
	NextBefore *string `json:"next_before"`
}

// getWallet 은 토큰의 주인이 지금 쓸 수 있는 크레딧을 돌려주는 핸들러를 만든다.
func getWallet(reader WalletReader) gin.HandlerFunc {
	return func(c *gin.Context) {
		balance, err := reader.Balance(c.Request.Context(), currentUser(c).UserID)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, toWalletBody(balance))
	}
}

// toWalletBody 는 잔액을 응답의 모양으로 바꾼다. 시각은 UTC 로 나간다.
func toWalletBody(balance wallet.Balance) walletBody {
	body := walletBody{Paid: balance.Paid, Free: balance.Free, Total: balance.Total()}
	if next := balance.NextExpiry; next != nil {
		body.NextExpiry = &expiryBody{Amount: next.Amount, ExpiresAt: next.At.UTC()}
	}
	return body
}

// listEntries 는 토큰의 주인의 원장을 최근 것부터 돌려주는 핸들러를 만든다.
func listEntries(reader WalletReader) gin.HandlerFunc {
	return func(c *gin.Context) {
		before, limit, ok := pageQuery(c)
		if !ok {
			badRequest(c, "before 는 1 이상의 정수, limit 은 1 부터 "+strconv.Itoa(wallet.MaxPageSize)+" 사이의 정수여야 합니다.")
			return
		}
		page, err := reader.Entries(c.Request.Context(), currentUser(c).UserID, before, limit)
		if err != nil {
			internalError(c, err)
			return
		}
		c.JSON(http.StatusOK, toEntriesBody(page))
	}
}

// pageQuery 는 주소의 before 와 limit 을 읽는다. 적지 않으면 가장 최근 줄부터 DefaultPageSize 줄이다.
// 받을 수 없는 값이면 false 다.
func pageQuery(c *gin.Context) (before int64, limit int, ok bool) {
	before, limit = wallet.FirstPage, DefaultPageSize
	if text, given := c.GetQuery("before"); given {
		value, err := strconv.ParseInt(text, 10, 64)
		if err != nil || value < 1 {
			return 0, 0, false
		}
		before = value
	}
	if text, given := c.GetQuery("limit"); given {
		value, err := strconv.Atoi(text)
		if err != nil || value < 1 || value > wallet.MaxPageSize {
			return 0, 0, false
		}
		limit = value
	}
	return before, limit, true
}

// toEntriesBody 는 원장의 한 쪽을 응답의 모양으로 바꾼다.
func toEntriesBody(page wallet.Page) entriesBody {
	entries := make([]entryBody, 0, len(page.Entries))
	for _, entry := range page.Entries {
		entries = append(entries, entryBody{
			ID:          strconv.FormatInt(entry.ID, 10),
			OperationID: entry.OperationID,
			Kind:        entry.Kind,
			Reason:      entry.Reason,
			Amount:      entry.Amount,
			OrderID:     entry.OrderID,
			HoldID:      entry.HoldID,
			CreatedAt:   entry.CreatedAt,
		})
	}
	return entriesBody{Entries: entries, NextBefore: nextBefore(page.NextBefore)}
}

// nextBefore 는 다음 쪽의 시작 값을 글자로 바꾼다. 다음 쪽이 없으면(0) nil 이다.
func nextBefore(value int64) *string {
	if value == 0 {
		return nil
	}
	text := strconv.FormatInt(value, 10)
	return &text
}
