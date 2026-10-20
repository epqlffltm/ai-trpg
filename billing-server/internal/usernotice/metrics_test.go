// billing-server/internal/usernotice/metrics_test.go

// 사용자의 알림함에 보낼 일을 종류와 결과로 세는지 시험한다(billing_user_notices_total). store_test.go 의 fixture 를 쓴다.
// 이름과 label 은 저장소 루트의 docs/observability.md 의 "결제 (billing)" 표에 있다.
package usernotice_test

import (
	"context"
	"testing"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/metrics/metricstest"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
)

// measure 는 정리 작업의 것(f.notices)과 서버의 것(f.services.UserNotices)이 센 것을 메모리에 모은다.
func (f fixture) measure() *metricstest.Recorder {
	f.t.Helper()
	recorder := metricstest.New(f.t)
	for _, service := range []*usernotice.Service{f.notices, f.services.UserNotices} {
		if err := service.Measure(recorder.Meter()); err != nil {
			f.t.Fatalf("알림의 메트릭을 만들지 못했다: %v", err)
		}
	}
	return recorder
}

// notices 는 그 종류와 결과의 수다. 세지 않았으면 0 이다.
func notices(recorder *metricstest.Recorder, kind usernotice.Kind, outcome string) int64 {
	labels := []attribute.KeyValue{attribute.String("kind", string(kind)), attribute.String("outcome", outcome)}
	if !recorder.HasPoint("billing_user_notices", labels...) {
		return 0
	}
	return recorder.Int64("billing_user_notices", labels...)
}

func TestQueuedAndSentNoticesAreCountedByKind(t *testing.T) {
	f := setUp(t)
	recorder := f.measure()
	f.paid(f.user())

	f.round()

	// 같은 스키마에 다른 테스트의 줄이 있을 수 있어 적어도 하나다
	if notices(recorder, usernotice.KindOrderPaid, usernotice.OutcomeQueued) < 1 {
		t.Errorf("적은 결제의 수가 없다: %v", recorder.Names())
	}
	if notices(recorder, usernotice.KindOrderPaid, usernotice.OutcomeSent) < 1 {
		t.Errorf("보낸 결제의 수가 없다")
	}
}

func TestUnsentNoticesAreCountedAsRetriedOrRejected(t *testing.T) {
	f := setUp(t)
	recorder := f.measure()
	user := f.user()
	if err := f.notices.RecordShort(context.Background(), user, "narration.standard", 50, false); err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}
	// 앞 테스트가 남긴 줄이 먼저 나갈 수 있다. 모두 닿지 못한 것으로 답한 뒤, 다음 바퀴는 모두 받지 않는다
	f.sender.answers = repeat(usernotice.Sent{Delivery: usernotice.Unavailable, Reason: "status_503"}, 1000)
	f.round()
	f.clock.now = f.clock.now.Add(time.Hour)
	f.sender.answers = repeat(usernotice.Sent{Delivery: usernotice.Rejected, Reason: "status_422"}, 1000)
	f.round()

	if notices(recorder, usernotice.KindCreditsShort, usernotice.OutcomeRetried) < 1 {
		t.Errorf("다시 보낼 것의 수가 없다")
	}
	if notices(recorder, usernotice.KindCreditsShort, usernotice.OutcomeRejected) < 1 {
		t.Errorf("받지 않은 것의 수가 없다")
	}
}

func TestAShortHoldIsCountedOnceAndThenAsDuplicate(t *testing.T) {
	f := setUp(t)
	recorder := f.measure()
	user := f.user()

	f.short(user)
	f.short(user)

	if got := notices(recorder, usernotice.KindCreditsShort, usernotice.OutcomeQueued); got != 1 {
		t.Errorf("적은 크레딧 부족 = %d, 기대 = 1", got)
	}
	if got := notices(recorder, usernotice.KindCreditsShort, usernotice.OutcomeDuplicate); got != 1 {
		t.Errorf("같은 날 다시 모자란 것 = %d, 기대 = 1", got)
	}
}

// repeat 는 같은 답을 n 개 늘어놓는다.
func repeat(answer usernotice.Sent, n int) []usernotice.Sent {
	answers := make([]usernotice.Sent, n)
	for i := range answers {
		answers[i] = answer
	}
	return answers
}
