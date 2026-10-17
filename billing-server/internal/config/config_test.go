// billing-server/internal/config/config_test.go

package config_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
)

// 테스트용 접속 주소. 실제로 접속하지 않는다. 비밀번호 자리의 글자가 오류에 새는지 볼 때 쓴다.
const (
	secret      = "do-not-print-me"
	databaseURL = "postgres://billing:" + secret + "@127.0.0.1:5432/trpg"
	jwksURL     = "http://127.0.0.1:8000/api/v1/auth/jwks"
	// 알림의 서명에 쓰는 비밀. 이것도 오류에 새면 안 된다
	webhookSecret = "do-not-print-this-webhook-secret-either"
	// 게임 서버가 보낸 요청의 서명에 쓰는 비밀. 이것도 새면 안 된다
	gameSecret = "do-not-print-this-game-server-secret"
	// 인증 서버가 보낸 요청의 서명에 쓰는 비밀. 이것도 새면 안 된다
	authSecret = "do-not-print-this-auth-server-secret"
	// 토스페이먼츠의 테스트 키 모양. 실제 키가 아니다. 시크릿 키는 오류에 새면 안 된다
	tossSecretKey = "test_gsk_doNotPrintThisSecretKey01"
	tossClientKey = "test_gck_publicClientKey01"
)

// required 는 반드시 있어야 하는 값만 채운 맵에 더할 것을 얹어 돌려준다.
func required(extra map[string]string) map[string]string {
	values := map[string]string{
		"DATABASE_URL": databaseURL, "AUTH_JWKS_URL": jwksURL, "PG_WEBHOOK_SECRET": webhookSecret, "GAME_SERVER_SECRET": gameSecret,
		"AUTH_SERVER_SECRET": authSecret,
	}
	for name, value := range extra {
		values[name] = value
	}
	return values
}

// without 은 반드시 있어야 하는 값 가운데 name 하나만 뺀 맵을 돌려준다.
func without(name string) map[string]string {
	values := required(nil)
	delete(values, name)
	return values
}

// from 은 맵을 설정을 찾는 함수로 바꾼다. 실제 환경 변수를 읽지 않는다.
func from(values map[string]string) config.Lookup {
	return func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}
}

func TestLoadFillsDefaults(t *testing.T) {
	settings, err := config.Load(from(required(nil)))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}

	want := config.Settings{
		Debug: false,
		// 적지 않으면 개발 환경이고, 버전은 dev 이고, info 부터 남긴다
		AppEnvironment: "development",
		AppVersion:     "dev",
		LogLevel:       "info",
		Host:           "127.0.0.1",
		Port:           8003,
		DatabaseURL:    databaseURL,
		DBSchema:       "billing",
		AuthJWKSURL:    jwksURL,
		// 적지 않으면 공개키 주소 옆이다
		AuthRevocationsURL: "http://127.0.0.1:8000/api/v1/auth/session-revocations",
		JWTIssuer:          "ai-trpg-auth",
		JWTAudience:        "ai-trpg-billing",
		// 적지 않으면 무료 크레딧부터 쓰고, 무료 크레딧은 30일 뒤에 사라진다
		SpendFreeFirst: true,
		FreeCreditTTL:  30 * 24 * time.Hour,
		// 적지 않으면 홀드와 주문은 하루 뒤에 만료된다
		HoldTTL:  24 * time.Hour,
		OrderTTL: 24 * time.Hour,
		// 적지 않으면 환영 크레딧은 1,000 이다
		WelcomeCredits:   1_000,
		WebhookSecret:    webhookSecret,
		GameServerSecret: gameSecret,
		AuthServerSecret: authSecret,
		// 적지 않으면 가짜 결제 대행사다
		Payment: config.Payment{Provider: "fake"},
	}
	if settings != want {
		t.Errorf("설정 = %+v, 기대 = %+v", settings, want)
	}
}

