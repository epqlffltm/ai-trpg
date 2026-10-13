// billing-server/internal/httpapi/checkout.go

package httpapi

import (
	"bytes"
	_ "embed"
	"html/template"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

// 토스페이먼츠로 크레딧을 사 보는 개발용 화면. 서버를 띄운 PC 의 브라우저에서 연다.
// 클라이언트 키의 종류에 따라 결제를 띄우는 방법이 다르다.
//   - 결제위젯 키(test_gck_): 결제위젯(결제 수단과 약관을 화면에 그린다). 결제 수단은 개발자센터의 결제 UI 설정이 정한다
//   - API 개별 연동 키(test_ck_): 결제창. 결제 수단을 카드(간편결제 포함)로 정해 연다. 가상계좌를 고를 수 없다
//
//	http://127.0.0.1:8003/dev/checkout
//
// 개발용이다. DEBUG=true 이고 PAYMENT_PROVIDER=toss 일 때만 열린다(config.Settings.CheckoutClientKey).
// 화면은 이 서버의 API(상품, 주문, 승인, 지갑)를 사용자의 access 토큰으로 부른다. 같은 주소에서 부르므로 CORS 가 필요 없다.
// 화면에는 클라이언트 키만 싣는다. 클라이언트 키는 브라우저에 싣도록 만든 공개된 값이다. 시크릿 키는 싣지 않는다.
//
// 흐름: 상품 고르기 → 주문 만들기(POST /orders) → 결제위젯이나 결제창에서 결제 → 토스페이먼츠가 이 화면으로 돌려보낸다
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
	// Widget 이 true 면 결제위젯, false 면 결제창으로 결제한다. 클라이언트 키의 종류로 정한다(checkoutUsesWidget).
	Widget bool
}

// checkoutUsesWidget 은 그 클라이언트 키로 결제위젯을 쓰는지 본다. 결제위젯 키(test_gck_, live_gck_)면 true 다.
// 결제위젯은 결제위젯 키로만, 결제창은 API 개별 연동 키로만 열린다.
func checkoutUsesWidget(clientKey string) bool {
	return strings.Contains(clientKey, "_gck_")
}

// checkout 은 개발용 결제 화면을 내주는 핸들러를 만든다.
// 화면의 주소에는 결제 번호가 실려 돌아온다. 캐시에 남기지 않는다. 화면의 스크립트는 읽은 뒤 주소에서 결제 번호를 지운다.
// 다른 사이트로 가는 요청에는 브라우저의 기본값(strict-origin-when-cross-origin)대로 주소의 경로와 쿼리가 실리지 않는다.
func checkout(clientKey string) gin.HandlerFunc {
	return func(c *gin.Context) {
		var page bytes.Buffer
		if err := checkoutPage.Execute(&page, checkoutData{ClientKey: clientKey, APIPrefix: APIPrefix, Widget: checkoutUsesWidget(clientKey)}); err != nil {
			internalError(c, err)
			return
		}
		c.Header("Cache-Control", "no-store")
		c.Data(http.StatusOK, "text/html; charset=utf-8", page.Bytes())
	}
}
