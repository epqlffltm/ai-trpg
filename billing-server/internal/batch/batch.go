// billing-server/internal/batch/batch.go

// Package batch 는 정리 작업과 대사가 줄 여러 개를 하나씩 처리할 때 쓰는 규칙을 한 곳에 둔다.
//
// 줄 하나가 실패해도 나머지는 마저 처리한다. 고장 난 줄 하나가 맨 앞에 있으면, 실패할 때마다 멈추는 작업은
// 그 뒤의 줄을 영영 처리하지 못한다. 실패한 줄은 세어 오류로 돌려주고, 다음 번에 다시 시도된다.
// 다만 작업이 그만두라는 신호(context 의 취소)를 받으면 거기서 멈춘다.
package batch

import (
	"context"
	"fmt"
)

// Each 는 items 를 하나씩 do 에 넘긴다. do 가 true 를 돌려준 수(바꾼 수)를 센다.
// 실패한 것이 있으면 그 수와 첫 오류를 담은 오류를 함께 돌려준다. 처리한 수는 오류가 있어도 맞다.
func Each[T any](ctx context.Context, items []T, do func(context.Context, T) (bool, error)) (int, error) {
	changed, failed := 0, 0
	var first error
	for _, item := range items {
		if err := ctx.Err(); err != nil {
			return changed, err
		}
		done, err := do(ctx, item)
		if err != nil {
			failed++
			if first == nil {
				first = err
			}
			continue
		}
		if done {
			changed++
		}
	}
	if failed > 0 {
		return changed, fmt.Errorf("%d 개 가운데 %d 개를 처리하지 못했습니다: %w", len(items), failed, first)
	}
	return changed, nil
}