func TestLoadReadsEveryValue(t *testing.T) {
	settings, err := config.Load(from(map[string]string{
		"DEBUG":                        "true",
		"HOST":                         "0.0.0.0",
		"PORT":                         "9000",
		"DATABASE_URL":                 databaseURL,
		"DB_SCHEMA":                    "billing_test",
		"AUTH_JWKS_URL":                "https://auth.example.com/jwks",
		"AUTH_SESSION_REVOCATIONS_URL": "https://auth.example.com/revoked",
		"JWT_ISSUER":                   "some-issuer",
		"JWT_AUDIENCE":                 "some-audience",
		"SPEND_FREE_FIRST":             "false",
		"FREE_CREDIT_TTL":              "36h30m",
		"HOLD_TTL":                     "2h",
		"ORDER_TTL":                    "30m",
		"PG_WEBHOOK_SECRET":            "0123456789abcdef0123456789abcdef",
		"GAME_SERVER_SECRET":           "fedcba9876543210fedcba9876543210",
		"AUTH_SERVER_SECRET":           "00112233445566778899aabbccddeeff",
		"WELCOME_CREDITS":              "250",
		"APP_ENVIRONMENT":              "production",
		"APP_VERSION":                  "3f2a9c1",
		"LOG_LEVEL":                    "warning",
		"PAYMENT_PROVIDER":             "toss",
		"TOSS_SECRET_KEY":              tossSecretKey,
		"TOSS_CLIENT_KEY":              tossClientKey,
	}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}

	want := config.Settings{
		Debug:              true,
		AppEnvironment:     "production",
		AppVersion:         "3f2a9c1",
		LogLevel:           "warning",
		Host:               "0.0.0.0",
		Port:               9000,
		DatabaseURL:        databaseURL,
		DBSchema:           "billing_test",
		AuthJWKSURL:        "https://auth.example.com/jwks",
		AuthRevocationsURL: "https://auth.example.com/revoked",
		JWTIssuer:          "some-issuer",
		JWTAudience:        "some-audience",
		SpendFreeFirst:     false,
		FreeCreditTTL:      36*time.Hour + 30*time.Minute,
		HoldTTL:            2 * time.Hour,
		OrderTTL:           30 * time.Minute,
		WelcomeCredits:     250,
		// 꼭 32자다. 받는 가장 짧은 길이다
		WebhookSecret:    "0123456789abcdef0123456789abcdef",
		GameServerSecret: "fedcba9876543210fedcba9876543210",
		AuthServerSecret: "00112233445566778899aabbccddeeff",
		Payment:          config.Payment{Provider: "toss", TossSecretKey: tossSecretKey, TossClientKey: tossClientKey},
	}
	if settings != want {
		t.Errorf("설정 = %+v, 기대 = %+v", settings, want)
	}
	if settings.Addr() != "0.0.0.0:9000" {
		t.Errorf("주소 = %q, 기대 = %q", settings.Addr(), "0.0.0.0:9000")
	}
}

func TestTheRevocationsURLMustBeGivenWhenItCannotBeDerived(t *testing.T) {
	// 공개키 주소가 …/jwks 로 끝나지 않으면 옆 주소를 짐작하지 않는다
	_, err := config.Load(from(required(map[string]string{"AUTH_JWKS_URL": "https://auth.example.com/keys"})))
	if err == nil || !strings.Contains(err.Error(), "AUTH_SESSION_REVOCATIONS_URL") {
		t.Errorf("오류 = %v. AUTH_SESSION_REVOCATIONS_URL 을 적으라고 해야 한다", err)
	}

	settings, err := config.Load(from(required(map[string]string{
		"AUTH_JWKS_URL": "https://auth.example.com/keys", "AUTH_SESSION_REVOCATIONS_URL": "https://auth.example.com/revoked",
	})))
	if err != nil || settings.AuthRevocationsURL != "https://auth.example.com/revoked" {
		t.Errorf("설정 = %q, 오류 = %v", settings.AuthRevocationsURL, err)
	}

	if _, err := config.Load(from(required(map[string]string{"AUTH_SESSION_REVOCATIONS_URL": "ftp://auth.example.com/x"}))); err == nil {
		t.Error("http 가 아닌 주소를 받았다")
	}
}

func TestLoadTreatsEmptyAsMissing(t *testing.T) {
	// .env 에 이름만 적고 값을 비워 둔 줄은 적지 않은 것과 같다
	settings, err := config.Load(from(required(map[string]string{
		"DEBUG": "", "HOST": "", "PORT": "", "DB_SCHEMA": "", "JWT_ISSUER": "", "JWT_AUDIENCE": "",
		"SPEND_FREE_FIRST": "", "FREE_CREDIT_TTL": "", "WELCOME_CREDITS": "", "HOLD_TTL": "", "ORDER_TTL": "",
	})))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}
	if settings.Port != config.DefaultPort || settings.DBSchema != config.DefaultSchema || settings.Debug {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
	if settings.JWTIssuer != config.DefaultJWTIssuer || settings.JWTAudience != config.DefaultJWTAudience {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
	if settings.WelcomeCredits != config.DefaultWelcomeCredits {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
	if settings.SpendFreeFirst != config.DefaultSpendFreeFirst || settings.FreeCreditTTL != config.DefaultFreeCreditTTL {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
	if settings.HoldTTL != config.DefaultHoldTTL || settings.OrderTTL != config.DefaultOrderTTL {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
}

func TestLoadRejectsBadValues(t *testing.T) {
	cases := []struct {
		name   string
		values map[string]string
		want   string
	}{
		{"접속 주소가 없다", without("DATABASE_URL"), "DATABASE_URL"},
		{"접속 주소가 비었다", required(map[string]string{"DATABASE_URL": ""}), "DATABASE_URL"},
		{"참거짓이 아니다", required(map[string]string{"DEBUG": "yes please"}), "DEBUG"},
		{"포트가 숫자가 아니다", required(map[string]string{"PORT": "http"}), "PORT"},
		{"포트가 0 이다", required(map[string]string{"PORT": "0"}), "PORT"},
		{"포트가 너무 크다", required(map[string]string{"PORT": "65536"}), "PORT"},
		{"스키마에 대문자", required(map[string]string{"DB_SCHEMA": "Billing"}), "DB_SCHEMA"},
		{"스키마에 쉼표", required(map[string]string{"DB_SCHEMA": "billing,auth"}), "DB_SCHEMA"},
		{"스키마에 따옴표", required(map[string]string{"DB_SCHEMA": `billing"; --`}), "DB_SCHEMA"},
		{"스키마가 숫자로 시작", required(map[string]string{"DB_SCHEMA": "1billing"}), "DB_SCHEMA"},
		{"공개키 주소가 없다", without("AUTH_JWKS_URL"), "AUTH_JWKS_URL"},
		{"알림의 비밀이 없다", without("PG_WEBHOOK_SECRET"), "PG_WEBHOOK_SECRET"},
		{"게임 서버의 비밀이 없다", without("GAME_SERVER_SECRET"), "GAME_SERVER_SECRET"},
		{"게임 서버의 비밀이 비었다", required(map[string]string{"GAME_SERVER_SECRET": ""}), "GAME_SERVER_SECRET"},
		{"게임 서버의 비밀이 짧다", required(map[string]string{"GAME_SERVER_SECRET": "0123456789abcdef0123456789abcde"}), "GAME_SERVER_SECRET"},
		{"두 비밀이 같은 값이다", required(map[string]string{"GAME_SERVER_SECRET": webhookSecret}), "서로 다른 값"},
		{"인증 서버의 비밀이 없다", without("AUTH_SERVER_SECRET"), "AUTH_SERVER_SECRET"},
		{"인증 서버의 비밀이 짧다", required(map[string]string{"AUTH_SERVER_SECRET": "0123456789abcdef0123456789abcde"}), "AUTH_SERVER_SECRET"},
		{"인증 서버의 비밀이 알림의 것과 같다", required(map[string]string{"AUTH_SERVER_SECRET": webhookSecret}), "서로 다른 값"},
		{"인증 서버의 비밀이 게임 서버의 것과 같다", required(map[string]string{"AUTH_SERVER_SECRET": gameSecret}), "서로 다른 값"},
		{"알림의 비밀이 비었다", required(map[string]string{"PG_WEBHOOK_SECRET": ""}), "PG_WEBHOOK_SECRET"},
		{"환영 크레딧이 숫자가 아니다", required(map[string]string{"WELCOME_CREDITS": "many"}), "WELCOME_CREDITS"},
		{"환영 크레딧이 음수다", required(map[string]string{"WELCOME_CREDITS": "-1"}), "WELCOME_CREDITS"},
		{"환영 크레딧이 소수다", required(map[string]string{"WELCOME_CREDITS": "10.5"}), "WELCOME_CREDITS"},
		{"환영 크레딧이 너무 많다", required(map[string]string{"WELCOME_CREDITS": "1000001"}), "WELCOME_CREDITS"},
		{"알림의 비밀이 짧다", required(map[string]string{"PG_WEBHOOK_SECRET": "0123456789abcdef0123456789abcde"}), "PG_WEBHOOK_SECRET"},
		{"공개키 주소가 비었다", required(map[string]string{"AUTH_JWKS_URL": ""}), "AUTH_JWKS_URL"},
		{"공개키 주소에 http 가 없다", required(map[string]string{"AUTH_JWKS_URL": "127.0.0.1:8000/jwks"}), "AUTH_JWKS_URL"},
		{"공개키 주소가 http 가 아니다", required(map[string]string{"AUTH_JWKS_URL": "ftp://auth.example.com/jwks"}), "AUTH_JWKS_URL"},
		{"공개키 주소가 파일이다", required(map[string]string{"AUTH_JWKS_URL": "file:///etc/passwd"}), "AUTH_JWKS_URL"},
		{"공개키 주소에 호스트가 없다", required(map[string]string{"AUTH_JWKS_URL": "http:///jwks"}), "AUTH_JWKS_URL"},
		{"쓰는 순서가 참거짓이 아니다", required(map[string]string{"SPEND_FREE_FIRST": "free"}), "SPEND_FREE_FIRST"},
		{"기한에 단위가 없다", required(map[string]string{"FREE_CREDIT_TTL": "168"}), "FREE_CREDIT_TTL"},
		{"기한이 날 단위다", required(map[string]string{"FREE_CREDIT_TTL": "7d"}), "FREE_CREDIT_TTL"},
		{"기한이 0 이다", required(map[string]string{"FREE_CREDIT_TTL": "0s"}), "FREE_CREDIT_TTL"},
		{"기한이 음수다", required(map[string]string{"FREE_CREDIT_TTL": "-1h"}), "FREE_CREDIT_TTL"},
		{"기한이 너무 짧다", required(map[string]string{"FREE_CREDIT_TTL": "999ms"}), "FREE_CREDIT_TTL"},
		{"홀드의 기한에 단위가 없다", required(map[string]string{"HOLD_TTL": "24"}), "HOLD_TTL"},
		{"홀드의 기한이 너무 짧다", required(map[string]string{"HOLD_TTL": "59s"}), "HOLD_TTL"},
		{"주문의 기한이 날 단위다", required(map[string]string{"ORDER_TTL": "1d"}), "ORDER_TTL"},
		{"주문의 기한이 너무 짧다", required(map[string]string{"ORDER_TTL": "59s"}), "ORDER_TTL"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := config.Load(from(tc.values))
			if err == nil {
				t.Fatal("오류가 나야 하는데 나지 않았다")
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Errorf("오류에 %s 가 없다: %v", tc.want, err)
			}
		})
	}
}

func TestLoadAcceptsTheShortestTTL(t *testing.T) {
	settings, err := config.Load(from(required(map[string]string{"FREE_CREDIT_TTL": "1s"})))
	if err != nil || settings.FreeCreditTTL != time.Second {
		t.Errorf("FreeCreditTTL = %v, %v, 기대 = 1s", settings.FreeCreditTTL, err)
	}
}

func TestLoadAcceptsTheShortestExpiry(t *testing.T) {
	settings, err := config.Load(from(required(map[string]string{"HOLD_TTL": "1m", "ORDER_TTL": "1m"})))
	if err != nil || settings.HoldTTL != time.Minute || settings.OrderTTL != time.Minute {
		t.Errorf("HoldTTL = %v, OrderTTL = %v, %v, 기대 = 1m", settings.HoldTTL, settings.OrderTTL, err)
	}
}

func TestLoadJobsNeedsNoServerSettings(t *testing.T) {
	// 작업 명령은 포트, 공개키 주소, 서명의 비밀이 없어도 돈다
	jobs, err := config.LoadJobs(from(map[string]string{
		"DATABASE_URL": databaseURL, "DB_SCHEMA": "billing_test", "HOLD_TTL": "2h", "SPEND_FREE_FIRST": "false",
		"APP_ENVIRONMENT": "staging", "LOG_LEVEL": "debug",
	}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}
	want := config.Jobs{
		Database: config.Database{URL: databaseURL, Schema: "billing_test"},
		Logging:  config.Logging{AppEnvironment: "staging", AppVersion: "dev", LogLevel: "debug"},
		Rules: config.Rules{
			SpendFreeFirst: false, FreeCreditTTL: 30 * 24 * time.Hour, HoldTTL: 2 * time.Hour, OrderTTL: 24 * time.Hour,
		},
		Payment: config.Payment{Provider: "fake"},
	}
	if jobs != want {
		t.Errorf("설정 = %+v, 기대 = %+v", jobs, want)
	}
}

func TestLoadSweeperNeedsNoPaymentSettings(t *testing.T) {
	// 정리 작업은 결제 대행사를 부르지 않는다. 토스페이먼츠를 골라 두고 키를 주지 않아도, 운영에서 가짜를 골라도 뜬다
	for name, values := range map[string]map[string]string{
		"토스인데 키가 없다":  {"PAYMENT_PROVIDER": "toss"},
		"토스인데 키가 틀렸다": {"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": "live_sk_x", "TOSS_CLIENT_KEY": "nope"},
		"운영인데 가짜다":    {"PAYMENT_PROVIDER": "fake", "APP_ENVIRONMENT": "production"},
		"모르는 결제 대행사":  {"PAYMENT_PROVIDER": "nope"},
	} {
		values["DATABASE_URL"] = databaseURL
		if _, err := config.LoadSweeper(from(values)); err != nil {
			t.Errorf("%s: %v. 결제 대행사의 설정을 읽지 않아야 한다", name, err)
		}
	}
}

func TestLoadSweeperReadsWhatItUses(t *testing.T) {
	sweeper, err := config.LoadSweeper(from(map[string]string{
		"DATABASE_URL": databaseURL, "DB_SCHEMA": "billing_test", "HOLD_TTL": "2h", "SPEND_FREE_FIRST": "false",
		"APP_ENVIRONMENT": "staging", "LOG_LEVEL": "debug", "HEARTBEAT_FILE": "/tmp/heartbeat",
	}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}
	want := config.Sweeper{
		Database: config.Database{URL: databaseURL, Schema: "billing_test"},
		Logging:  config.Logging{AppEnvironment: "staging", AppVersion: "dev", LogLevel: "debug"},
		Rules: config.Rules{
			SpendFreeFirst: false, FreeCreditTTL: 30 * 24 * time.Hour, HoldTTL: 2 * time.Hour, OrderTTL: 24 * time.Hour,
		},
		HeartbeatFile: "/tmp/heartbeat",
	}
	if sweeper != want {
		t.Errorf("설정 = %+v, 기대 = %+v", sweeper, want)
	}
}

func TestLoadSweeperReadsTheSameRulesAsTheServer(t *testing.T) {
	// 서버와 정리 작업의 규칙이 어긋나면 무료 크레딧과 홀드가 다르게 다뤄진다
	values := required(map[string]string{
		"SPEND_FREE_FIRST": "false", "FREE_CREDIT_TTL": "3h", "HOLD_TTL": "2h", "ORDER_TTL": "90m",
		"APP_ENVIRONMENT": "staging", "APP_VERSION": "v1.2.3", "LOG_LEVEL": "error",
	})
	settings, serverErr := config.Load(from(values))
	sweeper, sweeperErr := config.LoadSweeper(from(values))
	if serverErr != nil || sweeperErr != nil {
		t.Fatalf("설정을 읽지 못했다: %v, %v", serverErr, sweeperErr)
	}
	if settings.Rules() != sweeper.Rules || settings.Logging() != sweeper.Logging {
		t.Errorf("서버 = %+v %+v, 정리 작업 = %+v %+v", settings.Rules(), settings.Logging(), sweeper.Rules, sweeper.Logging)
	}
}

func TestLoadSweeperReportsEveryProblemAtOnce(t *testing.T) {
	_, err := config.LoadSweeper(from(map[string]string{
		"DB_SCHEMA": "NOPE", "HOLD_TTL": "nope", "ORDER_TTL": "1s", "SPEND_FREE_FIRST": "nope", "LOG_LEVEL": "loud",
	}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	for _, name := range []string{"DATABASE_URL", "DB_SCHEMA", "HOLD_TTL", "ORDER_TTL", "SPEND_FREE_FIRST", "LOG_LEVEL"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("오류에 %s 가 없다: %v", name, err)
		}
	}
}

func TestLoadJobsReadsTheSameRulesAsTheServer(t *testing.T) {
	// 서버와 정리 작업의 규칙이 어긋나면 무료 크레딧과 홀드가 다르게 다뤄진다
	values := required(map[string]string{
		"SPEND_FREE_FIRST": "false", "FREE_CREDIT_TTL": "3h", "HOLD_TTL": "2h", "ORDER_TTL": "90m",
		"APP_ENVIRONMENT": "staging", "APP_VERSION": "v1.2.3", "LOG_LEVEL": "error",
		"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": tossClientKey,
	})
	settings, serverErr := config.Load(from(values))
	jobs, jobsErr := config.LoadJobs(from(values))
	if serverErr != nil || jobsErr != nil {
		t.Fatalf("설정을 읽지 못했다: %v, %v", serverErr, jobsErr)
	}
	// 대사가 서버와 다른 결제 대행사에 물으면 결과가 어긋난다
	if settings.Rules() != jobs.Rules || settings.Logging() != jobs.Logging || settings.Payment != jobs.Payment {
		t.Errorf("서버 = %+v %+v %+v, 작업 = %+v %+v %+v",
			settings.Rules(), settings.Logging(), settings.Payment, jobs.Rules, jobs.Logging, jobs.Payment)
	}
}

func TestLoadJobsReportsEveryProblemAtOnce(t *testing.T) {
	_, err := config.LoadJobs(from(map[string]string{
		"DB_SCHEMA": "NOPE", "HOLD_TTL": "nope", "ORDER_TTL": "1s", "SPEND_FREE_FIRST": "nope", "LOG_LEVEL": "loud",
		"DATABASE_URL_X": databaseURL,
	}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	for _, name := range []string{"DATABASE_URL", "DB_SCHEMA", "HOLD_TTL", "ORDER_TTL", "SPEND_FREE_FIRST", "LOG_LEVEL"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("오류에 %s 가 없다: %v", name, err)
		}
	}
}

func TestLoadAcceptsTheEdgesOfWelcomeCredits(t *testing.T) {
	// 0 은 "주지 않는다"는 뜻이라 받는다
	for text, want := range map[string]int64{"0": 0, "1": 1, "1000000": 1_000_000} {
		settings, err := config.Load(from(required(map[string]string{"WELCOME_CREDITS": text})))
		if err != nil || int64(settings.WelcomeCredits) != want {
			t.Errorf("WELCOME_CREDITS=%s: %d, %v", text, settings.WelcomeCredits, err)
		}
	}
}

func TestLoadDatabaseNeedsOnlyTheDatabaseSettings(t *testing.T) {
	// 마이그레이션 명령은 인증 서버의 주소가 없어도 돈다
	db, err := config.LoadDatabase(from(map[string]string{"DATABASE_URL": databaseURL, "DB_SCHEMA": "billing_test"}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}
	if want := (config.Database{URL: databaseURL, Schema: "billing_test"}); db != want {
		t.Errorf("설정 = %+v, 기대 = %+v", db, want)
	}
}

func TestLoadDatabaseRejectsBadValues(t *testing.T) {
	_, err := config.LoadDatabase(from(map[string]string{"DB_SCHEMA": "Billing"}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	for _, name := range []string{"DATABASE_URL", "DB_SCHEMA"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("오류에 %s 가 없다: %v", name, err)
		}
	}
}

func TestLoadReportsEveryProblemAtOnce(t *testing.T) {
	_, err := config.Load(from(map[string]string{
		"PORT": "nope", "DEBUG": "nope", "DB_SCHEMA": "NOPE", "SPEND_FREE_FIRST": "nope", "FREE_CREDIT_TTL": "nope",
	}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}

	// 하나를 고치고 다시 띄워 다음 것을 만나는 일을 줄인다
	names := []string{
		"DATABASE_URL", "AUTH_JWKS_URL", "PORT", "DEBUG", "DB_SCHEMA", "SPEND_FREE_FIRST", "FREE_CREDIT_TTL", "PG_WEBHOOK_SECRET",
		"GAME_SERVER_SECRET", "AUTH_SERVER_SECRET",
	}
	for _, name := range names {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("오류에 %s 가 없다: %v", name, err)
		}
	}
}

func TestLoadNeverPrintsValues(t *testing.T) {
	// 다른 값이 틀려서 오류가 나도 접속 주소의 비밀번호는 오류에 실리지 않는다
	_, err := config.Load(from(required(map[string]string{"PORT": "nope"})))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), "nope") || strings.Contains(err.Error(), webhookSecret) ||
		strings.Contains(err.Error(), gameSecret) || strings.Contains(err.Error(), authSecret) {
		t.Errorf("오류에 설정의 값이 실렸다: %v", err)
	}
}

func TestLoadNeverPrintsAShortSecret(t *testing.T) {
	// 짧아서 거절한 비밀도 오류에 싣지 않는다. 길이만 알려 준다
	_, err := config.Load(from(required(map[string]string{"PG_WEBHOOK_SECRET": "too-short-secret"})))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	if strings.Contains(err.Error(), "too-short-secret") {
		t.Errorf("오류에 비밀이 실렸다: %v", err)
	}
}

func TestLoadAcceptsDeployedVersions(t *testing.T) {
	// git SHA, 태그, 이미지 태그의 모양이다
	for _, version := range []string{"3f2a9c1", "v1.2.3", "1.2.3-rc.1+build.5", "2026-10-11_main"} {
		settings, err := config.Load(from(required(map[string]string{"APP_VERSION": version})))
		if err != nil || settings.AppVersion != version {
			t.Errorf("APP_VERSION=%q 를 받지 않았다: %v", version, err)
		}
	}
}

func TestTheSameSecretInBothPlacesIsRejectedWithoutPrintingIt(t *testing.T) {
	_, err := config.Load(from(required(map[string]string{"GAME_SERVER_SECRET": webhookSecret})))

	if err == nil || strings.Contains(err.Error(), webhookSecret) {
		t.Errorf("오류 = %v. 거절하되 값은 싣지 않아야 한다", err)
	}
	// 둘 다 빠졌을 때는 "같다"가 아니라 "없다"만 말한다. 빈 값 둘이 같다고 하면 무엇을 고칠지 헷갈린다
	neither := without("GAME_SERVER_SECRET")
	delete(neither, "PG_WEBHOOK_SECRET")
	delete(neither, "AUTH_SERVER_SECRET")
	_, err = config.Load(from(neither))
	if err == nil || strings.Contains(err.Error(), "서로 다른 값") {
		t.Errorf("오류 = %v", err)
	}
}

func TestLoadRejectsValuesThatWouldBreakALogLine(t *testing.T) {
	// 이 값들은 모든 로그 줄에 실린다. 줄바꿈이나 따옴표가 든 값은 서버가 뜨기 전에 막는다
	cases := map[string][]string{
		"APP_ENVIRONMENT": {"Production", "prod env", "prod\n{\"level\":\"error\"}", "1prod", strings.Repeat("a", 33)},
		"APP_VERSION":     {"v1 beta", "v1\nforged", "v1/2", "\"quoted\"", strings.Repeat("a", 65)},
		"LOG_LEVEL":       {"INFO", "verbose", "trace", "info\n"},
	}
	for name, values := range cases {
		for _, value := range values {
			_, err := config.Load(from(required(map[string]string{name: value})))
			if err == nil || !strings.Contains(err.Error(), name) {
				t.Errorf("%s=%q 를 받았다: %v", name, value, err)
				continue
			}
			// 오류는 시작할 때 로그에 찍힌다. 받은 값을 싣지 않는다
			if strings.Contains(err.Error(), value) {
				t.Errorf("오류에 받은 값이 실렸다: %v", err)
			}
		}
	}
}

func TestLoadPaymentAcceptsBothKindsOfTestKeys(t *testing.T) {
	// 결제위젯 키(gsk, gck)와 API 개별 연동 키(sk, ck)를 받는다. 문서에 공개된 키도 같은 모양이다
	pairs := map[string]string{
		"test_gsk_docs_abc123": "test_gck_docs_abc123",
		"test_sk_abc123":       "test_ck_abc123",
	}
	for secretKey, clientKey := range pairs {
		settings, err := config.Load(from(required(map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": secretKey, "TOSS_CLIENT_KEY": clientKey,
		})))
		want := config.Payment{Provider: "toss", TossSecretKey: secretKey, TossClientKey: clientKey}
		if err != nil || settings.Payment != want {
			t.Errorf("%s, %s: 설정 = %+v, %v", secretKey, clientKey, settings.Payment, err)
		}
	}
}

func TestLoadPaymentFakeIgnoresTossKeys(t *testing.T) {
	// 가짜를 꽂으면 토스페이먼츠의 키는 읽지 않는다. 틀린 값이 있어도 서버는 뜬다
	settings, err := config.Load(from(required(map[string]string{
		"PAYMENT_PROVIDER": "fake", "TOSS_SECRET_KEY": "live_gsk_nope", "TOSS_CLIENT_KEY": "nope",
	})))
	if err != nil || settings.Payment != (config.Payment{Provider: "fake"}) {
		t.Errorf("설정 = %+v, %v", settings.Payment, err)
	}
}

func TestProductionRefusesTheFakeProvider(t *testing.T) {
	// #153: 가짜는 결제 번호의 앞머리만으로 승인한다. 운영에서 뜨면 누구나 크레딧을 얻는다.
	// 고르지 않아도 기본값이 가짜라 함께 막힌다. 서버와 작업 명령 모두다
	for name, values := range map[string]map[string]string{
		"가짜를 골랐다":    {"APP_ENVIRONMENT": "production", "PAYMENT_PROVIDER": "fake"},
		"아무것도 안 골랐다": {"APP_ENVIRONMENT": "production"},
	} {
		t.Run(name, func(t *testing.T) {
			_, serverErr := config.Load(from(required(values)))
			_, jobsErr := config.LoadJobs(from(required(values)))
			if !errors.Is(serverErr, config.ErrFakeInProduction) || !errors.Is(jobsErr, config.ErrFakeInProduction) {
				t.Errorf("서버 = %v, 작업 = %v. ErrFakeInProduction 이어야 한다", serverErr, jobsErr)
			}
		})
	}
}

func TestProductionAcceptsTossAndOtherEnvironmentsAcceptTheFake(t *testing.T) {
	toss := map[string]string{
		"APP_ENVIRONMENT": "production", "PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": tossClientKey,
	}
	if _, err := config.Load(from(required(toss))); err != nil {
		t.Errorf("운영의 토스페이먼츠 테스트 모드 = %v", err)
	}
	for _, environment := range []string{"development", "staging", "ci"} {
		if _, err := config.Load(from(required(map[string]string{"APP_ENVIRONMENT": environment}))); err != nil {
			t.Errorf("%s 의 가짜 = %v", environment, err)
		}
	}
}

func TestLoadPaymentRejectsBadTossSettings(t *testing.T) {
	cases := []struct {
		name   string
		values map[string]string
		// wantName 은 오류에 있어야 하는 설정의 이름이다
		wantName string
	}{
		{"모르는 결제 대행사", map[string]string{"PAYMENT_PROVIDER": "stripe"}, "PAYMENT_PROVIDER"},
		{"시크릿 키가 없다", map[string]string{"PAYMENT_PROVIDER": "toss", "TOSS_CLIENT_KEY": tossClientKey}, "TOSS_SECRET_KEY"},
		{"클라이언트 키가 없다", map[string]string{"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey}, "TOSS_CLIENT_KEY"},
		{"라이브 시크릿 키", map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": "live_gsk_doNotPrintThisSecretKey01", "TOSS_CLIENT_KEY": tossClientKey,
		}, "TOSS_SECRET_KEY"},
		{"라이브 클라이언트 키", map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": "live_gck_publicClientKey01",
		}, "TOSS_CLIENT_KEY"},
		{"자리가 바뀐 키", map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossClientKey, "TOSS_CLIENT_KEY": tossSecretKey,
		}, "TOSS_SECRET_KEY"},
		{"종류가 다른 키", map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": "test_ck_publicClientKey01",
		}, "같은 종류"},
		{"빈칸이 든 키", map[string]string{
			"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey + " ", "TOSS_CLIENT_KEY": tossClientKey,
		}, "TOSS_SECRET_KEY"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, serverErr := config.Load(from(required(tc.values)))
			_, jobsErr := config.LoadJobs(from(required(tc.values)))

			for _, err := range []error{serverErr, jobsErr} {
				if err == nil || !strings.Contains(err.Error(), tc.wantName) {
					t.Fatalf("오류 = %v. %s 가 들어 있어야 한다", err, tc.wantName)
				}
				// 시크릿 키는 오류에 싣지 않는다. 잘못 넣은 라이브 키도 진짜 비밀이다
				if strings.Contains(err.Error(), "doNotPrintThisSecretKey") {
					t.Errorf("오류에 시크릿 키가 실렸다: %v", err)
				}
			}
		})
	}
}

func TestCheckoutClientKeyOnlyInDebugWithToss(t *testing.T) {
	toss := map[string]string{"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": tossClientKey}
	cases := []struct {
		name   string
		values map[string]string
		want   string
	}{
		{"개발 모드의 토스페이먼츠", merge(toss, map[string]string{"DEBUG": "true"}), tossClientKey},
		{"운영 모드의 토스페이먼츠", merge(toss, map[string]string{"DEBUG": "false"}), ""},
		{"개발 모드의 가짜", map[string]string{"DEBUG": "true"}, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			settings, err := config.Load(from(required(tc.values)))
			if err != nil {
				t.Fatalf("설정을 읽지 못했다: %v", err)
			}
			if got := settings.CheckoutClientKey(); got != tc.want {
				t.Errorf("CheckoutClientKey = %q, 기대 = %q", got, tc.want)
			}
		})
	}
}

func TestCheckoutClientKeyNeedsTossEvenIfAKeyIsThere(t *testing.T) {
	// 가짜를 꽂았으면 키가 남아 있어도 화면을 열지 않는다
	settings := config.Settings{Debug: true, Payment: config.Payment{Provider: "fake", TossClientKey: tossClientKey}}
	if got := settings.CheckoutClientKey(); got != "" {
		t.Errorf("CheckoutClientKey = %q, 기대 = 빈 글자", got)
	}
}

// merge 는 두 맵을 합친 새 맵을 돌려준다. 같은 이름이면 뒤의 것이 이긴다.
func merge(first map[string]string, second map[string]string) map[string]string {
	merged := map[string]string{}
	for _, values := range []map[string]string{first, second} {
		for name, value := range values {
			merged[name] = value
		}
	}
	return merged
}

func TestTossNotificationsOnlyWithToss(t *testing.T) {
	toss := map[string]string{"PAYMENT_PROVIDER": "toss", "TOSS_SECRET_KEY": tossSecretKey, "TOSS_CLIENT_KEY": tossClientKey}
	cases := []struct {
		name   string
		values map[string]string
		want   bool
	}{
		// 개발 모드가 아니어도 받는다. 알림은 개발용 화면이 아니다
		{"운영 모드의 토스페이먼츠", merge(toss, map[string]string{"DEBUG": "false"}), true},
		{"개발 모드의 토스페이먼츠", merge(toss, map[string]string{"DEBUG": "true"}), true},
		{"가짜", map[string]string{"DEBUG": "true"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			settings, err := config.Load(from(required(tc.values)))
			if err != nil {
				t.Fatalf("설정을 읽지 못했다: %v", err)
			}
			if got := settings.ReceivesTossNotifications(); got != tc.want {
				t.Errorf("ReceivesTossNotifications = %v, 기대 = %v", got, tc.want)
			}
		})
	}
}
