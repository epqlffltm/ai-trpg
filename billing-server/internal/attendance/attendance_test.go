// billing-server/internal/attendance/attendance_test.go

package attendance

import (
	"testing"
	"time"
)

func day(month time.Month, d int) time.Time {
	return time.Date(2026, month, d, 0, 0, 0, 0, time.UTC)
}

func TestGrantKeysNameTheDay(t *testing.T) {
	if got := GrantKey(day(10, 18)); got != "attendance-20261018" {
		t.Fatalf("하루 양의 이름이 틀렸다: %s", got)
	}
	if got := ChestGrantKey(day(1, 2)); got != "chest-20260102" {
		t.Fatalf("상자의 이름이 틀렸다: %s", got)
	}
}
