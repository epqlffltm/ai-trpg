// billing-server/cmd/sweeper/main_test.go

package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/sweep"
)

// fakeRounder 는 정해 둔 답으로 바퀴를 도는 가짜다. stopAfter 바퀴를 돌면 cancel 을 부른다.
type fakeRounder struct {
	mu        sync.Mutex
	rounds    int
	stopAfter int
	cancel    context.CancelFunc
	err       error
}

func (f *fakeRounder) Round(context.Context) (sweep.Result, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.rounds++
	if f.rounds >= f.stopAfter {
		f.cancel()
	}
	return sweep.Result{Holds: 1}, f.err
}

func TestParseOptionsDefaults(t *testing.T) {
	opts, err := parseOptions(nil)
	if err != nil || opts != (options{interval: 30 * time.Second, once: false, limit: sweep.DefaultLimit}) {
		t.Errorf("옵션 = %+v, %v", opts, err)
	}
}

func TestParseOptionsReadsEveryFlag(t *testing.T) {
	opts, err := parseOptions([]string{"-once", "-interval", "2m", "-limit", "20"})
	if err != nil || opts != (options{interval: 2 * time.Minute, once: true, limit: 20}) {
		t.Errorf("옵션 = %+v, %v", opts, err)
	}
}

func TestParseOptionsRejectsBadValues(t *testing.T) {
	cases := [][]string{
		{"-interval", "10ms"},
		{"-interval", "soon"},
		{"-limit", "0"},
		{"-limit", "-3"},
		{"-unknown"},
		{"now"},
	}
	for _, args := range cases {
		if _, err := parseOptions(args); err == nil {
			t.Errorf("%v: 오류가 나야 한다", args)
		}
	}
}

func TestLoopKeepsGoingAfterAFailedRoundUntilCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	sweeper := &fakeRounder{stopAfter: 3, cancel: cancel, err: errors.New("db is down")}
	done := make(chan struct{})

	go func() {
		loop(ctx, sweeper, time.Millisecond)
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("끄라는 신호가 왔는데 멈추지 않았다")
	}
	if sweeper.rounds != 3 {
		t.Errorf("바퀴 = %d, 기대 = 3. 실패한 바퀴 뒤에도 돌아야 한다", sweeper.rounds)
	}
}

func TestLoopStopsWhileWaiting(t *testing.T) {
	// 바퀴 사이를 기다리는 중에 끄라는 신호가 오면 다음 바퀴를 기다리지 않고 멈춘다
	ctx, cancel := context.WithCancel(context.Background())
	sweeper := &fakeRounder{stopAfter: 1, cancel: cancel}
	started := time.Now()

	loop(ctx, sweeper, time.Hour)

	if time.Since(started) > 5*time.Second || sweeper.rounds != 1 {
		t.Errorf("바퀴 = %d, 걸린 시간 = %v", sweeper.rounds, time.Since(started))
	}
}

func TestPrintResultShowsTheCounts(t *testing.T) {
	var out bytes.Buffer
	printResult(&out, sweep.Result{Holds: 2, FreeCreditUsers: 1, Orders: 3})
	for _, want := range []string{"돌려준 홀드: 2", "무료 크레딧을 정리한 사용자: 1", "끝낸 주문: 3"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("화면 = %q, %q 가 없다", out.String(), want)
		}
	}
}
