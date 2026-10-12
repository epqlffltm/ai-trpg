// billing-server/internal/httpapi/checkout.go

package httpapi

import (
	"bytes"
	_ "embed"
	"html/template"
	"net/http"

	"github.com/gin-gonic/gin"
)

// 토스페이먼츠의 결제위젯으로 크레딧을 사 보는 개발용 화면. 서버를 띄운 PC 의 브라우저에서 연다.
//
//	http://127.0.0.1:8003/dev/checkout
//
// 개발용이다. DEBUG=true 이고 PAYMENT_PROVIDER=toss 일 때만 열린다(config.Settings.CheckoutClientKey).
// 화면은 이 서버의 API(상품, 주문, 승인, 지갑)를 사용자의 access 토큰으로 부른다. 같은 주소에서 부르므로 CORS 가 필요 없다.
// 화면에는 클라이언트 키만 싣는다. 클라이언트 키는 브라우저에 싣도록 만든 공개된 값이다. 시크릿 키는 싣지 않는다.
//
// 흐름: 상품 고르기 → 주문 만들기(POST /orders) → 결제위젯에서 결제 → 토스페이먼츠가 이 화면으로 돌려보낸다
// (?result=success&paymentKey=...&orderId=...&amount=...) → 승인 요청(POST /orders/{id}/confirm) → 잔액 보기.

// CheckoutPath 는 개발용 결제 화면의 주소다. API 가 아니라서 APIPrefix 밖에 둔다.
const CheckoutPath = "/dev/checkout"

// checkoutHTML 은 화면의 틀이다. 서버에 함께 묶여 들어간다(파일을 따로 배포하지 않는다).
//
//go:embed checkout.html
var checkoutHTML string

// checkoutPage 는 틀을 읽은 것이다. html/template 이라 값이 들어가는 자리(스크립트 안의 글자)에 맞게 값을 바꿔 넣는다.
var checkoutPage = template.Must(template.New("checkout").Parse(checkoutHTML))

// checkoutData 는 틀에 채우는 값이다.
type checkoutData struct {
	// ClientKey 는 토스페이먼츠의 클라이언트 키다.
	ClientKey string
	// APIPrefix 는 화면이 부를 API 의 주소다.
	APIPrefix string
}

// checkout 은 개발용 결제 화면을 내주는 핸들러를 만든다.
// 화면의 주소에는 결제 번호가 실려 돌아온다. 캐시에 남기지 않는다. 화면의 스크립트는 읽은 뒤 주소에서 결제 번호를 지운다.
// 다른 사이트로 가는 요청에는 브라우저의 기본값(strict-origin-when-cross-origin)대로 주소의 경로와 쿼리가 실리지 않는다.
func checkout(clientKey string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var page bytes.Buffer
		if err := checkoutPage.Execute(&page, checkoutData{ClientKey: clientKey, APIPrefix: APIPrefix}); err != nil {
			internalError(c, err)
			return
		}
		c.Header("Cache-Control", "no-store")
		c.Data(http.StatusOK, "text/html; charset=utf-8", page.Bytes())
	}
}
