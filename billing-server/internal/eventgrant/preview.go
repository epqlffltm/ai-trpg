// billing-server/internal/eventgrant/preview.go

package eventgrant

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// Counter 는 미리 보기가 세는 것이다. *wallet.Service 가 이 모양이다.
type Counter interface {
	CountGranted(ctx context.Context, key string, users []uuid.UUID) (int, error)
	CountWallets(ctx context.Context, users []uuid.UUID) (int, error)
}

// Preview 는 주기 전에 본 명단이다. 읽기만 한 것이라 실제로 줄 때(Give)와 몇 명 다를 수 있다.
type Preview struct {
	// Listed 는 명단의 사람 수다(겹친 번호는 한 번).
	Listed int
	// Granted 는 그 이름의 지급을 이미 받은 사람 수다. 줄 때 건너뛴다.
	Granted int
	// NoWallet 은 지갑이 없는 사람 수다. 이 서버에서 크레딧이 한 번도 바뀌지 않은 사람이다. 주면 지갑이 생긴다.
	NoWallet int
}

// ToGive 는 새로 받을 사람 수다.
func (p Preview) ToGive() int {
	return p.Listed - p.Granted
}

// Total 은 새로 줄 실버의 합이다.
func (p Preview) Total(silver credit.Amount) credit.Amount {
	return silver * credit.Amount(p.ToGive())
}

// Look 은 명단에서 이미 받은 사람과 지갑이 없는 사람을 센다. 아무것도 바꾸지 않는다.
func Look(ctx context.Context, counter Counter, plan Plan) (Preview, error) {
	granted, err := counter.CountGranted(ctx, plan.Key, plan.Users)
	if err != nil {
		return Preview{}, err
	}
	wallets, err := counter.CountWallets(ctx, plan.Users)
	if err != nil {
		return Preview{}, err
	}
	return Preview{Listed: len(plan.Users), Granted: granted, NoWallet: len(plan.Users) - wallets}, nil
}
