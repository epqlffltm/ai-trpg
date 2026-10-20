// billing-server/internal/usernotice/short_test.go

// 크레딧이 모자라 홀드를 걸지 못한 일(credit.short, #525)을 적고 보내는지 시험한다. store_test.go 의 fixture 를 쓴다.
package usernotice_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// short 는 크레딧이 없는 사용자에게 서술 한 번의 홀드를 걸어 본다. 모자라야 한다.
func (f fixture) short(user uuid.UUID) {
	f.t.Helper()
	reference := "table:" + uuid.NewString() + ":round:1"
	_, _, err := f.services.Holds.Place(context.Background(), "trpg-server", user, reference, pricing.NarrationStandard)
	if !errors.Is(err, wallet.ErrInsufficient) {
		f.t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
}

func TestAShortHoldIsToldOnceADay(t *testing.T) {
	// 지금은 한국 18시다. 라운드마다 모자라도 그날은 한 번만 알린다
	f := setUp(t)
	user := f.user()
	f.short(user)
	f.clock.now = f.clock.now.Add(5*time.Hour + 59*time.Minute)
	f.short(user)
	f.round()

	got := f.sender.of(user)
	if len(got) != 1 || got[0].Kind != usernotice.KindCreditsShort || got[0].Key != "credit.short:"+user.String()+":20260406" {
		t.Fatalf("보낸 것 = %+v", got)
	}
	want := map[string]any{"price_code": pricing.NarrationStandard, "amount": "50", "gold_required": false}
	for name, value := range want {
		if payload(t, got[0])[name] != value {
			t.Errorf("%s = %v, 기대 = %v", name, payload(t, got[0])[name], value)
		}
	}

	// 한국 날짜가 바뀌면(자정) 다시 알린다
	f.clock.now = f.clock.now.Add(time.Minute)
	f.short(user)
	f.round()
	if got := f.sender.of(user); len(got) != 2 || got[1].Key != "credit.short:"+user.String()+":20260407" {
		t.Errorf("다음 날 보낸 것 = %+v", got)
	}
}

func TestAShortOfGoldIsToldAsGoldRequired(t *testing.T) {
	f := setUp(t)
	user := f.user()

	if err := f.notices.RecordShort(context.Background(), user, "narration.premium-test", 200, true); err != nil {
		t.Fatalf("적지 못했다: %v", err)
	}
	f.round()

	got := f.sender.of(user)
	if len(got) != 1 || payload(t, got[0])["gold_required"] != true || payload(t, got[0])["amount"] != "200" {
		t.Errorf("보낸 것 = %+v", got)
	}
}

func TestAShortNoticeIsWrittenWithoutASender(t *testing.T) {
	// 서버는 보내는 것 없이 적기만 한다. 보내기는 정리 작업이 한다
	f := setUp(t)
	user := f.user()

	f.short(user)

	if rows := f.rows(user); len(rows) != 1 || rows[0] != "credit.short/pending" {
		t.Errorf("줄 = %v", rows)
	}
}
