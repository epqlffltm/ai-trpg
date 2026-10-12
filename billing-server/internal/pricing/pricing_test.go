// billing-server/internal/pricing/pricing_test.go

// 가격표를 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 시험한다.
// 가격표는 이름 하나를 여러 테스트가 함께 보지 않게, 테스트마다 새 이름("test.<번호>")을 지어 쓴다.
// 마이그레이션이 넣은 narration.standard 는 다른 패키지의 테스트가 기대므로 바꾸지 않는다.
package pricing_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// startedAt 은 테스트의 시계가 가리키는 시각이다.
var startedAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

// clock 은 테스트가 마음대로 돌리는 시계다.
type clock struct {
	mu  sync.Mutex
	now time.Time
}

func (c *clock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *clock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// fixture 는 테스트 하나가 쓰는 것들이다.
type fixture struct {
	t       *testing.T
	pool    *pgxpool.Pool
	clock   *clock
	service *pricing.Service
	// code 는 이 테스트만 쓰는 이름이다.
	code string
}

func setUp(t *testing.T) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	clock := &clock{now: startedAt}
	return fixture{t: t, pool: pool, clock: clock, service: pricing.NewService(pool, clock.Now), code: "test." + uuid.NewString()}
}

func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// change 는 이 테스트의 이름으로 바꿀 내용을 만든다.
func (f fixture) change(credits credit.Amount) pricing.Change {
	return pricing.Change{Code: f.code, Credits: credits, Reason: "테스트", ChangedBy: "test"}
}

// set 은 값을 정한다. 실패하면 테스트를 멈춘다.
func (f fixture) set(change pricing.Change) pricing.Version {
	f.t.Helper()
	version, err := f.service.Set(ctx(f.t), change)
	if err != nil {
		f.t.Fatalf("값을 정하지 못했다: %v", err)
	}
	return version
}

// priceNow 는 지금 시각의 값을 읽는다.
func (f fixture) priceNow() (pricing.Price, error) {
	return f.service.At(ctx(f.t), f.code, f.clock.Now())
}

func TestTheMigrationCarriesTheNarrationPriceOver(t *testing.T) {
	f := setUp(t)

	// 서버가 생기기 전부터 적용된 것으로 둔다. 정리 작업의 테스트가 쓰는 2001년에도 값이 있다
	for _, at := range []time.Time{startedAt, testenv.SweepEra} {
		price, err := f.service.At(ctx(t), pricing.NarrationStandard, at)
		if err != nil || price.Credits != 50 || price.Code != "narration.standard" {
			t.Errorf("%v 의 서술 값 = %+v, %v. 기대 = 50", at, price, err)
		}
	}
}

func TestSetMakesANewPriceAvailableNow(t *testing.T) {
	f := setUp(t)

	version := f.set(f.change(120))

	if !version.OnSale || version.Credits != 120 || !version.EffectiveAt.Equal(startedAt) || version.ChangedBy != "test" {
		t.Fatalf("줄 = %+v", version)
	}
	price, err := f.priceNow()
	if err != nil || price != (pricing.Price{Code: f.code, Credits: 120, Since: startedAt}) {
		t.Errorf("지금의 값 = %+v, %v", price, err)
	}
}

func TestANewValueAddsALineAndKeepsTheOldOne(t *testing.T) {
	f := setUp(t)
	f.set(f.change(50))
	f.clock.Advance(time.Hour)

	f.set(f.change(80))

	price, _ := f.priceNow()
	before, _ := f.service.At(ctx(t), f.code, startedAt)
	if price.Credits != 80 || before.Credits != 50 {
		t.Errorf("지금 = %d, 한 시간 전 = %d. 기대 = 80, 50", price.Credits, before.Credits)
	}
	history, err := f.service.History(ctx(t), f.code)
	if err != nil || len(history) != 2 || history[0].Credits != 50 || history[1].Credits != 80 {
		t.Errorf("기록 = %+v, %v", history, err)
	}
}

