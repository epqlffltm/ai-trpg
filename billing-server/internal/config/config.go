// billing-server/internal/config/config.go

// Package config 는 결제 서버의 설정을 환경 변수에서 읽는다.
//
// 값을 어디서 읽을지는 밖에서 받는다(Lookup). 실제 서버는 os.LookupEnv 를 넘기고,
// 테스트는 맵을 넘긴다. 그래서 테스트가 개발자의 .env 나 환경 변수에 흔들리지 않는다.
//
// 잘못된 설정이면 서버가 뜨기 전에 오류로 끝난다. 오류에는 변수의 이름만 싣고 값은 싣지 않는다.
// DATABASE_URL 에는 비밀번호가 들어 있다.
package config

import (
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 적지 않았을 때의 값들.
const (
	// DefaultHost 는 이 PC 에서만 접속할 수 있는 주소다. 같은 네트워크의 다른 기기에는 열지 않는다.
	DefaultHost = "127.0.0.1"
	// DefaultPort 는 결제 서버의 포트다. 인증 서버는 8000, 게임 서버는 8001, 게시판 서버는 8002 를 쓴다.
	DefaultPort = 8003
	// DefaultSchema 는 결제 서버의 테이블이 놓이는 스키마다.
	DefaultSchema = "billing"
	// DefaultJWTIssuer 는 토큰을 발급한 서버의 이름(iss)이다. 인증 서버의 JWT_ISSUER 와 같아야 한다.
	DefaultJWTIssuer = "ai-trpg-auth"
	// DefaultJWTAudience 는 이 서버의 이름이다. 토큰의 대상(aud)에 이 이름이 있어야 받는다.
	// 인증 서버의 JWT_AUDIENCE 목록에 이 이름이 들어 있어야 한다.
	DefaultJWTAudience = "ai-trpg-billing"
	// DefaultSpendFreeFirst 는 크레딧을 쓸 때 무료 크레딧부터 쓰는지다.
	// 무료 크레딧은 기한이 지나면 사라지므로, 먼저 써야 사용자가 잃는 것이 적다.
	DefaultSpendFreeFirst = true
	// DefaultFreeCreditTTL 은 무료 크레딧(실버)이 지급된 뒤 사라질 때까지의 시간이다. 30일이다(#338, 유저 결정 2026-10-17).
	// 환영 크레딧, 출석 보상 모두 같다. 바꿔도 이미 지급한 것의 기한은 그대로다(지급마다 기한을 적어 둔다).
	DefaultFreeCreditTTL = 30 * 24 * time.Hour
	// DefaultAppEnvironment 는 배포 환경의 이름이다. 로그의 environment 칸에 적힌다.
	DefaultAppEnvironment = "development"
	// DefaultAppVersion 은 배포한 코드의 버전이다. 로그의 version 칸에 적힌다. 운영에서는 git SHA 를 넣는다.
	DefaultAppVersion = "dev"
	// DefaultLogLevel 은 남기는 로그의 가장 낮은 수준이다.
	DefaultLogLevel = "info"
	// MinFreeCreditTTL 은 FREE_CREDIT_TTL 로 받는 가장 짧은 시간이다.
	// DB 는 시각을 백만분의 1초까지만 적는다. 그보다 짧으면 지급한 순간과 사라지는 순간이 같아진다.
	MinFreeCreditTTL = time.Second
	// DefaultHoldTTL 은 홀드를 걸거나 연장한 뒤 만료될 때까지의 시간이다. 하루다.
	// 부르는 쪽(게임 서버)이 그 안에 확정하거나 연장하지 않으면 정리 작업이 돌려준다.
	DefaultHoldTTL = 24 * time.Hour
	// DefaultChatHoldTTL 은 chat 서버가 건 홀드의 만료까지의 시간이다. 10분이다.
	// 말 한 번(길게 쓰는 답이어도 몇 분)보다 넉넉하고, chat 서버가 죽었을 때 크레딧이 오래 묶이지 않는다
	DefaultChatHoldTTL = 10 * time.Minute
	// DefaultOrderTTL 은 주문을 만든 뒤 만료될 때까지의 시간이다. 하루다. Stripe 의 결제창(Checkout)과 같은 기본값이다.
	DefaultOrderTTL = 24 * time.Hour
	// MinExpiryTTL 은 HOLD_TTL, CHAT_HOLD_TTL, ORDER_TTL 로 받는 가장 짧은 시간이다.
	// 정리 작업은 몇십 초마다 돈다. 그보다 짧으면 만료가 정리 작업의 간격에 묻힌다.
	MinExpiryTTL = time.Minute
	// DefaultWelcomeCredits 는 사용자가 한 번 받는 환영 크레딧(무료 크레딧)의 양이다. 가장 싼 상품과 같은 양이다.
	DefaultWelcomeCredits credit.Amount = 1_000
	// MaxWelcomeCredits 는 WELCOME_CREDITS 로 받는 가장 큰 양이다. 0 을 몇 개 더 붙인 실수를 막는다.
	MaxWelcomeCredits credit.Amount = 1_000_000
	// MinServiceSecretLength 는 GAME_SERVER_SECRET 의 가장 짧은 길이다.
	MinServiceSecretLength = 32
	// MinWebhookSecretLength 는 PG_WEBHOOK_SECRET 의 가장 짧은 길이다. 짧은 비밀은 서명을 꾸며 내기 쉽다.
	MinWebhookSecretLength = 32
	// ProviderFake 는 정해 둔 대로 답하는 가짜 결제 대행사다. PAYMENT_PROVIDER 의 기본값이다.
	ProviderFake = "fake"
	// ProviderToss 는 토스페이먼츠의 테스트 모드다. TOSS_SECRET_KEY 와 TOSS_CLIENT_KEY 가 있어야 한다.
	ProviderToss = "toss"
	// ProductionEnvironment 는 운영의 APP_ENVIRONMENT 다. 여기서는 가짜 결제 대행사로 뜨지 않는다(#153).
	ProductionEnvironment = "production"
)

// ErrFakeInProduction 은 운영에서 가짜 결제 대행사를 고른 설정이다. 가짜는 누구나 fake_ok_ 로 크레딧을 얻게 한다.
var ErrFakeInProduction = errors.New("APP_ENVIRONMENT=production 에서는 PAYMENT_PROVIDER=fake 를 쓸 수 없습니다. " +
	"가짜 결제 대행사는 결제 번호의 앞머리만으로 승인합니다. PAYMENT_PROVIDER=toss 와 테스트 키를 적어 주세요")

// schemaPattern 은 스키마 이름으로 받는 모양이다. 소문자, 숫자, 밑줄만 받는다.
// 이름이 접속 설정(search_path)에 그대로 들어가므로 다른 글자를 받지 않는다.
var schemaPattern = regexp.MustCompile(`^[a-z_][a-z0-9_]*$`)

var (
	// environmentPattern 은 APP_ENVIRONMENT 로 받는 모양이다. 소문자로 시작하는 짧은 이름이다.
	environmentPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,31}$`)
	// versionPattern 은 APP_VERSION 으로 받는 모양이다. git SHA, 태그(v1.2.3), 이미지 태그가 들어간다.
	// 이 값들은 모든 로그 줄에 실린다. 줄바꿈이나 따옴표가 든 값을 받지 않는다.
	versionPattern = regexp.MustCompile(`^[A-Za-z0-9._+-]{1,64}$`)
	// logLevels 는 LOG_LEVEL 로 받는 값들이다.
	logLevels = []string{"debug", "info", "warning", "error"}
	// providers 는 PAYMENT_PROVIDER 로 받는 값들이다.
	providers = []string{ProviderFake, ProviderToss}
	// tossSecretKeyPattern 과 tossClientKeyPattern 은 토스페이먼츠의 테스트 키 모양이다.
	// 결제위젯 키(test_gsk_, test_gck_)와 API 개별 연동 키(test_sk_, test_ck_)를 받는다. 라이브 키(live_)는 받지 않는다.
	// 이 서버는 연습용이라 실제 돈을 받지 않는다(테스트 키로 부르면 돈이 나가지 않는다).
	tossSecretKeyPattern = regexp.MustCompile(`^test_(g?)sk_[A-Za-z0-9_]{1,200}$`)
	tossClientKeyPattern = regexp.MustCompile(`^test_(g?)ck_[A-Za-z0-9_]{1,200}$`)
)

// Lookup 은 이름으로 설정값을 찾는다. 없으면 두 번째 값이 false 다. os.LookupEnv 와 같은 모양이다.
type Lookup func(name string) (string, bool)

// Settings 는 서버가 쓰는 설정 전부다. 만든 뒤에는 고치지 않는다.
type Settings struct {
	// Debug 가 켜지면 개발용 동작(자세한 로그)을 쓴다. 운영에서는 끈다.
	Debug bool
	// AppEnvironment 와 AppVersion 은 이 프로세스가 어디에 배포된 어느 버전인지다. 모든 로그 줄에 실린다.
	AppEnvironment string
	AppVersion     string
	// LogLevel 은 남기는 로그의 가장 낮은 수준이다. debug, info, warning, error 가운데 하나다.
	LogLevel string
	// Host 와 Port 는 서버가 요청을 받는 주소다.
	Host string
	Port int
	// DatabaseURL 은 PostgreSQL 접속 주소다. 비밀번호가 들어 있다. 로그와 오류에 싣지 않는다.
	DatabaseURL string
	// DBSchema 는 테이블이 놓이는 스키마다.
	DBSchema string
	// AuthJWKSURL 은 인증 서버가 공개키를 내주는 주소다. 이 주소에서 받은 키로 서명된 토큰을 믿는다.
	AuthJWKSURL string
	// AuthRevocationsURL 은 인증 서버가 끊긴 세션의 목록을 내주는 주소다(#274). 적지 않으면 AuthJWKSURL 옆의 주소다.
	AuthRevocationsURL string
	// JWTIssuer 는 받아들이는 토큰의 발급자(iss), JWTAudience 는 이 서버의 이름(aud)이다.
	JWTIssuer   string
	JWTAudience string
	// SpendFreeFirst 가 true 면 크레딧을 쓸 때 무료 크레딧부터 쓰고, false 면 산 크레딧부터 쓴다.
	SpendFreeFirst bool
	// FreeCreditTTL 은 무료 크레딧이 지급된 뒤 사라질 때까지의 시간이다.
	// 바꿔도 이미 지급한 것의 기한은 그대로다. 사라지는 시각은 지급할 때 정해 DB 에 적는다.
	FreeCreditTTL time.Duration
	// HoldTTL 은 홀드를 걸거나 연장한 뒤 만료될 때까지의 시간이다. 바꾸면 그 뒤에 걸거나 연장한 홀드부터 적용된다.
	HoldTTL time.Duration
	// ChatHoldTTL 은 chat 서버가 건 홀드의 만료까지의 시간이다(CHAT_HOLD_TTL). 연장할 때도 이만큼 민다.
	ChatHoldTTL time.Duration
	// OrderTTL 은 주문을 만든 뒤 만료될 때까지의 시간이다. 바꾸면 그 뒤에 만든 주문부터 적용된다.
	OrderTTL time.Duration
	// WelcomeCredits 는 사용자가 한 번 받는 환영 크레딧의 양이다. 0 이면 주지 않는다.
	WelcomeCredits credit.Amount
	// AttendanceSilver 는 출석의 하루 양이다(#339). 첫째 값이 1일째이고, 길이가 주기의 날 수다. 마지막 날에 보물 상자를 연다.
	// 바꾸면 그 뒤에 받는 출석부터 적용된다. 이미 받은 날의 기록은 그대로다.
	AttendanceSilver attendance.Schedule
	// WebhookSecret 은 결제 대행사의 알림에 붙은 서명을 확인하는 비밀이다. 로그와 오류에 싣지 않는다.
	WebhookSecret string
	// GameServerSecret 은 게임 서버가 보낸 요청의 서명을 확인하는 비밀이다. 게임 서버도 같은 값을 갖는다.
	// 로그와 오류에 싣지 않는다.
	GameServerSecret string
	// AuthServerSecret 은 인증 서버가 보낸 요청의 서명을 확인하는 비밀이다. 인증 서버도 같은 값을 갖는다(BILLING_SECRET).
	// 로그와 오류에 싣지 않는다.
	AuthServerSecret string
	// ChatServerSecret 은 chat 서버가 보낸 요청의 서명을 확인하는 비밀이다. chat 서버도 같은 값을 갖는다.
	// 비어 있으면 chat 서버의 요청을 하나도 받지 않는다(chat 서버를 띄우지 않는 동안). 로그와 오류에 싣지 않는다.
	ChatServerSecret string
	// Payment 는 꽂을 결제 대행사와 그 키다.
	Payment Payment
}

// Payment 는 결제 대행사의 설정이다. 서버와 대사(cmd/reconcile, 결제 대행사에 결과를 묻는다)가 같은 것을 읽는다.
type Payment struct {
	// Provider 는 꽂을 결제 대행사다. ProviderFake 나 ProviderToss 다.
	Provider string
	// TossSecretKey 는 토스페이먼츠의 시크릿 키다. 승인과 조회에 쓴다. 로그와 오류에 싣지 않는다.
	// Provider 가 toss 일 때만 있다.
	TossSecretKey string
	// TossClientKey 는 토스페이먼츠의 클라이언트 키다. 결제창(브라우저)에 실리는 공개된 값이다.
	// Provider 가 toss 일 때만 있다.
	TossClientKey string
}

// Database 는 DB 에 접속하는 데 필요한 설정이다. 마이그레이션 명령(cmd/migrate)은 이것만 읽는다.
type Database struct {
	// URL 은 PostgreSQL 접속 주소다. 비밀번호가 들어 있다. 로그와 오류에 싣지 않는다.
	URL string
	// Schema 는 테이블이 놓이는 스키마다.
	Schema string
}

// Logging 은 로그에 싣는 것과 남기는 수준이다. 서버와 작업 명령(cmd/sweeper, cmd/reconcile)이 함께 읽는다.
type Logging struct {
	// AppEnvironment 와 AppVersion 은 이 프로세스가 어디에 배포된 어느 버전인지다. 모든 로그 줄에 실린다.
	AppEnvironment string
	AppVersion     string
	// LogLevel 은 남기는 로그의 가장 낮은 수준이다.
	LogLevel string
}

// Metrics 는 메트릭을 어디로, 얼마나 자주 보낼지다(docs/observability.md 의 "2. 메트릭").
// 서버와 작업 명령(cmd/sweeper, cmd/reconcile)이 함께 읽는다(LoadMetrics). Endpoint 가 비면 보내지 않는다.
type Metrics struct {
	// Endpoint 는 수집기의 OTLP(HTTP) 주소다(OTEL_EXPORTER_OTLP_ENDPOINT, http://alloy:4318). 끝의 / 는 뗀다.
	Endpoint string
	// Interval 은 모은 값을 보내는 간격이다(OTEL_METRIC_EXPORT_INTERVAL, 밀리초).
	Interval time.Duration
}

// Rules 는 크레딧을 다루는 규칙이다. 서버와 작업 명령이 같은 값을 써야 한다.
// 정리 작업도 사라질 무료 크레딧을 지우고 홀드를 돌려주므로, 서버와 규칙이 다르면 결과가 어긋난다.
type Rules struct {
	SpendFreeFirst bool
	FreeCreditTTL  time.Duration
	HoldTTL        time.Duration
	// ChatHoldTTL 은 chat 서버가 건 홀드의 만료까지의 시간이다. 0 이면 따로 정하지 않은 것이다(HoldTTL 그대로)
	ChatHoldTTL time.Duration
	OrderTTL    time.Duration
}

// Jobs 는 결제 대행사에 묻는 작업 명령(cmd/reconcile, cmd/orders)이 읽는 설정이다.
// 요청을 받지 않으므로 포트, 공개키 주소, 서명의 비밀이 없어도 돈다.
// 결제 대행사의 설정은 읽는다. 대사가 서버와 같은 결제 대행사에 결과를 묻는다.
type Jobs struct {
	Database Database
	Logging  Logging
	Rules    Rules
	Payment  Payment
}

// Sweeper 는 정리 작업(cmd/sweeper)이 읽는 설정이다. 결제 대행사의 설정은 읽지 않는다.
// 정리 작업이 다루는 것(만료된 홀드, 사라진 무료 크레딧, 만료된 pending 주문)은 DB 만으로 끝난다.
// 그래서 결제 대행사의 키(TOSS_SECRET_KEY)를 주지 않아도 돈다. 비밀은 쓰는 프로세스에만 준다(docker-compose.yml).
type Sweeper struct {
	Database Database
	Logging  Logging
	Rules    Rules
	// HeartbeatFile 은 한 바퀴를 끝낼 때마다 시각을 바꾸는 파일이다(jobs.Beat).
	// compose 가 정리 작업의 컨테이너에 넣는다. 비어 있으면 쓰지 않는다(PC 에서 돌릴 때)
	HeartbeatFile string
	// GuardianNotices 는 보호자에게 알릴 결제를 인증 서버에 보내는 설정이다(#352).
	GuardianNotices GuardianNotices
	// UserNotices 는 사용자의 알림함에 알릴 일을 알림 서버에 보내는 설정이다(#385).
	UserNotices UserNotices
}

// UserNotices 는 정리 작업이 사용자의 알림을 알림 서버에 보낼 곳과 비밀이다.
// 둘 중 하나라도 비면 보내지 않는다. 알릴 일은 적어 두었다가 설정한 뒤에 나간다(7일이 지난 것은 보내지 않는다).
type UserNotices struct {
	// URL 은 알림 서버의 주소다(NOTIFICATION_URL, http://127.0.0.1:8004). 경로(/api/v1/notification/...)는 붙이지 않는다.
	URL string
	// Secret 은 알림 서버와 함께 아는 비밀이다(NOTIFICATION_SECRET). 알림 서버의 BILLING_SERVER_SECRET 과 같은 값이다.
	Secret string
}

// Enabled 는 보낼 곳과 비밀이 모두 있는지다.
func (u UserNotices) Enabled() bool {
	return u.URL != "" && u.Secret != ""
}

// GuardianNotices 는 정리 작업이 보호자 알림을 인증 서버에 보낼 곳과 비밀이다.
// 둘 중 하나라도 비면 보내지 않는다. 알릴 일은 적어 두었다가 설정한 뒤에 나간다.
type GuardianNotices struct {
	// URL 은 인증 서버의 알림 주소다. AUTH_GUARDIAN_NOTICES_URL 이고, 적지 않으면 AUTH_JWKS_URL 옆의 …/service/guardian-notices 다.
	URL string
	// Secret 은 인증 서버와 함께 아는 비밀이다(AUTH_SERVER_SECRET). 인증 서버가 이 서버를 부를 때와 같은 짝이다.
	Secret string
}

// Enabled 는 보낼 곳과 비밀이 모두 있는지다.
func (g GuardianNotices) Enabled() bool {
	return g.URL != "" && g.Secret != ""
}

// Addr 는 서버가 요청을 받는 주소를 "host:port" 로 돌려준다.
func (s Settings) Addr() string {
	return fmt.Sprintf("%s:%d", s.Host, s.Port)
}

// Load 는 설정을 읽어 검사한 뒤 돌려준다. 틀린 것이 여럿이면 한 번에 모두 알려 준다.
func Load(lookup Lookup) (Settings, error) {
	debug, debugErr := readBool(lookup, "DEBUG", false)
	port, portErr := readPort(lookup, "PORT", DefaultPort)
	db, dbErr := LoadDatabase(lookup)
	jwksURL, jwksErr := readHTTPURL(lookup, "AUTH_JWKS_URL")
	revocationsURL, revocationsErr := readRevocationsURL(lookup, jwksURL)
	rules, rulesErr := loadRules(lookup)
	logging, loggingErr := loadLogging(lookup)
	webhookSecret, webhookErr := readSecret(lookup, "PG_WEBHOOK_SECRET", MinWebhookSecretLength)
	gameSecret, gameSecretErr := readSecret(lookup, "GAME_SERVER_SECRET", MinServiceSecretLength)
	authSecret, authSecretErr := readSecret(lookup, "AUTH_SERVER_SECRET", MinServiceSecretLength)
	chatSecret, chatSecretErr := readOptionalSecret(lookup, "CHAT_SERVER_SECRET", MinServiceSecretLength)
	welcome, welcomeErr := readCredits(lookup, "WELCOME_CREDITS", DefaultWelcomeCredits, MaxWelcomeCredits)
	attendanceSilver, attendanceErr := readSchedule(lookup, "ATTENDANCE_SILVER")
	payment, paymentErr := loadPayment(lookup)

	if err := errors.Join(
		debugErr, portErr, dbErr, jwksErr, revocationsErr, rulesErr, loggingErr, webhookErr, welcomeErr, attendanceErr, paymentErr,
		gameSecretErr, authSecretErr, chatSecretErr, distinctSecrets(webhookSecret, gameSecret, authSecret, chatSecret),
		providerAllowed(logging, payment),
	); err != nil {
		return Settings{}, err
	}
	return Settings{
		Debug:              debug,
		AppEnvironment:     logging.AppEnvironment,
		AppVersion:         logging.AppVersion,
		LogLevel:           logging.LogLevel,
		Host:               readString(lookup, "HOST", DefaultHost),
		Port:               port,
		DatabaseURL:        db.URL,
		DBSchema:           db.Schema,
		AuthJWKSURL:        jwksURL,
		AuthRevocationsURL: revocationsURL,
		JWTIssuer:          readString(lookup, "JWT_ISSUER", DefaultJWTIssuer),
		JWTAudience:        readString(lookup, "JWT_AUDIENCE", DefaultJWTAudience),
		SpendFreeFirst:     rules.SpendFreeFirst,
		FreeCreditTTL:      rules.FreeCreditTTL,
		HoldTTL:            rules.HoldTTL,
		ChatHoldTTL:        rules.ChatHoldTTL,
		OrderTTL:           rules.OrderTTL,
		WelcomeCredits:     welcome,
		AttendanceSilver:   attendanceSilver,
		WebhookSecret:      webhookSecret,
		GameServerSecret:   gameSecret,
		AuthServerSecret:   authSecret,
		ChatServerSecret:   chatSecret,
		Payment:            payment,
	}, nil
}

// LoadJobs 는 결제 대행사에 묻는 작업 명령이 쓰는 설정만 읽어 검사한다. 틀린 것이 여럿이면 한 번에 모두 알려 준다.
func LoadJobs(lookup Lookup) (Jobs, error) {
	db, dbErr := LoadDatabase(lookup)
	logging, loggingErr := loadLogging(lookup)
	rules, rulesErr := loadRules(lookup)
	payment, paymentErr := loadPayment(lookup)
	if err := errors.Join(dbErr, loggingErr, rulesErr, paymentErr, providerAllowed(logging, payment)); err != nil {
		return Jobs{}, err
	}
	return Jobs{Database: db, Logging: logging, Rules: rules, Payment: payment}, nil
}

// LoadSweeper 는 정리 작업이 쓰는 설정만 읽어 검사한다. 틀린 것이 여럿이면 한 번에 모두 알려 준다.
// 결제 대행사의 설정(PAYMENT_PROVIDER, TOSS_*)은 적혀 있어도 읽지 않는다.
// 인증 서버의 비밀(AUTH_SERVER_SECRET)은 보호자 알림을 보내는 데만 쓴다. 없으면 알릴 일을 적기만 한다.
func LoadSweeper(lookup Lookup) (Sweeper, error) {
	db, dbErr := LoadDatabase(lookup)
	logging, loggingErr := loadLogging(lookup)
	rules, rulesErr := loadRules(lookup)
	notices, noticesErr := readGuardianNotices(lookup)
	userNotices, userNoticesErr := readUserNotices(lookup)
	if err := errors.Join(
		dbErr, loggingErr, rulesErr, noticesErr, userNoticesErr, differentSecret(notices.Secret, userNotices.Secret),
	); err != nil {
		return Sweeper{}, err
	}
	heartbeat := readString(lookup, "HEARTBEAT_FILE", "")
	return Sweeper{
		Database: db, Logging: logging, Rules: rules, HeartbeatFile: heartbeat,
		GuardianNotices: notices, UserNotices: userNotices,
	}, nil
}

// readUserNotices 는 사용자의 알림을 보낼 곳과 비밀을 읽는다. 없어도 된다(그러면 보내지 않는다). 있으면 모양을 본다.
func readUserNotices(lookup Lookup) (UserNotices, error) {
	var notices UserNotices
	var secretErr, urlErr error
	if value, ok := lookup("NOTIFICATION_SECRET"); ok && value != "" {
		notices.Secret, secretErr = readSecret(lookup, "NOTIFICATION_SECRET", MinServiceSecretLength)
	}
	if value, ok := lookup("NOTIFICATION_URL"); ok && value != "" {
		notices.URL, urlErr = readHTTPURL(lookup, "NOTIFICATION_URL")
	}
	return notices, errors.Join(secretErr, urlErr)
}

// differentSecret 은 인증 서버의 비밀과 알림 서버의 비밀이 다른지 본다. 비어 있으면 보지 않는다.
// 같은 값이면 한쪽이 아는 비밀로 다른 쪽인 척할 수 있고, 하나가 새면 둘 다 샌 것이 된다.
func differentSecret(authSecret string, notificationSecret string) error {
	if authSecret != "" && authSecret == notificationSecret {
		return errors.New("AUTH_SERVER_SECRET 과 NOTIFICATION_SECRET 은 서로 다른 값이어야 합니다")
	}
	return nil
}

// guardianNoticesPath 는 인증 서버의 알림 주소의 끝이다. 공개키(…/jwks)와 같은 곳(/api/v1/auth)에 있다.
const guardianNoticesPath = "/service/guardian-notices"

// readGuardianNotices 는 보호자 알림을 보낼 곳과 비밀을 읽는다. 없어도 된다(그러면 보내지 않는다). 있으면 모양을 본다.
func readGuardianNotices(lookup Lookup) (GuardianNotices, error) {
	var notices GuardianNotices
	var secretErr, urlErr error
	if value, ok := lookup("AUTH_SERVER_SECRET"); ok && value != "" {
		notices.Secret, secretErr = readSecret(lookup, "AUTH_SERVER_SECRET", MinServiceSecretLength)
	}
	notices.URL, urlErr = readGuardianNoticesURL(lookup)
	return notices, errors.Join(secretErr, urlErr)
}

// readGuardianNoticesURL 은 알림 주소를 읽는다. 적지 않았으면 공개키 주소에서 만든다. 둘 다 없으면 빈 글자다.
func readGuardianNoticesURL(lookup Lookup) (string, error) {
	if value, ok := lookup("AUTH_GUARDIAN_NOTICES_URL"); ok && value != "" {
		return readHTTPURL(lookup, "AUTH_GUARDIAN_NOTICES_URL")
	}
	value, ok := lookup("AUTH_JWKS_URL")
	if !ok || value == "" {
		return "", nil
	}
	jwksURL, err := readHTTPURL(lookup, "AUTH_JWKS_URL")
	if err != nil {
		return "", err
	}
	if !strings.HasSuffix(jwksURL, jwksPath) {
		return "", errors.New("AUTH_JWKS_URL 이 /jwks 로 끝나지 않습니다. AUTH_GUARDIAN_NOTICES_URL 을 적어야 합니다")
	}
	return strings.TrimSuffix(jwksURL, jwksPath) + guardianNoticesPath, nil
}

// providerAllowed 는 그 환경에서 쓸 수 있는 결제 대행사인지 본다. 운영에서는 가짜를 받지 않는다.
// 서버와 작업 명령(정리 작업, 대사) 모두 같은 규칙이다. 대사가 가짜에 물으면 가짜의 답으로 원장을 맞춘다.
func providerAllowed(logging Logging, payment Payment) error {
	if logging.AppEnvironment == ProductionEnvironment && payment.Provider == ProviderFake {
		return ErrFakeInProduction
	}
	return nil
}

// loadPayment 는 결제 대행사의 설정을 읽는다. 토스페이먼츠면 테스트 키 둘이 있어야 하고, 둘의 종류가 같아야 한다.
// 가짜면 토스페이먼츠의 키는 읽지 않는다.
func loadPayment(lookup Lookup) (Payment, error) {
	provider, err := readChoice(lookup, "PAYMENT_PROVIDER", ProviderFake, providers)
	if err != nil || provider != ProviderToss {
		return Payment{Provider: provider}, err
	}
	secretKey, secretErr := readTossKey(lookup, "TOSS_SECRET_KEY", tossSecretKeyPattern, "test_gsk_ 나 test_sk_")
	clientKey, clientErr := readTossKey(lookup, "TOSS_CLIENT_KEY", tossClientKeyPattern, "test_gck_ 나 test_ck_")
	if err := errors.Join(secretErr, clientErr); err != nil {
		return Payment{}, err
	}
	if !sameTossFamily(secretKey, clientKey) {
		return Payment{}, errors.New("TOSS_SECRET_KEY 와 TOSS_CLIENT_KEY 는 같은 종류의 키여야 합니다(결제위젯 키 test_gsk_·test_gck_ 끼리, API 개별 연동 키 test_sk_·test_ck_ 끼리)")
	}
	return Payment{Provider: provider, TossSecretKey: secretKey, TossClientKey: clientKey}, nil
}

// readTossKey 는 토스페이먼츠의 테스트 키를 읽는다. 없거나 모양이 다르면(라이브 키도) 오류다. 오류에는 받은 값을 싣지 않는다.
func readTossKey(lookup Lookup, name string, pattern *regexp.Regexp, prefixes string) (string, error) {
	value, err := readRequired(lookup, name)
	if err != nil {
		return "", err
	}
	if !pattern.MatchString(value) {
		return "", fmt.Errorf("%s 는 %s 로 시작하는 테스트 키여야 합니다. 이 서버는 연습용이라 라이브 키를 받지 않습니다", name, prefixes)
	}
	return value, nil
}

// sameTossFamily 는 두 키가 같은 종류(결제위젯 또는 API 개별 연동)인지 본다. 앞머리의 g 가 같은지 본다.
// 종류가 다르면 결제창이 뜨지 않거나 승인이 거절된다. 서버가 뜨기 전에 알린다.
func sameTossFamily(secretKey string, clientKey string) bool {
	return tossSecretKeyPattern.FindStringSubmatch(secretKey)[1] == tossClientKeyPattern.FindStringSubmatch(clientKey)[1]
}

// 메트릭을 보내는 간격. OpenTelemetry 의 이름(OTEL_METRIC_EXPORT_INTERVAL)과 단위(밀리초)를 따른다.
// SDK 의 기본(60초)이면 rate(…[1m]) 에 점이 하나뿐이라 15초로 둔다.
const (
	DefaultMetricInterval = 15 * time.Second
	MinMetricInterval     = time.Second
)

// LoadMetrics 는 메트릭을 보낼 곳과 간격을 읽는다. 보낼 곳은 없어도 된다(그러면 보내지 않는다).
// 다른 설정과 따로 읽는다. 메트릭을 내는 프로세스만 부른다.
func LoadMetrics(lookup Lookup) (Metrics, error) {
	endpoint, endpointErr := readOTLPEndpoint(lookup)
	interval, intervalErr := readMilliseconds(lookup, "OTEL_METRIC_EXPORT_INTERVAL", DefaultMetricInterval, MinMetricInterval)
	if err := errors.Join(endpointErr, intervalErr); err != nil {
		return Metrics{}, err
	}
	return Metrics{Endpoint: endpoint, Interval: interval}, nil
}

// readOTLPEndpoint 는 수집기의 주소를 읽는다. 비어 있으면 빈 글자다. 있으면 http:// 나 https:// 로 시작해야 하고 경로가 없어야 한다.
// 경로(/v1/metrics)는 보내는 쪽이 붙인다. OpenTelemetry 의 OTEL_EXPORTER_OTLP_ENDPOINT 와 같은 뜻이다.
func readOTLPEndpoint(lookup Lookup) (string, error) {
	const name = "OTEL_EXPORTER_OTLP_ENDPOINT"
	value, ok := lookup(name)
	if !ok || value == "" {
		return "", nil
	}
	endpoint, err := readHTTPURL(lookup, name)
	if err != nil {
		return "", err
	}
	parsed, _ := url.Parse(endpoint)
	if strings.Trim(parsed.Path, "/") != "" || parsed.RawQuery != "" {
		return "", fmt.Errorf("%s 는 http://alloy:4318 처럼 경로 없이 적습니다. /v1/metrics 는 붙이지 않습니다", name)
	}
	return strings.TrimSuffix(endpoint, "/"), nil
}

// readMilliseconds 는 밀리초로 적은 시간을 읽는다. minimum 보다 짧으면 받지 않는다.
func readMilliseconds(lookup Lookup, name string, fallback time.Duration, minimum time.Duration) (time.Duration, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback, nil
	}
	milliseconds, err := strconv.ParseInt(value, 10, 64)
	duration := time.Duration(milliseconds) * time.Millisecond
	if err != nil || duration < minimum {
		return 0, fmt.Errorf("%s 는 15000 처럼 밀리초로 적고 %d 이상이어야 합니다", name, minimum.Milliseconds())
	}
	return duration, nil
}

// loadLogging 은 로그에 관한 설정을 읽는다.
func loadLogging(lookup Lookup) (Logging, error) {
	environment, environmentErr := readPattern(lookup, "APP_ENVIRONMENT", DefaultAppEnvironment, environmentPattern,
		"소문자로 시작하고 소문자, 숫자, 밑줄, 붙임표로 된 32자 이하의 이름이어야 합니다")
	version, versionErr := readPattern(lookup, "APP_VERSION", DefaultAppVersion, versionPattern,
		"영문자, 숫자, 점, 밑줄, 더하기, 붙임표로 된 64자 이하의 값이어야 합니다")
	logLevel, logLevelErr := readChoice(lookup, "LOG_LEVEL", DefaultLogLevel, logLevels)
	if err := errors.Join(environmentErr, versionErr, logLevelErr); err != nil {
		return Logging{}, err
	}
	return Logging{AppEnvironment: environment, AppVersion: version, LogLevel: logLevel}, nil
}

// loadRules 는 크레딧을 다루는 규칙을 읽는다.
func loadRules(lookup Lookup) (Rules, error) {
	freeFirst, freeFirstErr := readBool(lookup, "SPEND_FREE_FIRST", DefaultSpendFreeFirst)
	freeTTL, freeTTLErr := readDuration(lookup, "FREE_CREDIT_TTL", DefaultFreeCreditTTL, MinFreeCreditTTL)
	holdTTL, holdTTLErr := readDuration(lookup, "HOLD_TTL", DefaultHoldTTL, MinExpiryTTL)
	chatHoldTTL, chatHoldTTLErr := readDuration(lookup, "CHAT_HOLD_TTL", DefaultChatHoldTTL, MinExpiryTTL)
	orderTTL, orderTTLErr := readDuration(lookup, "ORDER_TTL", DefaultOrderTTL, MinExpiryTTL)
	if err := errors.Join(freeFirstErr, freeTTLErr, holdTTLErr, chatHoldTTLErr, orderTTLErr); err != nil {
		return Rules{}, err
	}
	return Rules{
		SpendFreeFirst: freeFirst, FreeCreditTTL: freeTTL, HoldTTL: holdTTL, ChatHoldTTL: chatHoldTTL, OrderTTL: orderTTL,
	}, nil
}

// Rules 는 서버의 설정에서 크레딧을 다루는 규칙만 꺼낸다. 서버와 작업 명령이 같은 방법으로 서비스를 만든다.
func (s Settings) Rules() Rules {
	return Rules{
		SpendFreeFirst: s.SpendFreeFirst, FreeCreditTTL: s.FreeCreditTTL, HoldTTL: s.HoldTTL, ChatHoldTTL: s.ChatHoldTTL,
		OrderTTL: s.OrderTTL,
	}
}

// ReceivesTossNotifications 는 토스페이먼츠의 알림(웹훅)을 받는지다. 토스페이먼츠를 꽂았을 때만 받는다.
// 가짜를 꽂은 서버에 서명 없는 알림 주소를 열 까닭이 없다.
func (s Settings) ReceivesTossNotifications() bool {
	return s.Payment.Provider == ProviderToss
}

// CheckoutClientKey 는 개발용 결제 화면에 실을 토스페이먼츠의 클라이언트 키다.
// 개발 모드(DEBUG)에서 토스페이먼츠를 꽂았을 때만 있다. 빈 글자면 그 화면을 열지 않는다.
func (s Settings) CheckoutClientKey() string {
	if s.Debug && s.Payment.Provider == ProviderToss {
		return s.Payment.TossClientKey
	}
	return ""
}

// Logging 은 서버의 설정에서 로그에 관한 것만 꺼낸다.
func (s Settings) Logging() Logging {
	return Logging{AppEnvironment: s.AppEnvironment, AppVersion: s.AppVersion, LogLevel: s.LogLevel}
}

// LoadDatabase 는 DB 접속에 필요한 설정만 읽어 검사한다.
// 마이그레이션 명령은 인증 서버의 주소 같은 다른 설정이 없어도 돈다.
func LoadDatabase(lookup Lookup) (Database, error) {
	databaseURL, urlErr := readRequired(lookup, "DATABASE_URL")
	schema, schemaErr := readSchema(lookup, "DB_SCHEMA", DefaultSchema)
	if err := errors.Join(urlErr, schemaErr); err != nil {
		return Database{}, err
	}
	return Database{URL: databaseURL, Schema: schema}, nil
}

// readString 은 값을 그대로 읽는다. 없거나 비어 있으면 fallback 이다.
func readString(lookup Lookup, name string, fallback string) string {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback
	}
	return value
}

// readPattern 은 정해 둔 모양의 값을 읽는다. 없으면 fallback 이고, 모양이 다르면 오류다.
// 오류에는 받은 값을 싣지 않는다. rule 은 어떤 모양이어야 하는지 알려 주는 말이다.
func readPattern(lookup Lookup, name string, fallback string, pattern *regexp.Regexp, rule string) (string, error) {
	value := readString(lookup, name, fallback)
	if !pattern.MatchString(value) {
		return "", fmt.Errorf("%s 는 %s", name, rule)
	}
	return value, nil
}

// readChoice 는 정해 둔 값들 가운데 하나를 읽는다. 없으면 fallback 이고, 그 밖의 값이면 오류다.
func readChoice(lookup Lookup, name string, fallback string, choices []string) (string, error) {
	value := readString(lookup, name, fallback)
	if !slices.Contains(choices, value) {
		return "", fmt.Errorf("%s 는 %s 가운데 하나여야 합니다", name, strings.Join(choices, ", "))
	}
	return value, nil
}

// readRequired 는 반드시 있어야 하는 값을 읽는다. 없거나 비어 있으면 오류다.
func readRequired(lookup Lookup, name string) (string, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return "", fmt.Errorf("%s 가 없습니다. .env 나 환경 변수에 적어 주세요", name)
	}
	return value, nil
}

// readCredits 는 크레딧의 양을 읽는다. 0 부터 maximum 까지만 받는다.
func readCredits(lookup Lookup, name string, fallback credit.Amount, maximum credit.Amount) (credit.Amount, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback, nil
	}
	amount, err := credit.Parse(value)
	if err != nil || amount < 0 || amount > maximum {
		return 0, fmt.Errorf("%s 는 0 부터 %s 사이의 크레딧 양이어야 합니다", name, maximum)
	}
	return amount, nil
}

// readSchedule 은 출석의 하루 양을 쉼표로 나눈 목록으로 읽는다(140,160,180). 적지 않으면 기본값(attendance.DefaultSchedule)이다.
// 날 수와 양의 범위는 attendance.Schedule 의 규칙을 따른다.
func readSchedule(lookup Lookup, name string) (attendance.Schedule, error) {
	value, ok := lookup(name)
	if !ok || strings.TrimSpace(value) == "" {
		return attendance.DefaultSchedule(), nil
	}
	parts := strings.Split(value, ",")
	schedule := make(attendance.Schedule, 0, len(parts))
	for _, part := range parts {
		amount, err := credit.Parse(strings.TrimSpace(part))
		if err != nil {
			return nil, fmt.Errorf("%s 는 쉼표로 나눈 실버의 양이어야 합니다(예: 140,160,180)", name)
		}
		schedule = append(schedule, amount)
	}
	if err := schedule.Validate(); err != nil {
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	return schedule, nil
}

// readSecret 은 반드시 있어야 하는 비밀을 읽는다. minimum 글자보다 짧으면 오류다.
func readSecret(lookup Lookup, name string, minimum int) (string, error) {
	value, err := readRequired(lookup, name)
	if err != nil {
		return "", err
	}
	if len(value) < minimum {
		return "", fmt.Errorf("%s 는 %d자 이상이어야 합니다", name, minimum)
	}
	return value, nil
}

// readOptionalSecret 은 없어도 되는 비밀을 읽는다. 없거나 비어 있으면 빈 글자다. 적었으면 minimum 자 이상이어야 한다.
// 비어 있는 비밀로는 아무 요청도 통과하지 않는다(httpapi 의 requireAnyService 가 건너뛴다).
func readOptionalSecret(lookup Lookup, name string, minimum int) (string, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return "", nil
	}
	if len(value) < minimum {
		return "", fmt.Errorf("%s 는 %d자 이상이어야 합니다", name, minimum)
	}
	return value, nil
}

// distinctSecrets 는 서명에 쓰는 비밀들이 서로 다른 값인지 본다. 읽지 못한 것(빈 글자)은 보지 않는다. 그 오류는 따로 난다.
// 같은 값을 두 자리에 쓰면 한쪽이 아는 비밀로 다른 쪽인 척할 수 있고, 하나가 새면 둘 다 샌 것이 된다.
func distinctSecrets(secrets ...string) error {
	seen := map[string]bool{}
	for _, secret := range secrets {
		if secret == "" {
			continue
		}
		if seen[secret] {
			return errors.New("PG_WEBHOOK_SECRET, GAME_SERVER_SECRET, AUTH_SERVER_SECRET, CHAT_SERVER_SECRET 은 서로 다른 값이어야 합니다")
		}
		seen[secret] = true
	}
	return nil
}

// readHTTPURL 은 반드시 있어야 하는 http(s) 주소를 읽는다. 없거나 주소의 모양이 아니면 오류다.
// 서버가 뜬 뒤 첫 요청에서야 틀린 주소를 알게 되는 일을 막는다.
func readHTTPURL(lookup Lookup, name string) (string, error) {
	value, err := readRequired(lookup, name)
	if err != nil {
		return "", err
	}
	parsed, parseErr := url.Parse(value)
	if parseErr != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return "", fmt.Errorf("%s 는 http:// 나 https:// 로 시작하는 주소여야 합니다", name)
	}
	return value, nil
}

// jwksPath 와 revocationsPath 는 인증 서버의 두 주소의 끝이다. 둘은 같은 곳(/api/v1/auth)에 있다.
const (
	jwksPath        = "/jwks"
	revocationsPath = "/session-revocations"
)

// readRevocationsURL 은 끊긴 세션 목록의 주소를 읽는다(AUTH_SESSION_REVOCATIONS_URL).
// 적지 않으면 공개키 주소(…/jwks) 옆의 …/session-revocations 다. 공개키 주소가 그렇게 끝나지 않으면 적어야 한다.
// 공개키 주소가 틀렸으면(jwksURL 이 비었으면) 그 오류가 이미 따로 나므로 여기서는 더하지 않는다.
func readRevocationsURL(lookup Lookup, jwksURL string) (string, error) {
	if value, ok := lookup("AUTH_SESSION_REVOCATIONS_URL"); ok && value != "" {
		return readHTTPURL(lookup, "AUTH_SESSION_REVOCATIONS_URL")
	}
	if jwksURL == "" {
		return "", nil
	}
	if !strings.HasSuffix(jwksURL, jwksPath) {
		return "", errors.New("AUTH_JWKS_URL 이 /jwks 로 끝나지 않습니다. AUTH_SESSION_REVOCATIONS_URL 을 적어야 합니다")
	}
	return strings.TrimSuffix(jwksURL, jwksPath) + revocationsPath, nil
}

// readBool 은 참과 거짓을 읽는다. true, false, 1, 0 같은 값을 받는다.
func readBool(lookup Lookup, name string, fallback bool) (bool, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return false, fmt.Errorf("%s 는 true 나 false 여야 합니다", name)
	}
	return parsed, nil
}

// readDuration 은 시간의 길이를 읽는다. 168h, 30m, 90s 처럼 단위를 붙여 적는다. minimum 보다 짧으면 오류다.
func readDuration(lookup Lookup, name string, fallback time.Duration, minimum time.Duration) (time.Duration, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback, nil
	}
	duration, err := time.ParseDuration(value)
	if err != nil || duration < minimum {
		return 0, fmt.Errorf("%s 는 168h, 30m 처럼 단위를 붙인 시간이어야 하고 %s 보다 짧을 수 없습니다", name, minimum)
	}
	return duration, nil
}

// readPort 는 포트 번호를 읽는다. 1 부터 65535 까지만 받는다.
func readPort(lookup Lookup, name string, fallback int) (int, error) {
	value, ok := lookup(name)
	if !ok || value == "" {
		return fallback, nil
	}
	port, err := strconv.Atoi(value)
	if err != nil || port < 1 || port > 65535 {
		return 0, fmt.Errorf("%s 는 1 부터 65535 사이의 숫자여야 합니다", name)
	}
	return port, nil
}

// readSchema 는 스키마 이름을 읽는다. 소문자, 숫자, 밑줄로 된 이름만 받는다.
func readSchema(lookup Lookup, name string, fallback string) (string, error) {
	schema := readString(lookup, name, fallback)
	if !schemaPattern.MatchString(schema) {
		return "", fmt.Errorf("%s 는 소문자, 숫자, 밑줄로 된 이름이어야 합니다", name)
	}
	return schema, nil
}
