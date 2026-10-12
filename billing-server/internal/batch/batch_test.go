// billing-server/internal/batch/batch_test.go

package batch_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/batch"
)

func TestEachCountsOnlyWhatChanged(t *testing.T) {
	changed, err := batch.Each(context.Background(), []int{1, 2, 3, 4}, func(_ context.Context, n int) (bool, error) {
		return n%2 == 0, nil
	})
	if changed != 2 || err != nil {
		t.Errorf("바꾼 수 = %d, 오류 = %v. 기대 = 2, 없음", changed, err)
	}
}

func TestEachKeepsGoingPastAFailure(t *testing.T) {
	// 맨 앞의 줄이 고장 나도 뒤의 줄은 처리한다
	var seen []int
	broken := errors.New("broken row")
	changed, err := batch.Each(context.Background(), []int{1, 2, 3}, func(_ context.Context, n int) (bool, error) {
		seen = append(seen, n)
		if n == 1 {
			return false, broken
		}
		return true, nil
	})
	if changed != 2 || len(seen) != 3 {
		t.Errorf("바꾼 수 = %d, 처리한 것 = %v", changed, seen)
	}
	if !errors.Is(err, broken) || !strings.Contains(err.Error(), "3 개 가운데 1 개") {
		t.Errorf("오류 = %v", err)
	}
}

func TestEachStopsWhenCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	calls := 0
	changed, err := batch.Each(ctx, []int{1, 2, 3}, func(_ context.Context, _ int) (bool, error) {
		calls++
		cancel()
		return true, nil
	})
	if calls != 1 || changed != 1 || !errors.Is(err, context.Canceled) {
		t.Errorf("부른 수 = %d, 바꾼 수 = %d, 오류 = %v", calls, changed, err)
	}
}

func TestEachOfNothingIsNothing(t *testing.T) {
	changed, err := batch.Each(context.Background(), []string{}, func(context.Context, string) (bool, error) {
		t.Fatal("부르지 않아야 한다")
		return false, nil
	})
	if changed != 0 || err != nil {
		t.Errorf("바꾼 수 = %d, 오류 = %v", changed, err)
	}
}
