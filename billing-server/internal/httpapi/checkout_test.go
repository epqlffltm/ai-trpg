// billing-server/internal/httpapi/checkout_test.go

package httpapi_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
)

// checkoutKey 는 시험에 쓰는 클라이언트 키다. 실제 키가 아니다.
const checkoutKey = "test_gck_sandbox_0123456789"

func TestCheckoutPageIsClosedWithoutAClientKey(t *testing.T) {
	// 개발 모드에서 토스페이먼츠를 꽂지 않았으면 화면이 없다
	response := send(t, httpapi.Dependencies{}, request{method: http.MethodGet, path: httpapi.CheckoutPath, anonymous: true})

	if response.Code != http.StatusNotFound {
		t.Errorf("상태 코드 = %d, 기대 = 404", response.Code)
	}
}

func TestCheckoutPageCarriesTheClientKey(t *testing.T) {
	// 화면 자체는 토큰 없이 받는다. 화면이 부르는 API 가 토큰을 요구한다
	response := send(t, httpapi.Dependencies{CheckoutClientKey: checkoutKey}, request{
		method: http.MethodGet, path: httpapi.CheckoutPath, anonymous: true,
	})

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d", response.Code)
	}
	if got := response.Header().Get("Content-Type"); got != "text/html; charset=utf-8" {
		t.Errorf("Content-Type = %q", got)
	}
	// 결제 번호가 실린 주소로 돌아오는 화면이다. 캐시에 남기지 않는다
	if got := response.Header().Get("Cache-Control"); got != "no-store" {
		t.Errorf("Cache-Control = %q", got)
	}
	page := body(response)
	for _, want := range []string{
		`const clientKey = "` + checkoutKey + `";`,
		`const api = "` + httpapi.APIPrefix + `";`,
		`<script src="https://js.tosspayments.com/v2/standard"></script>`,
	} {
		if !strings.Contains(page, want) {
			t.Errorf("화면에 %q 가 없다", want)
		}
	}
}

func TestCheckoutPageEscapesWhatItFillsIn(t *testing.T) {
	// 설정이 키의 모양을 막지만, 화면도 값을 스크립트의 글자로만 넣는다. 스크립트를 닫고 새 스크립트를 열 수 없다
	hostile := `x";alert(1);"</script><script>alert(2)</script>`
	response := send(t, httpapi.Dependencies{CheckoutClientKey: hostile}, request{
		method: http.MethodGet, path: httpapi.CheckoutPath, anonymous: true,
	})

	page := body(response)
	if strings.Contains(page, `</script><script>alert(2)`) || strings.Contains(page, `"x";alert(1)`) {
		t.Errorf("값이 바꿔지지 않고 들어갔다")
	}
}

func TestCheckoutPageOffersRefundsThroughTheAPI(t *testing.T) {
	// 청약철회도 다른 클라이언트와 같은 주소를 부른다. 할 수 있는지는 서버가 준 refundable 을 따른다
	response := send(t, httpapi.Dependencies{CheckoutClientKey: checkoutKey}, request{
		method: http.MethodGet, path: httpapi.CheckoutPath, anonymous: true,
	})

	page := body(response)
	for _, want := range []string{
		`id="refund"`, `id="lookup-id"`,
		`"/orders/" + encodeURIComponent(order.id) + "/refund"`,
		`order.refundable || order.status === "refunding"`,
	} {
		if !strings.Contains(page, want) {
			t.Errorf("화면에 %q 가 없다", want)
		}
	}
}
