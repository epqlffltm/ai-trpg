// billing-server/internal/order/export_test.go

// 테스트에만 여는 것. 이 파일은 테스트를 빌드할 때만 들어간다.
package order

// ProviderFor 는 주문의 길에 맞는 결제 대행사를 고르는 providerFor 다. 지금 DB 에는 웹 말고 다른 길의 주문을 적을 수 없어서
// 맞는 결제 대행사가 없는 경우를 서비스를 거쳐 만들 수 없다. 고르는 규칙만 따로 확인한다.
var ProviderFor = (*Service).providerFor
