// billing-server/cmd/autocharge/main_test.go

package main

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
)

// fakeRounder 는 정해 둔 답으로 바퀴를 도는 가짜다. stopAfter 바퀴를 돌면 cancel 을 부른다.
type fakeRounder struct {
	mu        sync.Mutex
	rounds    int
	limit     int
	stopAfter int
	cancel    context.CancelFunc
	err       error
}

func (f *fakeRounder) ChargeRound(_ context.Context, limit int) (autocharge.ChargeResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.rounds++
	f.limit = limit
	if f.rounds >= f.stopAfter {
		f.cancel()
	}
	return autocharge.ChargeResult{Paid: 1}, f.err
}

func TestParseOptions(t *testing.T) {
	defaults, defaultsErr := parseOptions(nil)
	every, everyErr := parseOptions([]string{"-once", "-interval", "2m", "-limit", "20"})

	if defaultsErr != nil || defaults != (options{interval: defaultInterval, limit: defaultLimit}) {
		t.Errorf("기본 = %+v, %v", defaults, defaultsErr)
	}
	if everyErr != nil || every != (options{interval: 2 * time.Minute, once: true, limit: 20}) {
		t.Errorf("모두 = %+v, %v", every, everyErr)
	}
	for _, bad := range [][]string{{"-interval", "10ms"}, {"-limit", "0"}, {"extra"}, {"-unknown"}} {
		if _, err := parseOptions(bad); err == nil {
			t.Errorf("%v: 오류여야 한다", bad)
		}
	}
}

func TestTheLoopKeepsGoingAfterAFailedRound(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	charger := &fakeRounder{stopAfter: 3, cancel: cancel, err: errors.New("DB 가 끊겼다")}

	loop(ctx, charger, time.Millisecond, 7, "")

	if charger.rounds != 3 || charger.limit != 7 {
		t.Errorf("바퀴 = %d, limit = %d", charger.rounds, charger.limit)
	}
}

func TestTheLoopBeatsOnlyAfterASuccessfulRound(t *testing.T) {
	// 심장박동은 DB 에 닿아 끝낸 바퀴만 남긴다. healthy 가 "DB 에 닿으며 돈다"는 뜻이 된다
	cases := map[string]struct {
		err       error
		wantBeats bool
	}{
		"성공한 바퀴": {err: nil, wantBeats: true},
		"실패한 바퀴": {err: errors.New("db is down"), wantBeats: false},
	}
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			charger := &fakeRounder{stopAfter: 1, cancel: cancel, err: c.err}
			heartbeat := filepath.Join(t.TempDir(), "heartbeat")

			loop(ctx, charger, time.Hour, 1, heartbeat)

			_, statErr := os.Stat(heartbeat)
			if beat := statErr == nil; beat != c.wantBeats {
				t.Errorf("심장박동 = %v, 기대 = %v", beat, c.wantBeats)
			}
		})
	}
}

func TestTheLoopKeepsGoingWhenTheHeartbeatCannotBeWritten(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	charger := &fakeRounder{stopAfter: 2, cancel: cancel}

	loop(ctx, charger, time.Millisecond, 1, filepath.Join(t.TempDir(), "no-such-folder", "heartbeat"))

	if charger.rounds != 2 {
		t.Errorf("바퀴 = %d, 기대 = 2", charger.rounds)
	}
}

func TestPrintResultShowsTheCounts(t *testing.T) {
	var out bytes.Buffer
	printResult(&out, autocharge.ChargeResult{Paid: 1, Declined: 2, Skipped: 3, Retried: 4, LookedUp: 5})

	for _, want := range []string{"결제함: 1", "거절됨: 2", "그만둠: 3", "다시 보낼 것: 4", "주문 번호로 조회함: 5"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("화면 = %q, %q 가 없다", out.String(), want)
		}
	}
}