func TestAScheduledValueAppliesOnlyFromItsTime(t *testing.T) {
	f := setUp(t)
	f.set(f.change(50))
	change := f.change(70)
	change.EffectiveAt = startedAt.Add(24 * time.Hour)

	f.set(change)

	if price, _ := f.priceNow(); price.Credits != 50 {
		t.Errorf("예약한 때 전의 값 = %d, 기대 = 50", price.Credits)
	}
	f.clock.Advance(24 * time.Hour)
	if price, _ := f.priceNow(); price.Credits != 70 {
		t.Errorf("예약한 때의 값 = %d, 기대 = 70", price.Credits)
	}
}

func TestStopEndsTheSaleAndSetResumesIt(t *testing.T) {
	f := setUp(t)
	f.set(f.change(50))
	f.clock.Advance(time.Minute)

	stopped, err := f.service.Stop(ctx(t), f.change(0))
	if err != nil || stopped.OnSale || stopped.Credits != 0 {
		t.Fatalf("멈춘 줄 = %+v, %v", stopped, err)
	}
	if _, err := f.priceNow(); !errors.Is(err, pricing.ErrNotForSale) {
		t.Errorf("멈춘 뒤의 값 = %v. ErrNotForSale 이어야 한다", err)
	}
	f.clock.Advance(time.Minute)
	f.set(f.change(60))
	if price, err := f.priceNow(); err != nil || price.Credits != 60 {
		t.Errorf("다시 판 값 = %+v, %v", price, err)
	}
}

func TestUnknownNamesAndTimesBeforeTheFirstValueHaveNoPrice(t *testing.T) {
	f := setUp(t)
	if _, err := f.priceNow(); !errors.Is(err, pricing.ErrUnknownCode) {
		t.Errorf("없는 이름 = %v. ErrUnknownCode 이어야 한다", err)
	}
	f.clock.Advance(time.Hour)
	f.set(f.change(50))
	if _, err := f.service.At(ctx(t), f.code, startedAt); !errors.Is(err, pricing.ErrUnknownCode) {
		t.Errorf("처음 값보다 앞선 시각 = %v. ErrUnknownCode 이어야 한다", err)
	}
	if _, err := f.service.Stop(ctx(t), pricing.Change{Code: "test." + uuid.NewString(), Reason: "r", ChangedBy: "b"}); !errors.Is(err, pricing.ErrUnknownCode) {
		t.Errorf("판 적 없는 이름의 판매 중지 = %v. ErrUnknownCode 이어야 한다", err)
	}
}

