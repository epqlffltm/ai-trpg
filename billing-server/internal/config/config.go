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
	// DefaultFreeCreditTTL 은 무료 크레딧이 지급된 뒤 사라질 때까지의 시간이다. 1주일이다.
	DefaultFreeCreditTTL = 7 * 24 * time.Hour
	// DefaultAppEnvironment 는 배포 환경의 이름이다. 로그의 environment 칸에 적힌다.
	DefaultAppEnvironment = "development"
	// DefaultAppVersion 은 배포한 코드의 버전이다. 로그의 version 칸에 적힌다. 운영에서는 git SHA 를 넣는다.
	DefaultAppVersion = "dev"
	// DefaultLogLevel 은 남기는 로그의 가장 낮은 수준이다.
	DefaultLogLevel = "info"
	// MinFreeCreditTTL 은 FREE_CREDIT_TTL 로 받는 가장 짧은 시간이다.
	// DB 는 시각을 백만분의 1초까지만 적는다. 그보다 짧으면 지급한 순간과 사라지는 순간이 같아진다.
	MinFreeCreditTTL = time.Second
	// DefaultWelcomeCredits 는 사용자가 한 번 받는 환영 크레딧(무료 크레딧)의 양이다. 가장 싼 상품과 같은 양이다.
	DefaultWelcomeCredits credit.Amount = 1_000
	// MaxWelcomeCredits 는 WELCOME_CREDITS 로 받는 가장 큰 양이다. 0 을 몇 개 더 붙인 실수를 막는다.
	MaxWelcomeCredits credit.Amount = 1_000_000
	// MinServiceSecretLength 는 GAME_SERVER_SECRET 의 가장 짧은 길이다.
	MinServiceSecretLength = 32
	// MinWebhookSecretLength 는 PG_WEBHOOK_SECRET 의 가장 짧은 길이다. 짧은 비밀은 서명을 꾸며 내기 쉽다.
	MinWebhookSecretLength = 32
)

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
	// JWTIssuer 는 받아들이는 토큰의 발급자(iss), JWTAudience 는 이 서버의 이름(aud)이다.
	JWTIssuer   string
	JWTAudience string
	// SpendFreeFirst 가 true 면 크레딧을 쓸 때 무료 크레딧부터 쓰고, false 면 산 크레딧부터 쓴다.
	SpendFreeFirst bool
	// FreeCreditTTL 은 무료 크레딧이 지급된 뒤 사라질 때까지의 시간이다.
	// 바꿔도 이미 지급한 것의 기한은 그대로다. 사라지는 시각은 지급할 때 정해 DB 에 적는다.
	FreeCreditTTL time.Duration
	// WelcomeCredits 는 사용자가 한 번 받는 환영 크레딧의 양이다. 0 이면 주지 않는다.
	WelcomeCredits credit.Amount
	// WebhookSecret 은 결제 대행사의 알림에 붙은 서명을 확인하는 비밀이다. 로그와 오류에 싣지 않는다.
	WebhookSecret string
	// GameServerSecret 은 게임 서버가 보낸 요청의 서명을 확인하는 비밀이다. 게임 서버도 같은 값을 갖는다.
	// 로그와 오류에 싣지 않는다.
	GameServerSecret string
	// AuthServerSecret 은 인증 서버가 보낸 요청의 서명을 확인하는 비밀이다. 인증 서버도 같은 값을 갖는다(BILLING_SERVICE_SECRET).
	// 로그와 오류에 싣지 않는다.
	AuthServerSecret string
}

// Database 는 DB 에 접속하는 데 필요한 설정이다. 마이그레이션 명령(cmd/migrate)은 이것만 읽는다.
type Database struct {
	// URL 은 PostgreSQL 접속 주소다. 비밀번호가 들어 있다. 로그와 오류에 싣지 않는다.
	URL string
	// Schema 는 테이블이 놓이는 스키마다.
	Schema string
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
	freeFirst, freeFirstErr := readBool(lookup, "SPEND_FREE_FIRST", DefaultSpendFreeFirst)
	freeTTL, freeTTLErr := readDuration(lookup, "FREE_CREDIT_TTL", DefaultFreeCreditTTL, MinFreeCreditTTL)
	webhookSecret, webhookErr := readSecret(lookup, "PG_WEBHOOK_SECRET", MinWebhookSecretLength)
	gameSecret, gameSecretErr := readSecret(lookup, "GAME_SERVER_SECRET", MinServiceSecretLength)
	authSecret, authSecretErr := readSecret(lookup, "AUTH_SERVER_SECRET", MinServiceSecretLength)
	welcome, welcomeErr := readCredits(lookup, "WELCOME_CREDITS", DefaultWelcomeCredits, MaxWelcomeCredits)
	environment, environmentErr := readPattern(lookup, "APP_ENVIRONMENT", DefaultAppEnvironment, environmentPattern,
		"소문자로 시작하고 소문자, 숫자, 밑줄, 붙임표로 된 32자 이하의 이름이어야 합니다")
	version, versionErr := readPattern(lookup, "APP_VERSION", DefaultAppVersion, versionPattern,
		"영문자, 숫자, 점, 밑줄, 더하기, 붙임표로 된 64자 이하의 값이어야 합니다")
	logLevel, logLevelErr := readChoice(lookup, "LOG_LEVEL", DefaultLogLevel, logLevels)

	if err := errors.Join(
		debugErr, portErr, dbErr, jwksErr, freeFirstErr, freeTTLErr, webhookErr, welcomeErr,
		environmentErr, versionErr, logLevelErr, gameSecretErr, authSecretErr, distinctSecrets(webhookSecret, gameSecret, authSecret),
	); err != nil {
		return Settings{}, err
	}
	return Settings{
		Debug:            debug,
		AppEnvironment:   environment,
		AppVersion:       version,
		LogLevel:         logLevel,
		Host:             readString(lookup, "HOST", DefaultHost),
		Port:             port,
		DatabaseURL:      db.URL,
		DBSchema:         db.Schema,
		AuthJWKSURL:      jwksURL,
		JWTIssuer:        readString(lookup, "JWT_ISSUER", DefaultJWTIssuer),
		JWTAudience:      readString(lookup, "JWT_AUDIENCE", DefaultJWTAudience),
		SpendFreeFirst:   freeFirst,
		FreeCreditTTL:    freeTTL,
		WelcomeCredits:   welcome,
		WebhookSecret:    webhookSecret,
		GameServerSecret: gameSecret,
		AuthServerSecret: authSecret,
	}, nil
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

// distinctSecrets 는 서명에 쓰는 비밀들이 서로 다른 값인지 본다. 읽지 못한 것(빈 글자)은 보지 않는다. 그 오류는 따로 난다.
// 같은 값을 두 자리에 쓰면 한쪽이 아는 비밀로 다른 쪽인 척할 수 있고, 하나가 새면 둘 다 샌 것이 된다.
func distinctSecrets(secrets ...string) error {
	seen := map[string]bool{}
	for _, secret := range secrets {
		if secret == "" {
			continue
		}
		if seen[secret] {
			return errors.New("PG_WEBHOOK_SECRET, GAME_SERVER_SECRET, AUTH_SERVER_SECRET 은 서로 다른 값이어야 합니다")
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
