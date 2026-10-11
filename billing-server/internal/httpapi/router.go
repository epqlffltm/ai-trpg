// billing-server/internal/httpapi/router.go

// Package httpapi 는 결제 서버의 HTTP 주소들을 만든다. 요청을 받아 응답의 모양으로 바꾸는 일만 한다.
//
// 라우터는 전역 변수로 두지 않고 함수(NewRouter)로 만든다. 필요한 것(DB, 검증기, 지갑, 주문)을 밖에서 받으므로,
// 테스트가 가짜를 넣어 라우터를 여러 개 만들 수 있다.
package httpapi

import (
	"time"

	"github.com/gin-gonic/gin"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
)

// APIPrefix 는 이 서버의 API 가 놓이는 주소다. 인증 서버는 /api/v1/auth, 게임 서버는 /api/v1/game 을 쓴다.
const APIPrefix = "/api/v1/billing"

// Dependencies 는 라우터가 요청을 처리하는 데 쓰는 것들이다. 서버가 뜰 때 한 번 만들어 넘긴다.
type Dependencies struct {
	// DB 는 준비 상태를 확인할 때 살아 있는지 물어볼 대상이다.
	DB database.Pinger
	// Verifier 는 요청의 access 토큰을 검증한다.
	Verifier TokenVerifier
	// Wallet 은 지갑을 읽는다.
	Wallet WalletReader
	// Welcome 은 환영 크레딧을 준다. WelcomeCredits 는 그 양이다. 0 이면 주지 않는다.
	Welcome        WelcomeGranter
	WelcomeCredits credit.Amount
	// Orders 는 주문을 만들고 치른다.
	Orders OrderService
	// Notifier 는 결제 대행사의 알림을 처리한다.
	Notifier PaymentNotifier
	// WebhookSecret 은 결제 대행사의 알림에 붙은 서명을 확인하는 비밀이다.
	WebhookSecret string
	// Now 는 지금 시각을 돌려준다. 알림의 서명이 방금 것인지 볼 때 쓴다.
	Now func() time.Time
}

// SetMode 는 gin 의 동작 방식을 정한다. debug 가 아니면 등록한 주소 목록 같은 개발용 출력을 끈다.
// gin 은 이것을 프로세스 전체의 설정으로 둔다. 그래서 라우터를 만들 때가 아니라 서버가 뜰 때 한 번 부른다.
func SetMode(debug bool) {
	if debug {
		gin.SetMode(gin.DebugMode)
		return
	}
	gin.SetMode(gin.ReleaseMode)
}

// NewRouter 는 주소들이 붙은 라우터를 만들어 돌려준다.
func NewRouter(deps Dependencies) *gin.Engine {
	// gin.Default 를 쓰지 않고 미들웨어를 직접 고른다. 무엇이 붙었는지 여기서 보인다
	router := gin.New()
	// 처리 중에 패닉이 나도 서버가 죽지 않고 500 으로 답한다
	router.Use(gin.Recovery())
	// 요청마다 한 줄씩 기록한다(시각, 상태 코드, 걸린 시간, 주소). 요청의 본문과 머리말은 적지 않는다
	router.Use(gin.Logger())

	// 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
	router.GET("/health", health)
	router.GET("/health/ready", readiness(deps.DB))

	// 이 아래의 주소는 모두 로그인이 필요하다. 주소마다 붙이지 않고 묶음에 한 번 붙인다.
	// 새 주소를 더하면서 검증을 빠뜨리는 일이 없다
	api := router.Group(APIPrefix, requireUser(deps.Verifier))
	api.GET("/me", me)
	api.GET("/wallet", getWallet(deps.Wallet))
	api.GET("/wallet/entries", listEntries(deps.Wallet))
	api.POST("/wallet/welcome", claimWelcome(deps.Welcome, deps.WelcomeCredits))
	api.GET("/products", listProducts)
	api.POST("/orders", createOrder(deps.Orders))
	api.GET("/orders/:id", getOrder(deps.Orders))
	api.POST("/orders/:id/confirm", confirmOrder(deps.Orders))

	// 결제 대행사가 부르는 주소다. 로그인 묶음 밖에 둔다. 토큰 대신 본문의 서명을 확인한다
	router.POST(APIPrefix+"/webhooks/payment", paymentWebhook(deps.Notifier, deps.WebhookSecret, deps.Now))

	return router
}
