// billing-server/internal/hold/expire_internal_test.go

// 정리 작업의 한 줄(expireOne)을 안에서 시험한다. 정리 작업은 만료된 홀드를 먼저 읽고 하나씩 돌려준다.
// 읽은 뒤 돌려주기 전에 게임 서버가 연장하면, 그 홀드는 돌려주지 않아야 한다. 이 틈은 밖에서 만들 수 없어서 안에서 본다.
package hold

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/hold/holddb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

func TestExpireOneSkipsAHoldExtendedAfterItWasListed(t *testing.T) {
	ctx := context.Background()
	pool := testenv.Pool(t)
	at := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	now := func() time.Time { return at }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: 7 * 24 * time.Hour})
	service, err := NewService(pool, now, wallets, pricing.NewService(pool, now), 24*time.Hour)
	if err != nil {
		t.Fatalf("홀드 서비스를 만들지 못했다: %v", err)
	}
	user := uuid.New()
	if err := wallets.Deposit(ctx, user, 100); err != nil {
		t.Fatalf("산 크레딧을 넣지 못했다: %v", err)
	}
	reference := "table:" + uuid.NewString() + ":round:1"
	placed, _, err := service.Place(ctx, "trpg-server", user, reference, pricing.NarrationStandard)
	if err != nil {
		t.Fatalf("홀드를 걸지 못했다: %v", err)
	}
	// 만료 시각이 되었다. 정리 작업이 이 홀드를 읽었다고 치고, 돌려주기 전에 연장이 먼저 왔다
	at = at.Add(24 * time.Hour)
	if _, err := service.Extend(ctx, "trpg-server", reference); err != nil {
		t.Fatalf("연장하지 못했다: %v", err)
	}

	changed, err := service.expireOne(ctx, placed.ID)

	if err != nil || changed {
		t.Errorf("돌려줬다 = %v, %v. 연장된 홀드는 돌려주지 않아야 한다", changed, err)
	}
	row, err := holddb.New(pool).GetHoldByReference(ctx, holddb.GetHoldByReferenceParams{Source: "trpg-server", Reference: reference})
	if err != nil || Status(row.Status) != StatusHeld {
		t.Errorf("홀드 = %+v, %v. held 여야 한다", row.Status, err)
	}
	balance, err := wallets.Balance(ctx, user)
	if err != nil || balance.Paid != 50 {
		t.Errorf("잔액 = %+v, %v. 크레딧이 돌아오지 않아야 한다", balance, err)
	}
}
