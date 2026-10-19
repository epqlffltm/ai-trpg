// billing-server/internal/httpapi/router.go

// Package httpapi 는 결제 서버의 HTTP 주소들을 만든다. 요청을 받아 응답의 모양으로 바꾸는 일만 한다.
//
// 라우터는 전역 변수로 두지 않고 함수(NewRouter)로 만든다. 필요한 것(DB, 검증기, 지갑, 주문)을 밖에서 받으므로,
// 테스트가 가짜를 넣어 라우터를 여러 개 만들 수 있다.
package httpapi

import (
	"log/slog"
	"time"

	"github.com/gin-gonic/gin"
	"go.opentelemetry.io/otel/metric"

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
	// Eligibility 는 인증 서버가 알려 준 결제 자격을 받아 적는다.
	Eligibility EligibilityRecorder
	// Welcome 은 환영 크레딧을 준다. WelcomeCredits 는 그 양이다. 0 이면 주지 않는다.
	Welcome        WelcomeGranter
	WelcomeCredits credit.Amount
	// Attendance 는 출석과 보물 상자다(#339). 넣지 않으면 그 주소들을 열지 않는다.
	Attendance AttendanceService
	// Orders 는 주문을 만들고 치른다. 서버는 결제 자격으로 감싼 것(eligibility.Guard)을 넣는다.
	Orders OrderService
	// Notifier 는 결제 대행사의 알림을 처리한다.
	Notifier PaymentNotifier
	// WebhookSecret 은 결제 대행사의 알림에 붙은 서명을 확인하는 비밀이다.
	WebhookSecret string
	// TossWebhook 이 true 면 토스페이먼츠의 알림 주소(TossWebhookPath)를 연다. 알림은 Notifier 가 처리한다.
	TossWebhook bool
	// Holds 는 홀드를 걸고, 확정하고, 돌려주고, 연장한다. 게임 서버가 부른다.
	Holds HoldService
	// Prices 는 가격 목록을 읽는다. 게임 서버가 부른다.
	Prices PriceLister
	// GameServerSecret 은 게임 서버가 보낸 요청의 서명을 확인하는 비밀이다.
	GameServerSecret string
	// AuthServerSecret 은 인증 서버가 보낸 요청의 서명을 확인하는 비밀이다.
	AuthServerSecret string
	// CheckoutClientKey 는 개발용 결제 화면(CheckoutPath)에 실을 토스페이먼츠의 클라이언트 키다.
	// 비어 있으면 그 화면을 열지 않는다.
	CheckoutClientKey string
	// Now 는 지금 시각을 돌려준다. 서명이 방금 것인지 볼 때 쓴다.
	Now func() time.Time
	// Logger 는 요청의 기록을 남기는 곳이다. 넣지 않으면 프로세스의 기본 로거(slog.Default)다.
	Logger *slog.Logger
	// RequestTimeout 은 요청 하나를 처리하는 가장 긴 시간이다. 넣지 않으면 RequestTimeout(10초)이다. 테스트가 짧게 줄여 쓴다.
	RequestTimeout time.Duration
	// Meter 는 요청과 DB 의 상태를 세는 계측기를 만든다(metrics.go). 넣지 않으면 세지 않는다.
	Meter metric.Meter
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

// loggerOf 는 라우터가 쓸 로거를 고른다. 넣어 준 것이 없으면 프로세스의 기본 로거다.
func loggerOf(deps Dependencies) *slog.Logger {
	if deps.Logger != nil {
		return deps.Logger
	}
	return slog.Default()
}

// NewRouter 는 주소들이 붙은 라우터를 만들어 돌려준다.
func NewRouter(deps Dependencies) *gin.Engine {
	// gin.Default 를 쓰지 않고 미들웨어를 직접 고른다. 무엇이 붙었는지 여기서 보인다
	router := gin.New()
	logger := loggerOf(deps)
	meters := newRouterMetrics(deps.Meter, logger)
	// 요청을 세고 걸린 시간을 잰다. 패닉으로 끝난 요청(500)과 마감에 걸린 요청도 센다
	router.Use(measureRequests(meters.http))
	// 요청마다 식별자를 걸고, 끝나면 공통 규격의 한 줄을 남긴다. 요청의 본문과 머리말은 적지 않는다.
	// 가장 먼저 붙인다. 뒤에 오는 것들의 로그에 식별자가 붙는다
	router.Use(requestLogging(logger))
	// 처리 중에 패닉이 나도 서버가 죽지 않고 500 으로 답한다
	router.Use(recoverPanics(logger))
	// 요청 하나를 처리하는 시간에 마감을 둔다. 연결 풀을 기다리는 시간도 여기에 든다(deadline.go)
	router.Use(requestDeadline(requestTimeoutOf(deps)))

	// 상태를 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다.
	// HEAD 도 받는다. 같은 핸들러가 돌고, 본문은 net/http 가 버린다. HEAD 로 확인하는 도구가 있다
	ready := readiness(deps.DB, logger, meters.db)
	router.GET(HealthPath, health)
	router.HEAD(HealthPath, health)
	router.GET(ReadyPath, ready)
	router.HEAD(ReadyPath, ready)

	// 개발용 결제 화면. 로그인 묶음 밖에 둔다. 화면 자체는 누구나 받지만, 화면이 부르는 API 는 토큰이 있어야 한다
	if deps.CheckoutClientKey != "" {
		router.GET(CheckoutPath, checkout(deps.CheckoutClientKey))
	}

	// 이 아래의 주소는 모두 로그인이 필요하다. 주소마다 붙이지 않고 묶음에 한 번 붙인다.
	// 새 주소를 더하면서 검증을 빠뜨리는 일이 없다
	api := router.Group(APIPrefix, requireUser(deps.Verifier))
	api.GET("/me", me)
	api.GET("/wallet", getWallet(deps.Wallet))
	api.GET("/wallet/entries", listEntries(deps.Wallet))
	api.GET("/products", listProducts)
	api.POST("/orders", createOrder(deps.Orders))
	api.GET("/orders", listOrders(deps.Orders))
	api.GET("/orders/:id", getOrder(deps.Orders))
	api.POST("/orders/:id/confirm", confirmOrder(deps.Orders))
	api.POST("/orders/:id/refund", refundOrder(deps.Orders))
	if deps.Attendance != nil {
		api.GET("/attendance", getAttendance(deps.Attendance))
		api.POST("/attendance", claimAttendance(deps.Attendance))
		// 하루 양과 보물 상자의 확률을 공개한다. 로그인 묶음 밖에 둔다. 가입하기 전에도 볼 수 있다
		router.GET(APIPrefix+"/attendance/rewards", attendanceRewards(deps.Attendance))
	}

	// 결제 대행사가 부르는 주소다. 로그인 묶음 밖에 둔다. 토큰 대신 본문의 서명을 확인한다
	router.POST(APIPrefix+"/webhooks/payment", paymentWebhook(deps.Notifier, deps.WebhookSecret, deps.Now))
	// 토스페이먼츠의 알림. 서명이 없다. 주문 번호와 결제 번호만 읽고 결과는 토스페이먼츠에 다시 묻는다
	if deps.TossWebhook {
		router.POST(TossWebhookPath, tossWebhook(deps.Notifier))
	}

	// 우리 서버들이 부르는 주소들이다. 로그인 묶음 밖에 둔다. 사용자의 토큰이 아니라 요청의 서명을 확인한다.
	// 사용자의 토큰으로는 들어오지 못한다. "이 사용자의 크레딧을 빼라"를 사용자가 직접 부를 수 없다.
	// 서버마다 비밀이 다르고, 부를 수 있는 주소도 다르다. 게임 서버의 비밀로 환영 크레딧을 줄 수 없다
	service := router.Group(APIPrefix + "/service")

	game := service.Group("", requireService(GameServer, deps.GameServerSecret, deps.Now))
	game.POST("/holds", placeHold(deps.Holds))
	game.POST("/holds/capture", captureHold(deps.Holds))
	game.POST("/holds/release", releaseHold(deps.Holds))
	game.POST("/holds/extend", extendHold(deps.Holds))
	game.GET("/prices", listPrices(deps.Prices))

	authServer := service.Group("", requireService(AuthServer, deps.AuthServerSecret, deps.Now))
	authServer.POST("/grants/welcome", grantWelcome(deps.Welcome, deps.WelcomeCredits))
	authServer.POST("/eligibility", recordEligibility(deps.Eligibility))

	return router
}
