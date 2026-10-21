// billing-server/internal/eventgrant/wallet_test.go

// 진짜 지갑(테스트용 스키마)에 주고 다시 돌려 보는 시험이다. 두 번 돌려도 한 사람이 한 번만 받는지 본다.
package eventgrant_test

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eventgrant"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestGivingTwiceGivesOnce(t *testing.T) {
	captureLogs(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	wallets := wallet.NewService(testenv.Pool(t), time.Now, wallet.Policy{FreeFirst: true, FreeTTL: 720 * time.Hour})
	users := []uuid.UUID{uuid.New(), uuid.New(), uuid.New()}
	key, _ := eventgrant.Key("twice-" + users[0].String()[:8])
	plan := eventgrant.Plan{Key: key, Silver: 300, Users: users[:2], Reason: "보상", By: "test"}

	first, err := eventgrant.Give(ctx, wallets, plan, func(eventgrant.Result) {})
	if err != nil || first != (eventgrant.Result{Given: 2}) {
		t.Fatalf("첫째 = %+v, %v", first, err)
	}
	// 명단을 늘려 다시 돌린다. 앞의 둘은 건너뛰고 새 사람만 받는다
	plan.Users = users
	preview, err := eventgrant.Look(ctx, wallets, plan)
	if err != nil || preview != (eventgrant.Preview{Listed: 3, Granted: 2, NoWallet: 1}) {
		t.Fatalf("미리 보기 = %+v, %v", preview, err)
	}
	second, err := eventgrant.Give(ctx, wallets, plan, func(eventgrant.Result) {})
	if err != nil || second != (eventgrant.Result{Given: 1, Already: 2}) {
		t.Fatalf("둘째 = %+v, %v", second, err)
	}

	for _, user := range users {
		balance, err := wallets.Balance(ctx, user)
		if err != nil || balance.Free != 300 || balance.Paid != 0 {
			t.Errorf("%s: 잔액 = %+v, %v. 무료 300 이어야 한다", user, balance, err)
		}
	}
}
