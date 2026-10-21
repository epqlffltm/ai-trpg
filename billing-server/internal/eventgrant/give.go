// billing-server/internal/eventgrant/give.go

package eventgrant

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// Granter 는 한 사람에게 한 번만 주는 것이다. *wallet.Service 가 이 모양이다.
type Granter interface {
	GrantFreeOnce(ctx context.Context, userID uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error)
}

// Result 는 지금까지 한 것이다.
type Result struct {
	// Given 은 이번에 준 사람 수다.
	Given int
	// Already 는 이미 받아서 건너뛴 사람 수다.
	Already int
}

// Done 은 지금까지 본 사람 수다.
func (r Result) Done() int {
	return r.Given + r.Already
}

// Give 는 명단의 차례대로 한 사람씩 준다. 사람마다 트랜잭션 하나다. 이미 받은 사람은 건너뛴다.
// 다른 오류가 나거나 ctx 가 끝나면 그 자리에서 멈추고 그때까지 한 것과 오류를 돌려준다. 이미 준 것은 그대로 둔다.
// 같은 명단으로 다시 돌리면 받은 사람은 건너뛰고 남은 사람부터 준다.
// 사람 하나를 볼 때마다 onEach 를 부른다(진행을 찍는 데 쓴다). 끝나면 성공이든 실패든 로그(grant.event)를 남긴다.
func Give(ctx context.Context, granter Granter, plan Plan, onEach func(Result)) (Result, error) {
	if err := plan.Check(); err != nil {
		return Result{}, err
	}
	result, err := giveAll(ctx, granter, plan, onEach)
	logOutcome(ctx, plan, result, err)
	return result, err
}

// giveAll 은 명단의 사람마다 giveOne 을 부른다. 처음의 오류에서 멈춘다.
func giveAll(ctx context.Context, granter Granter, plan Plan, onEach func(Result)) (Result, error) {
	result := Result{}
	for _, user := range plan.Users {
		if err := ctx.Err(); err != nil {
			return result, err
		}
		given, err := giveOne(ctx, granter, plan, user)
		if err != nil {
			return result, fmt.Errorf("%s 에게 주지 못했습니다: %w", user, err)
		}
		if given {
			result.Given++
		} else {
			result.Already++
		}
		onEach(result)
	}
	return result, nil
}

// giveOne 은 한 사람에게 준다. 이미 받은 사람이면 주지 않고 false 다.
func giveOne(ctx context.Context, granter Granter, plan Plan, user uuid.UUID) (bool, error) {
	_, err := granter.GrantFreeOnce(ctx, user, plan.Silver, plan.Key)
	if errors.Is(err, wallet.ErrAlreadyGranted) {
		return false, nil
	}
	return err == nil, err
}

// logOutcome 은 지급의 기록을 로그에 남긴다. 누가 왜 몇 명에게 얼마를 줬는지다. 사용자 번호는 싣지 않는다(명단 파일이 기록이다).
// 멈췄으면(오류, 끄라는 신호) 어디까지 했는지와 이유를 warn 으로 남긴다. 사람이 화면을 보고 다시 돌리는 일이라 error 로 경보하지 않는다.
func logOutcome(ctx context.Context, plan Plan, result Result, err error) {
	attrs := []any{
		slog.String("operation", "grant.event"),
		slog.String("grant_key", plan.Key),
		slog.String("silver", plan.Silver.String()),
		slog.Int("listed", len(plan.Users)),
		slog.Int("given", result.Given),
		slog.Int("already", result.Already),
		slog.String("granted_by", plan.By),
		slog.String("reason", plan.Reason),
	}
	if err != nil {
		slog.WarnContext(ctx, "운영자의 이벤트 지급이 중간에 멈췄다", append(attrs, slog.String("error", err.Error()))...)
		return
	}
	slog.InfoContext(ctx, "운영자가 이벤트 실버를 줬다", attrs...)
}
