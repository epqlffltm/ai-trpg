// billing-server/internal/httpapi/prices.go

package httpapi

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// 가격 목록. 게임 서버가 부른다. 사용자는 부를 수 없다(requireService).
//
//	GET /service/prices
//
// 사용자에게는 게임 서버가 로그인한 사람에게만 보여 준다(가격을 아무나 긁어 가지 못하게, 유저 결정 2026-10-17).
// 게임 서버는 받은 목록을 캐싱하고 1분쯤마다 다시 묻는다. 그때 지난 응답의 ETag 를 If-None-Match 에 실으면,
// 바뀐 것이 없을 때 본문 없이 304 로 답한다. 바뀌었으면 새 목록과 새 ETag 를 받고 옛 것은 버린다.
// ETag 는 본문의 해시다. 가격표에 줄을 더할 때뿐 아니라, 예약한 값이 적용 시각을 지나 목록이 바뀔 때도 저절로 바뀐다.

// PriceLister 는 가격 목록을 읽는 것의 모양이다. *pricing.Service 가 이 모양이다.
type PriceLister interface {
	List(ctx context.Context) ([]pricing.Listing, error)
}

// priceListBody 는 가격 목록의 응답 모양이다.
type priceListBody struct {
	Prices []priceBody `json:"prices"`
}

// priceBody 는 가격 목록의 이름 하나다.
type priceBody struct {
	// Code 는 가격표의 이름이다(narration.claude-sonnet-5-5.i0.o0). 게임 서버의 모델 목록과 이 이름으로 맞춘다.
	Code string `json:"code"`
	// Credits 는 지금 1번에 받는 값이다. 지금 팔지 않으면(예약만 있으면) null 이다.
	Credits *credit.Amount `json:"credits"`
	// Since 는 지금 값이 적용되기 시작한 시각이다. Credits 가 null 이면 null 이다.
	Since *time.Time `json:"since"`
	// Tier 는 지금의 등급이다(standard, premium). premium 은 골드로만 낸다. Credits 가 null 이면 null 이다.
	// 결제에 쓰는 등급은 이것이 기준이다. 게임 서버의 모델 목록의 분류와 다르면 게임 서버가 알린다.
	Tier *pricing.Tier `json:"tier"`
	// Next 는 다음에 바뀔 값이다. 예약이 없으면 null 이다.
	Next *nextPriceBody `json:"next"`
}

// nextPriceBody 는 다음에 바뀔 값이다.
type nextPriceBody struct {
	// Credits 는 바뀔 값이다. null 이면 이 시각부터 판매를 멈춘다.
	Credits *credit.Amount `json:"credits"`
	// Tier 는 이 시각부터의 등급이다. Credits 가 null 이면 null 이다.
	Tier        *pricing.Tier `json:"tier"`
	EffectiveAt time.Time     `json:"effective_at"`
}

// listPrices 는 가격 목록의 핸들러를 만든다. 요청의 If-None-Match 가 지금 목록의 ETag 와 같으면 304 다.
func listPrices(prices PriceLister) gin.HandlerFunc {
	return func(c *gin.Context) {
		listings, err := prices.List(c.Request.Context())
		if err != nil {
			internalError(c, err)
			return
		}
		body, err := json.Marshal(toPriceList(listings))
		if err != nil {
			internalError(c, err)
			return
		}
		tag := entityTag(body)
		// 캐시는 둬도 되지만 쓰기 전에 늘 다시 물어보라는 뜻이다. 묻는 값은 304 로 싸다
		c.Header("Cache-Control", "no-cache")
		c.Header("ETag", tag)
		if matchesTag(c.GetHeader("If-None-Match"), tag) {
			c.Status(http.StatusNotModified)
			return
		}
		c.Data(http.StatusOK, "application/json; charset=utf-8", body)
	}
}

// toPriceList 는 가격 목록을 응답의 모양으로 바꾼다. 줄이 없어도 prices 는 빈 배열이다(null 이 아니다).
func toPriceList(listings []pricing.Listing) priceListBody {
	prices := make([]priceBody, 0, len(listings))
	for _, listing := range listings {
		prices = append(prices, toPriceBody(listing))
	}
	return priceListBody{Prices: prices}
}

// toPriceBody 는 목록의 이름 하나를 응답의 모양으로 바꾼다.
func toPriceBody(listing pricing.Listing) priceBody {
	body := priceBody{Code: listing.Code}
	if listing.Current != nil {
		credits, since, tier := listing.Current.Credits, listing.Current.Since, listing.Current.Tier
		body.Credits, body.Since, body.Tier = &credits, &since, &tier
	}
	if listing.Next != nil {
		next := nextPriceBody{EffectiveAt: listing.Next.EffectiveAt}
		if listing.Next.OnSale {
			credits, tier := listing.Next.Credits, listing.Next.Tier
			next.Credits, next.Tier = &credits, &tier
		}
		body.Next = &next
	}
	return body
}

// entityTag 는 본문의 ETag 를 만든다. 본문의 SHA-256 앞 16바이트를 16진수로 적어 따옴표로 감싼다.
func entityTag(body []byte) string {
	sum := sha256.Sum256(body)
	return `"` + hex.EncodeToString(sum[:16]) + `"`
}

// matchesTag 는 If-None-Match 머리말에 그 ETag 가 있는지 본다. 쉼표로 여럿을 적거나 약한 비교(W/)를 붙여도 받는다.
func matchesTag(header string, tag string) bool {
	for _, candidate := range strings.Split(header, ",") {
		candidate = strings.TrimPrefix(strings.TrimSpace(candidate), "W/")
		if candidate == tag || candidate == "*" {
			return true
		}
	}
	return false
}
