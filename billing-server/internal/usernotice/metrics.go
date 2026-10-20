// billing-server/internal/usernotice/metrics.go

package usernotice

import (
	"context"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics"
)

// 사용자의 알림함에 보낼 일을 종류(kind)와 결과(outcome)로 센다(billing_user_notices_total).
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
//
// 적은 것(queued)은 정리 작업이 찾아 적은 것과 서버가 402 의 자리에서 적은 크레딧 부족(credit.short)을 함께 센다.
// 바퀴의 로그(user_notices_queued)는 정리 작업이 적은 것만 센다. 크레딧 부족이 몇 번 나가는지는 이것으로 본다.
// 오래되어 보내지 않은 것(expired)과 지운 것(purged)은 세지 않는다. 종류를 모르고 바퀴의 로그에 수가 있다.

// metricUserNotices 는 계측기의 이름이다. 수집기가 _total 을 붙인다.
const metricUserNotices = "billing_user_notices"

// 알릴 일의 결과(label outcome).
const (
	// OutcomeQueued 는 새로 적었다는 것이다.
	OutcomeQueued = "queued"
	// OutcomeDuplicate 는 같은 사람의 같은 날 크레딧 부족을 이미 적어 적지 않았다는 것이다(credit.short 만).
	OutcomeDuplicate = "duplicate"
	// OutcomeSent 는 알림 서버가 받았다는 것이다.
	OutcomeSent = "sent"
	// OutcomeRetried 는 닿지 못해 다시 보낼 것이라는 것이다.
	OutcomeRetried = "retried"
	// OutcomeRejected 는 알림 서버가 받지 않았다는 것이다. 버그다.
	OutcomeRejected = "rejected"
)

// newNoticeCounter 는 알릴 일을 세는 계측기를 만든다. meter 가 없으면 세지 않는다.
func newNoticeCounter(meter metric.Meter) (metric.Int64Counter, error) {
	return metrics.MeterOrNoop(meter).Int64Counter(metricUserNotices,
		metric.WithDescription("사용자의 알림함에 보낼 일. kind 는 알림의 종류, outcome 은 queued, duplicate, sent, retried, rejected 다"))
}

// noNoticeCounter 는 세지 않는 계측기다. Measure 를 부르기 전의 값이다.
func noNoticeCounter() metric.Int64Counter {
	unmeasured, _ := newNoticeCounter(nil)
	return unmeasured
}

// Measure 는 이 서비스가 적고 보낸 일을 meter 로 세게 한다. 서비스를 쓰기 전에 한 번 부른다.
func (s *Service) Measure(meter metric.Meter) error {
	counter, err := newNoticeCounter(meter)
	if err != nil {
		return err
	}
	s.notices = counter
	return nil
}

// count 는 그 종류의 일 n 개를 outcome 으로 센다. 0 개면 세지 않는다(점을 만들지 않는다).
func (s *Service) count(ctx context.Context, kind Kind, outcome string, n int64) {
	if n <= 0 {
		return
	}
	s.notices.Add(ctx, n, metric.WithAttributes(attribute.String("kind", string(kind)), attribute.String("outcome", outcome)))
}

// deliveryOutcome 은 보낸 결과를 label outcome 의 값으로 바꾼다.
func deliveryOutcome(delivery Delivery) string {
	switch delivery {
	case Delivered:
		return OutcomeSent
	case Unavailable:
		return OutcomeRetried
	default:
		return OutcomeRejected
	}
}
