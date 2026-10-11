// billing-server/internal/catalog/catalog.go

// Package catalog 는 파는 상품의 목록이다. 무엇을 얼마에 파는지를 이 파일 하나가 정한다.
//
// 목록을 DB 가 아니라 코드에 둔다. 가격을 고치는 관리 화면이 아직 없어서 DB 에 둘 까닭이 없다.
// 가격을 바꾸려면 이 파일을 고쳐 배포한다. 주문은 만들 때의 값과 크레딧을 스스로 적어 두므로,
// 여기를 고쳐도 지난 주문은 바뀌지 않는다.
//
// 클라이언트는 상품의 번호만 보낸다. 값과 크레딧의 양은 서버가 이 목록에서 찾는다.
// 클라이언트가 보낸 금액을 믿지 않는다.
package catalog

import "github.com/epqlffltm/ai-trpg/billing-server/internal/credit"

// Product 는 파는 상품 하나다.
type Product struct {
	// ID 는 상품의 번호다. 주문에 그대로 적히므로 한 번 쓴 번호를 다른 상품에 다시 쓰지 않는다.
	ID string
	// Name 은 화면에 보여 줄 이름이다.
	Name string
	// Price 는 값이다. 원(KRW)이다.
	Price int64
	// Credits 는 사면 들어오는 산 크레딧의 양이다.
	Credits credit.Amount
}

// products 는 파는 상품 전부다. 1원에 1크레딧이다. 많이 산다고 더 주지 않는다.
var products = []Product{
	{ID: "credits-1000", Name: "크레딧 1,000", Price: 1_000, Credits: 1_000},
	{ID: "credits-5000", Name: "크레딧 5,000", Price: 5_000, Credits: 5_000},
	{ID: "credits-10000", Name: "크레딧 10,000", Price: 10_000, Credits: 10_000},
	{ID: "credits-30000", Name: "크레딧 30,000", Price: 30_000, Credits: 30_000},
}

// All 은 파는 상품을 싼 것부터 돌려준다. 돌려받은 목록을 고쳐도 원래 목록은 바뀌지 않는다.
func All() []Product {
	return append([]Product(nil), products...)
}

// Find 는 번호로 상품을 찾는다. 없으면 두 번째 값이 false 다.
func Find(id string) (Product, bool) {
	for _, product := range products {
		if product.ID == id {
			return product, true
		}
	}
	return Product{}, false
}
