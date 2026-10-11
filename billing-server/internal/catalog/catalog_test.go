// billing-server/internal/catalog/catalog_test.go

package catalog_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestEveryProductCanBeSold(t *testing.T) {
	seen := map[string]bool{}
	var previous int64
	for _, product := range catalog.All() {
		if product.ID == "" || product.Name == "" {
			t.Errorf("번호나 이름이 빈 상품이 있다: %+v", product)
		}
		if seen[product.ID] {
			t.Errorf("번호 %s 가 둘이다", product.ID)
		}
		seen[product.ID] = true
		// DB 의 CHECK 와 지갑이 받는 범위 안이어야 주문하고 충전할 수 있다
		if product.Price <= 0 || product.Credits <= 0 || product.Credits > wallet.MaxAmount {
			t.Errorf("%s 의 값이나 크레딧이 범위를 벗어났다: %+v", product.ID, product)
		}
		if product.Price <= previous {
			t.Errorf("%s 가 싼 것부터 놓여 있지 않다", product.ID)
		}
		previous = product.Price
	}
	if len(seen) == 0 {
		t.Error("파는 상품이 없다")
	}
}

func TestOneWonBuysOneCredit(t *testing.T) {
	for _, product := range catalog.All() {
		if int64(product.Credits) != product.Price {
			t.Errorf("%s: %d원에 %d크레딧이다. 1원에 1크레딧이어야 한다", product.ID, product.Price, product.Credits)
		}
	}
}

func TestFindReturnsTheProduct(t *testing.T) {
	product, ok := catalog.Find("credits-5000")
	if !ok || product.Price != 5_000 || product.Credits != 5_000 {
		t.Errorf("Find = %+v, %v", product, ok)
	}
}

func TestFindRejectsUnknownIDs(t *testing.T) {
	for _, id := range []string{"", "credits-1", "CREDITS-1000", " credits-1000", "credits-1000 "} {
		if product, ok := catalog.Find(id); ok {
			t.Errorf("Find(%q) = %+v. 없어야 한다", id, product)
		}
	}
}

func TestAllReturnsACopy(t *testing.T) {
	// 받은 목록을 고쳐도 파는 값이 바뀌지 않는다
	list := catalog.All()
	list[0].Price = 1

	if product, _ := catalog.Find(list[0].ID); product.Price == 1 {
		t.Error("돌려받은 목록을 고쳤더니 원래 목록이 바뀌었다")
	}
}
