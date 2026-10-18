// billing-server/internal/usernotice/store_internal_test.go

package usernotice

import (
	"testing"
	"time"
)

func TestTheWaitDoublesUpToAnHour(t *testing.T) {
	for attempts, want := range map[int]time.Duration{
		0: 5 * time.Second, 1: 5 * time.Second, 2: 10 * time.Second, 3: 20 * time.Second,
		10: 2560 * time.Second, 11: time.Hour, 50: time.Hour,
	} {
		if got := retryDelay(attempts); got != want {
			t.Errorf("%d 번 뒤: %s, 기대 = %s", attempts, got, want)
		}
	}
}

func TestALongErrorIsCutWithoutBreakingALetter(t *testing.T) {
	if got := cut("짧다", 10); got != "짧다" {
		t.Errorf("짧은 글 = %q", got)
	}
	// 한글은 3바이트다. 7바이트 안에는 두 글자만 든다
	if got := cut("알림서버", 7); got != "알림" {
		t.Errorf("자른 글 = %q", got)
	}
}

func TestAnEmptyRoundIsNothing(t *testing.T) {
	if (Result{}).Any() {
		t.Error("한 일이 없는데 있다고 한다")
	}
	for _, result := range []Result{{Queued: 1}, {Sent: 1}, {Retried: 1}, {Rejected: 1}, {Expired: 1}, {Purged: 1}} {
		if !result.Any() {
			t.Errorf("%+v: 한 일이 있는데 없다고 한다", result)
		}
	}
}
