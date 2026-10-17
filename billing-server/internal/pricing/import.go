// billing-server/internal/pricing/import.go

package pricing

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing/pricingdb"
)

// 가격표에 여러 줄을 한꺼번에 넣는다. 새 모델 묶음, 옵션 조합, 일괄 인상처럼 줄이 많을 때 쓴다.
//
// 지키는 것 둘.
//  1. 다 들어가거나 하나도 들어가지 않는다(한 트랜잭션). 가격은 돈이라 일부만 바뀐 상태가 가장 위험하다.
//  2. 넣기 전에 무엇이 바뀌는지 본다(Plan). Import 도 같은 계산을 거쳐 넣는다. 미리 본 것과 넣은 것이 어긋나지 않는다.
//
// 지금은 명령(cmd/prices import)이 부른다. 관리 서버가 생기면 관리자용 주소가 같은 함수를 부른다.

// Entry 는 한꺼번에 넣을 줄 하나다.
type Entry struct {
	Code string
	// Credits 는 새 값이다. Stop 이면 읽지 않는다.
	Credits credit.Amount
	// Stop 이면 판매를 멈추는 줄이다.
	Stop bool
	// EffectiveAt 은 적용을 시작할 시각이다. 비워 두면(zero) 지금이다. 지금보다 앞설 수 없다.
	EffectiveAt time.Time
}

// Effect 는 줄 하나가 가격표를 어떻게 바꾸는지다.
type Effect string

const (
	// EffectNew 는 그 시각에 팔지 않던 이름을 팔기 시작하는 것이다(처음 팔거나 다시 판다).
	EffectNew Effect = "new"
	// EffectRaise 와 EffectLower 는 값을 올리거나 내리는 것이다.
	EffectRaise Effect = "raise"
	EffectLower Effect = "lower"
	// EffectStop 은 판매를 멈추는 것이다.
	EffectStop Effect = "stop"
	// EffectSame 은 그 시각의 값과 같아 바뀌는 것이 없는 줄이다. 넣지 않는다.
	EffectSame Effect = "same"
)

// Planned 는 넣기 전에 계산한 줄 하나다.
type Planned struct {
	Entry Entry
	// EffectiveAt 은 실제로 적힐 적용 시각이다(비웠으면 지금).
	EffectiveAt time.Time
	// Before 는 그 시각에 바뀌기 전의 값이다. 그때 팔지 않으면 nil 이다.
	Before *Price
	Effect Effect
}

var (
	// ErrNoEntries 는 넣을 줄이 없다는 오류다.
	ErrNoEntries = errors.New("넣을 줄이 없습니다")
	// ErrDuplicateEntry 는 같은 이름이 두 번 나왔다는 오류다. 어느 줄이 맞는지 정할 수 없다.
	ErrDuplicateEntry = errors.New("같은 이름이 두 번 나왔습니다")
)

// Plan 은 줄들을 넣으면 무엇이 바뀌는지 계산한다. 가격표를 바꾸지 않는다.
// 틀린 줄이 하나라도 있으면 그 줄의 번호(1부터)와 이름을 붙인 오류다.
func (s *Service) Plan(ctx context.Context, entries []Entry, reason string, changedBy string) ([]Planned, error) {
	return planEntries(ctx, pricingdb.New(s.pool), s.clock(), entries, reason, changedBy)
}

// Import 는 줄들을 한 트랜잭션으로 넣는다. 바뀌는 것이 없는 줄(EffectSame)은 넣지 않는다.
// 틀린 줄이 하나라도 있거나 넣다가 실패하면 아무것도 넣지 않는다. 계산한 줄들을 돌려준다.
func (s *Service) Import(ctx context.Context, entries []Entry, reason string, changedBy string) ([]Planned, error) {
	now := s.clock()
	var planned []Planned
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := pricingdb.New(tx)
		var err error
		if planned, err = planEntries(ctx, queries, now, entries, reason, changedBy); err != nil {
			return err
		}
		return insertPlanned(ctx, queries, now, planned, reason, changedBy)
	})
	if err != nil {
		return nil, err
	}
	return planned, nil
}

