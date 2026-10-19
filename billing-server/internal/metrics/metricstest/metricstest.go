// billing-server/internal/metrics/metricstest/metricstest.go

// Package metricstest 는 테스트가 계측한 값을 읽게 한다. 메모리에 모으는 것(ManualReader)으로 Meter 를 만들고,
// 이름과 label 로 값을 찾는다. 보내는 일(OTLP)은 하지 않는다. 끝에서 끝까지는 CI 의 stack 이 본다.
package metricstest

import (
	"context"
	"testing"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// Recorder 는 테스트 하나의 계측을 모은다.
type Recorder struct {
	t      testing.TB
	reader *sdkmetric.ManualReader
	meter  metric.Meter
}

// New 는 메모리에 모으는 Meter 를 만든다.
func New(t testing.TB) *Recorder {
	t.Helper()
	reader := sdkmetric.NewManualReader()
	provider := sdkmetric.NewMeterProvider(sdkmetric.WithReader(reader))
	t.Cleanup(func() { _ = provider.Shutdown(context.Background()) })
	return &Recorder{t: t, reader: reader, meter: provider.Meter(metrics.ScopeName)}
}

// Meter 는 계측하는 코드에 넘길 Meter 다.
func (r *Recorder) Meter() metric.Meter {
	return r.meter
}

// Find 는 그 이름의 메트릭을 지금 모은 값에서 찾는다. 없으면 테스트를 멈춘다.
func (r *Recorder) Find(name string) metricdata.Metrics {
	r.t.Helper()
	found, ok := r.lookup(name)
	if !ok {
		r.t.Fatalf("메트릭 %s 가 없다. 있는 것: %v", name, r.Names())
	}
	return found
}

// Has 는 그 이름의 메트릭이 있는지 본다.
func (r *Recorder) Has(name string) bool {
	r.t.Helper()
	_, ok := r.lookup(name)
	return ok
}

// Names 는 지금 모은 메트릭의 이름들이다.
func (r *Recorder) Names() []string {
	r.t.Helper()
	var names []string
	for _, scope := range r.collect().ScopeMetrics {
		for _, found := range scope.Metrics {
			names = append(names, found.Name)
		}
	}
	return names
}

// lookup 은 이름으로 메트릭 하나를 찾는다.
func (r *Recorder) lookup(name string) (metricdata.Metrics, bool) {
	for _, scope := range r.collect().ScopeMetrics {
		for _, found := range scope.Metrics {
			if found.Name == name {
				return found, true
			}
		}
	}
	return metricdata.Metrics{}, false
}

// collect 는 지금까지 모은 값을 읽는다.
func (r *Recorder) collect() metricdata.ResourceMetrics {
	r.t.Helper()
	var collected metricdata.ResourceMetrics
	if err := r.reader.Collect(context.Background(), &collected); err != nil {
		r.t.Fatalf("메트릭을 모으지 못했다: %v", err)
	}
	return collected
}

// Int64 는 정수 메트릭(counter, up-down counter, gauge)에서 label 이 꼭 맞는 점의 값이다. 없으면 테스트를 멈춘다.
func (r *Recorder) Int64(name string, attrs ...attribute.KeyValue) int64 {
	r.t.Helper()
	want := attribute.NewSet(attrs...)
	for _, point := range int64Points(r.t, r.Find(name)) {
		if point.Attributes.Equals(&want) {
			return point.Value
		}
	}
	r.t.Fatalf("메트릭 %s 에 label %v 인 점이 없다", name, want.ToSlice())
	return 0
}

// HasPoint 는 정수 메트릭에 label 이 꼭 맞는 점이 있는지 본다. 메트릭이 아직 없으면 점도 없다.
func (r *Recorder) HasPoint(name string, attrs ...attribute.KeyValue) bool {
	r.t.Helper()
	found, ok := r.lookup(name)
	if !ok {
		return false
	}
	want := attribute.NewSet(attrs...)
	for _, point := range int64Points(r.t, found) {
		if point.Attributes.Equals(&want) {
			return true
		}
	}
	return false
}

// HistogramCount 는 히스토그램에서 label 이 꼭 맞는 점이 센 수다. 없으면 테스트를 멈춘다.
func (r *Recorder) HistogramCount(name string, attrs ...attribute.KeyValue) uint64 {
	r.t.Helper()
	want := attribute.NewSet(attrs...)
	histogram, ok := r.Find(name).Data.(metricdata.Histogram[float64])
	if !ok {
		r.t.Fatalf("메트릭 %s 가 실수 히스토그램이 아니다", name)
	}
	for _, point := range histogram.DataPoints {
		if point.Attributes.Equals(&want) {
			return point.Count
		}
	}
	r.t.Fatalf("메트릭 %s 에 label %v 인 점이 없다", name, want.ToSlice())
	return 0
}

// Bounds 는 히스토그램의 구간이다. 점이 없으면 테스트를 멈춘다.
func (r *Recorder) Bounds(name string) []float64 {
	r.t.Helper()
	histogram, ok := r.Find(name).Data.(metricdata.Histogram[float64])
	if !ok || len(histogram.DataPoints) == 0 {
		r.t.Fatalf("메트릭 %s 가 점이 있는 실수 히스토그램이 아니다", name)
	}
	return histogram.DataPoints[0].Bounds
}

// int64Points 는 정수 메트릭의 점들이다.
func int64Points(t testing.TB, found metricdata.Metrics) []metricdata.DataPoint[int64] {
	t.Helper()
	switch data := found.Data.(type) {
	case metricdata.Sum[int64]:
		return data.DataPoints
	case metricdata.Gauge[int64]:
		return data.DataPoints
	default:
		t.Fatalf("메트릭 %s 가 정수 메트릭이 아니다(%T)", found.Name, found.Data)
		return nil
	}
}
