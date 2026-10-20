// billing-server/internal/hold/shortfall_test.go

// 크레딧이 모자라 홀드를 걸지 못한 일을 붙여 둔 것(WithShortfalls)에 알리는지 시험한다(#525).
package hold_test

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// shortfall 은 알린 일 하나다.
type shortfall struct {
	user         uuid.UUID
	priceCode    string
	amount       credit.Amount
	goldRequired bool
}

// shortfalls 는 알린 것을 적는 가짜다. fail 이 있으면 그 오류를 돌려준다.
type shortfalls struct {
	got  []shortfall
	fail error
}

func (s *shortfalls) RecordShort(_ context.Context, userID uuid.UUID, priceCode string, amount credit.Amount, goldRequired bool) error {
	s.got = append(s.got, shortfall{user: userID, priceCode: priceCode, amount: amount, goldRequired: goldRequired})
	return s.fail
}

// noted 는 알린 것을 적는 가짜를 홀드 서비스에 붙인다.
func (f fixture) noted() *shortfalls {
	recorded := &shortfalls{}
	f.service.WithShortfalls(recorded)
	return recorded
}

func TestAHoldShortOfCreditsIsNoted(t *testing.T) {
	f := setUp(t)
	f.fund(10, 10)
	recorded := f.noted()

	_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), priceCode)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
	want := shortfall{user: f.user, priceCode: priceCode, amount: price, goldRequired: false}
	if len(recorded.got) != 1 || recorded.got[0] != want {
		t.Errorf("알린 것 = %+v, 기대 = %+v", recorded.got, want)
	}
}

func TestAPremiumHoldShortOfGoldIsNotedAsGoldRequired(t *testing.T) {
	f := setUp(t)
	f.fund(100, 1_000)
	code := f.newPremium(200)
	recorded := f.noted()

	_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), code)

	if !errors.Is(err, wallet.ErrPaidInsufficient) {
		t.Fatalf("오류 = %v. ErrPaidInsufficient 이어야 한다", err)
	}
	want := shortfall{user: f.user, priceCode: code, amount: 200, goldRequired: true}
	if len(recorded.got) != 1 || recorded.got[0] != want {
		t.Errorf("알린 것 = %+v, 기대 = %+v", recorded.got, want)
	}
}

func TestOnlyAShortHoldIsNoted(t *testing.T) {
	// 걸린 홀드, 같은 이름표로 다시 부른 것, 가격표에 없는 이름은 모자람이 아니다
	f := setUp(t)
	f.fund(0, price)
	recorded := f.noted()
	reference := newReference()

	f.place(reference)
	f.place(reference)
	_, _, unknown := f.service.Place(ctx(t), source, f.user, newReference(), "test.unknown-"+uuid.NewString())

	if unknown == nil {
		t.Fatal("없는 이름이 걸렸다")
	}
	if len(recorded.got) != 0 {
		t.Errorf("알린 것 = %+v", recorded.got)
	}
}

func TestAFailedNoteKeepsTheShortAnswer(t *testing.T) {
	// 알림은 덤이다. 적지 못해도 부르는 서버는 그대로 402(모자람)를 받는다. warning 한 줄만 남는다
	f := setUp(t)
	recorded := f.noted()
	recorded.fail = errors.New("DB 에 닿지 못했다")
	var logs bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&logs, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })

	_, _, err := f.service.Place(ctx(t), source, f.user, newReference(), priceCode)

	if !errors.Is(err, wallet.ErrInsufficient) {
		t.Fatalf("오류 = %v. ErrInsufficient 이어야 한다", err)
	}
	line := logs.String()
	if !strings.Contains(line, `"level":"WARN"`) || !strings.Contains(line, `"kind":"credit.short"`) || strings.Contains(line, f.user.String()) {
		t.Errorf("로그 = %s", line)
	}
}