func TestBadChangesAreRefusedAndWriteNothing(t *testing.T) {
	f := setUp(t)
	long := strings.Repeat("가", 201)
	cases := map[string]struct {
		change pricing.Change
		want   error
	}{
		"값이 0":       {pricing.Change{Code: f.code, Credits: 0, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCredits},
		"값이 음수":      {pricing.Change{Code: f.code, Credits: -5, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCredits},
		"값이 너무 크다":   {pricing.Change{Code: f.code, Credits: 1_000_001, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCredits},
		"이름에 점이 없다":  {pricing.Change{Code: "narration", Credits: 5, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCode},
		"이름에 대문자":    {pricing.Change{Code: "Narration.x", Credits: 5, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCode},
		"이름에 쌍점":     {pricing.Change{Code: "narration.gemma4:26b", Credits: 5, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCode},
		"이름이 너무 길다":  {pricing.Change{Code: "narration." + strings.Repeat("a", 60), Credits: 5, Reason: "r", ChangedBy: "b"}, pricing.ErrInvalidCode},
		"이유가 없다":     {pricing.Change{Code: f.code, Credits: 5, ChangedBy: "b"}, pricing.ErrMissingNote},
		"바꾼 사람이 없다":  {pricing.Change{Code: f.code, Credits: 5, Reason: "r"}, pricing.ErrMissingNote},
		"이유가 너무 길다":  {pricing.Change{Code: f.code, Credits: 5, Reason: long, ChangedBy: "b"}, pricing.ErrMissingNote},
		"적용 시각이 지났다": {pricing.Change{Code: f.code, Credits: 5, Reason: "r", ChangedBy: "b", EffectiveAt: startedAt.Add(-time.Second)}, pricing.ErrPastEffective},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := f.service.Set(ctx(t), tc.change); !errors.Is(err, tc.want) {
				t.Errorf("오류 = %v, 기대 = %v", err, tc.want)
			}
		})
	}
	if history, _ := f.service.History(ctx(t), f.code); len(history) != 0 {
		t.Errorf("거절했는데 줄이 남았다: %+v", history)
	}
}

func TestTwoValuesForTheSameMomentAreRefused(t *testing.T) {
	f := setUp(t)
	f.set(f.change(50))

	_, err := f.service.Set(ctx(t), f.change(60))

	if !errors.Is(err, pricing.ErrSameMoment) {
		t.Errorf("오류 = %v. ErrSameMoment 이어야 한다", err)
	}
}

func TestCurrentListsEachNameOnceWithItsLiveLine(t *testing.T) {
	f := setUp(t)
	stoppedCode := "test." + uuid.NewString()
	f.set(f.change(50))
	f.set(pricing.Change{Code: stoppedCode, Credits: 30, Reason: "r", ChangedBy: "b"})
	f.clock.Advance(time.Minute)
	f.set(f.change(90))
	if _, err := f.service.Stop(ctx(t), pricing.Change{Code: stoppedCode, Reason: "r", ChangedBy: "b"}); err != nil {
		t.Fatalf("판매를 멈추지 못했다: %v", err)
	}
	scheduled := f.change(500)
	scheduled.EffectiveAt = startedAt.Add(time.Hour)
	f.set(scheduled)

	current, err := f.service.Current(ctx(t))
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}

	// 예약한 값은 아직이다. 멈춘 이름은 판매 중지로 나온다. 이름마다 한 줄이다
	found := map[string][]pricing.Version{}
	for _, version := range current {
		found[version.Code] = append(found[version.Code], version)
	}
	if lines := found[f.code]; len(lines) != 1 || lines[0].Credits != 90 || !lines[0].OnSale {
		t.Errorf("%s = %+v", f.code, lines)
	}
	if lines := found[stoppedCode]; len(lines) != 1 || lines[0].OnSale {
		t.Errorf("%s = %+v", stoppedCode, lines)
	}
	if lines := found[pricing.NarrationStandard]; len(lines) != 1 || lines[0].Credits != 50 {
		t.Errorf("%s = %+v", pricing.NarrationStandard, lines)
	}
}

func TestTheDatabaseKeepsThePriceListAppendOnly(t *testing.T) {
	f := setUp(t)
	version := f.set(f.change(50))

	for name, sql := range map[string]string{
		"값을 고친다": "UPDATE price_versions SET amount = 1 WHERE id = $1",
		"줄을 지운다": "DELETE FROM price_versions WHERE id = $1",
	} {
		_, err := f.pool.Exec(ctx(t), sql, version.ID)
		if err == nil || !strings.Contains(err.Error(), "23001") {
			t.Errorf("%s: 오류 = %v. 트리거(23001)가 막아야 한다", name, err)
		}
	}
	insert := `INSERT INTO price_versions (code, amount, effective_at, reason, changed_by, created_at) VALUES ($1, $2, $3, $4, $5, $3)`
	for name, args := range map[string][]any{
		"값이 0":        {f.code, 0, startedAt.Add(time.Hour), "r", "b"},
		"값이 너무 크다":    {f.code, 1_000_001, startedAt.Add(time.Hour), "r", "b"},
		"이름의 모양":      {"Narration", 5, startedAt.Add(time.Hour), "r", "b"},
		"이유가 빈 글자":    {f.code, 5, startedAt.Add(time.Hour), "", "b"},
		"바꾼 사람이 빈 글자": {f.code, 5, startedAt.Add(time.Hour), "r", ""},
	} {
		_, err := f.pool.Exec(ctx(t), insert, args...)
		if err == nil || !strings.Contains(err.Error(), "23514") {
			t.Errorf("%s: 오류 = %v. CHECK(23514)로 거절해야 한다", name, err)
		}
	}
}
