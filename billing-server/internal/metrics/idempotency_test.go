// billing-server/internal/metrics/idempotency_test.go

package metrics_test

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
)

// errReused 는 테스트의 "같은 키에 다른 내용" 오류다.
var errReused = errors.New("reused")

func TestIdempotencyOutcomeNamesWhatTheKeyDid(t *testing.T) {
	cases := []struct {
		name    string
		created bool
		err     error
		want    string
		counted bool
	}{
		{"새로 만들었다", true, nil, "first", true},
		{"먼저 것을 돌려줬다", false, nil, "replayed", true},
		{"같은 키에 다른 내용", false, errReused, "conflict", true},
		{"감싼 다른 내용", false, fmt.Errorf("place: %w", errReused), "conflict", true},
		// 키를 보기 전에 끝났다(모양이 틀린 키, 모자란 크레딧, DB 오류). 키의 결과가 아니다
		{"그 밖의 오류", false, errors.New("connection refused"), "", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, counted := metrics.IdempotencyOutcome(tc.created, tc.err, errReused)
			if got != tc.want || counted != tc.counted {
				t.Errorf("결과 = %q, %v. 기대 = %q, %v", got, counted, tc.want, tc.counted)
			}
		})
	}
}

func TestOrdersAndHoldsShareOneIdempotencyCounter(t *testing.T) {
	// 두 곳이 따로 만들어도 같은 계측기다. 설명이 달라 둘이 되면 수집기에서 이름이 겹친다
	recorder := metricstest.New(t)
	orders, err := metrics.NewIdempotency(recorder.Meter())
	if err != nil {
		t.Fatalf("계측기를 만들지 못했다: %v", err)
	}
	holds, err := metrics.NewIdempotency(recorder.Meter())
	if err != nil {
		t.Fatalf("계측기를 만들지 못했다: %v", err)
	}

	orders.Count(context.Background(), "order", true, nil, errReused)
	holds.Count(context.Background(), "hold", false, nil, errReused)

	if names := recorder.Names(); len(names) != 1 || names[0] != "billing_idempotency" {
		t.Fatalf("메트릭 = %v. billing_idempotency 하나여야 한다", names)
	}
	first := recorder.Int64("billing_idempotency", attribute.String("kind", "order"), attribute.String("outcome", "first"))
	replayed := recorder.Int64("billing_idempotency", attribute.String("kind", "hold"), attribute.String("outcome", "replayed"))
	if first != 1 || replayed != 1 {
		t.Errorf("order/first = %d, hold/replayed = %d. 1, 1 이어야 한다", first, replayed)
	}
}
