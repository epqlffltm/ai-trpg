// billing-server/internal/config/metrics_test.go

package config_test

import (
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
)

// 메트릭을 보낼 곳과 간격(LoadMetrics)을 본다. docs/observability.md 의 "계측기를 만드는 법"에 적은 값이다.

func TestMetricsAreOffWithoutAnEndpoint(t *testing.T) {
	// PC 에서 직접 띄운 서버와 app 프로필만 켠 compose 는 보낼 곳이 없다. 없는 주소로 보내며 오류를 남기지 않는다
	for name, values := range map[string]map[string]string{
		"없다":    {},
		"빈 글자다": {"OTEL_EXPORTER_OTLP_ENDPOINT": ""},
	} {
		t.Run(name, func(t *testing.T) {
			got, err := config.LoadMetrics(from(values))
			if err != nil || got.Endpoint != "" || got.Interval != config.DefaultMetricInterval {
				t.Errorf("설정 = %+v, 오류 = %v", got, err)
			}
		})
	}
}

func TestMetricsReadTheCollectorAndTheInterval(t *testing.T) {
	got, err := config.LoadMetrics(from(map[string]string{
		"OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy:4318/",
		"OTEL_METRIC_EXPORT_INTERVAL": "30000",
	}))

	// 끝의 / 는 뗀다. 보내는 쪽이 /v1/metrics 를 붙인다
	want := config.Metrics{Endpoint: "http://alloy:4318", Interval: 30 * time.Second}
	if err != nil || got != want {
		t.Errorf("설정 = %+v, 오류 = %v. %+v 여야 한다", got, err, want)
	}
}

func TestTheDefaultIntervalIsFifteenSeconds(t *testing.T) {
	// SDK 의 기본(60초)이면 rate(…[1m]) 에 점이 하나뿐이다
	if config.DefaultMetricInterval != 15*time.Second {
		t.Errorf("기본 간격 = %s", config.DefaultMetricInterval)
	}
}

func TestMetricsRejectBadValues(t *testing.T) {
	cases := map[string]map[string]string{
		"주소의 모양이 아니다": {"OTEL_EXPORTER_OTLP_ENDPOINT": "alloy:4318"},
		"http 가 아니다":  {"OTEL_EXPORTER_OTLP_ENDPOINT": "grpc://alloy:4317"},
		"경로를 붙였다":     {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://alloy:4318/v1/metrics"},
		"간격이 숫자가 아니다": {"OTEL_METRIC_EXPORT_INTERVAL": "15s"},
		"간격이 1초보다 짧다": {"OTEL_METRIC_EXPORT_INTERVAL": "999"},
		"간격이 0 이다":    {"OTEL_METRIC_EXPORT_INTERVAL": "0"},
	}
	for name, values := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := config.LoadMetrics(from(values)); err == nil {
				t.Errorf("%v 를 받았다", values)
			}
		})
	}
}
