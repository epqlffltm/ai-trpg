// billing-server/internal/config/config_test.go

package config_test

import (
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
)

// 테스트용 접속 주소. 실제로 접속하지 않는다. 비밀번호 자리의 글자가 오류에 새는지 볼 때 쓴다.
const (
	secret      = "do-not-print-me"
	databaseURL = "postgres://billing:" + secret + "@127.0.0.1:5432/trpg"
)

// from 은 맵을 설정을 찾는 함수로 바꾼다. 실제 환경 변수를 읽지 않는다.
func from(values map[string]string) config.Lookup {
	return func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}
}

func TestLoadFillsDefaults(t *testing.T) {
	settings, err := config.Load(from(map[string]string{"DATABASE_URL": databaseURL}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}

	want := config.Settings{
		Debug:       false,
		Host:        "127.0.0.1",
		Port:        8003,
		DatabaseURL: databaseURL,
		DBSchema:    "billing",
	}
	if settings != want {
		t.Errorf("설정 = %+v, 기대 = %+v", settings, want)
	}
}

func TestLoadReadsEveryValue(t *testing.T) {
	settings, err := config.Load(from(map[string]string{
		"DEBUG":        "true",
		"HOST":         "0.0.0.0",
		"PORT":         "9000",
		"DATABASE_URL": databaseURL,
		"DB_SCHEMA":    "billing_test",
	}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}

	want := config.Settings{Debug: true, Host: "0.0.0.0", Port: 9000, DatabaseURL: databaseURL, DBSchema: "billing_test"}
	if settings != want {
		t.Errorf("설정 = %+v, 기대 = %+v", settings, want)
	}
	if settings.Addr() != "0.0.0.0:9000" {
		t.Errorf("주소 = %q, 기대 = %q", settings.Addr(), "0.0.0.0:9000")
	}
}

func TestLoadTreatsEmptyAsMissing(t *testing.T) {
	// .env 에 이름만 적고 값을 비워 둔 줄은 적지 않은 것과 같다
	settings, err := config.Load(from(map[string]string{
		"DEBUG": "", "HOST": "", "PORT": "", "DB_SCHEMA": "", "DATABASE_URL": databaseURL,
	}))
	if err != nil {
		t.Fatalf("설정을 읽지 못했다: %v", err)
	}
	if settings.Port != config.DefaultPort || settings.DBSchema != config.DefaultSchema || settings.Debug {
		t.Errorf("빈 값이 기본값으로 채워지지 않았다: %+v", settings)
	}
}

func TestLoadRejectsBadValues(t *testing.T) {
	cases := []struct {
		name   string
		values map[string]string
		want   string
	}{
		{"접속 주소가 없다", map[string]string{}, "DATABASE_URL"},
		{"접속 주소가 비었다", map[string]string{"DATABASE_URL": ""}, "DATABASE_URL"},
		{"참거짓이 아니다", map[string]string{"DATABASE_URL": databaseURL, "DEBUG": "yes please"}, "DEBUG"},
		{"포트가 숫자가 아니다", map[string]string{"DATABASE_URL": databaseURL, "PORT": "http"}, "PORT"},
		{"포트가 0 이다", map[string]string{"DATABASE_URL": databaseURL, "PORT": "0"}, "PORT"},
		{"포트가 너무 크다", map[string]string{"DATABASE_URL": databaseURL, "PORT": "65536"}, "PORT"},
		{"스키마에 대문자", map[string]string{"DATABASE_URL": databaseURL, "DB_SCHEMA": "Billing"}, "DB_SCHEMA"},
		{"스키마에 쉼표", map[string]string{"DATABASE_URL": databaseURL, "DB_SCHEMA": "billing,auth"}, "DB_SCHEMA"},
		{"스키마에 따옴표", map[string]string{"DATABASE_URL": databaseURL, "DB_SCHEMA": `billing"; --`}, "DB_SCHEMA"},
		{"스키마가 숫자로 시작", map[string]string{"DATABASE_URL": databaseURL, "DB_SCHEMA": "1billing"}, "DB_SCHEMA"},
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

func TestLoadReportsEveryProblemAtOnce(t *testing.T) {
	_, err := config.Load(from(map[string]string{"PORT": "nope", "DEBUG": "nope", "DB_SCHEMA": "NOPE"}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}

	// 하나를 고치고 다시 띄워 다음 것을 만나는 일을 줄인다
	for _, name := range []string{"DATABASE_URL", "PORT", "DEBUG", "DB_SCHEMA"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("오류에 %s 가 없다: %v", name, err)
		}
	}
}

func TestLoadNeverPrintsValues(t *testing.T) {
	// 다른 값이 틀려서 오류가 나도 접속 주소의 비밀번호는 오류에 실리지 않는다
	_, err := config.Load(from(map[string]string{"DATABASE_URL": databaseURL, "PORT": "nope"}))
	if err == nil {
		t.Fatal("오류가 나야 하는데 나지 않았다")
	}
	if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), "nope") {
		t.Errorf("오류에 설정의 값이 실렸다: %v", err)
	}
}