// planEntries 는 줄들을 확인하고 줄마다 무엇이 바뀌는지 계산한다.
func planEntries(ctx context.Context, queries *pricingdb.Queries, now time.Time, entries []Entry, reason string, changedBy string) ([]Planned, error) {
	if len(entries) == 0 {
		return nil, ErrNoEntries
	}
	seen := map[string]bool{}
	planned := make([]Planned, 0, len(entries))
	for i, entry := range entries {
		if seen[entry.Code] {
			return nil, lineError(i, entry, ErrDuplicateEntry)
		}
		seen[entry.Code] = true
		line, err := planEntry(ctx, queries, now, entry, reason, changedBy)
		if err != nil {
			return nil, lineError(i, entry, err)
		}
		planned = append(planned, line)
	}
	return planned, nil
}

// planEntry 는 줄 하나를 확인하고, 그 적용 시각에 바뀌기 전의 값을 읽어 무엇이 바뀌는지 정한다.
func planEntry(ctx context.Context, queries *pricingdb.Queries, now time.Time, entry Entry, reason string, changedBy string) (Planned, error) {
	effective, err := checkEntry(entry, now, reason, changedBy)
	if err != nil {
		return Planned{}, err
	}
	before, everSold, err := priceBefore(ctx, queries, entry.Code, effective)
	if err != nil {
		return Planned{}, err
	}
	if entry.Stop && !everSold {
		return Planned{}, ErrUnknownCode
	}
	return Planned{Entry: entry, EffectiveAt: effective, Before: before, Effect: effectOf(entry, before)}, nil
}

// checkEntry 는 줄 하나의 이름, 값, 이유, 바꾼 사람, 적용 시각을 확인하고 적용 시각을 돌려준다. Set·Stop 과 같은 규칙이다.
func checkEntry(entry Entry, now time.Time, reason string, changedBy string) (time.Time, error) {
	if !entry.Stop && (entry.Credits <= 0 || entry.Credits > MaxCredits) {
		return time.Time{}, ErrInvalidCredits
	}
	return checkChange(Change{Code: entry.Code, EffectiveAt: entry.EffectiveAt, Reason: reason, ChangedBy: changedBy}, now)
}

// priceBefore 는 그 이름의 at 시각의 값을 읽는다. 그때 팔지 않으면 nil 이다.
// 두 번째 값은 at 시각까지 그 이름의 줄이 하나라도 있었는지다(판매를 멈출 수 있는지).
func priceBefore(ctx context.Context, queries *pricingdb.Queries, code string, at time.Time) (*Price, bool, error) {
	row, err := queries.CurrentPrice(ctx, pricingdb.CurrentPriceParams{Code: code, Now: at})
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	if row.Amount == nil {
		return nil, true, nil
	}
	return &Price{Code: row.Code, Credits: *row.Amount, Since: row.EffectiveAt}, true, nil
}

// effectOf 는 바뀌기 전의 값과 새 줄을 견줘 무엇이 바뀌는지 정한다.
func effectOf(entry Entry, before *Price) Effect {
	switch {
	case entry.Stop && before == nil:
		return EffectSame
	case entry.Stop:
		return EffectStop
	case before == nil:
		return EffectNew
	case entry.Credits > before.Credits:
		return EffectRaise
	case entry.Credits < before.Credits:
		return EffectLower
	default:
		return EffectSame
	}
}

// insertPlanned 는 계산한 줄 가운데 바뀌는 것이 있는 줄을 넣는다. 같은 적용 시각의 줄이 이미 있으면 ErrSameMoment 다.
func insertPlanned(ctx context.Context, queries *pricingdb.Queries, now time.Time, planned []Planned, reason string, changedBy string) error {
	for i, line := range planned {
		if line.Effect == EffectSame {
			continue
		}
		_, err := queries.InsertPriceVersion(ctx, pricingdb.InsertPriceVersionParams{
			Code:        line.Entry.Code,
			Amount:      amountOf(line.Entry),
			EffectiveAt: line.EffectiveAt,
			Reason:      reason,
			ChangedBy:   changedBy,
			Now:         now,
		})
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation {
			return lineError(i, line.Entry, ErrSameMoment)
		}
		if err != nil {
			return err
		}
	}
	return nil
}

// amountOf 는 줄에 적을 값이다. 판매를 멈추는 줄이면 nil 이다.
func amountOf(entry Entry) *credit.Amount {
	if entry.Stop {
		return nil
	}
	credits := entry.Credits
	return &credits
}

// lineError 는 오류에 줄 번호(1부터)와 이름을 붙인다. errors.Is 로 원래 오류를 알아본다.
func lineError(index int, entry Entry, err error) error {
	return fmt.Errorf("%d번째 줄(%s): %w", index+1, entry.Code, err)
}
