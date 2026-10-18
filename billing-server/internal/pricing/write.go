// billing-server/internal/pricing/write.go

package pricing

import (
	"context"
	"errors"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing/pricingdb"
)

// uniqueViolation 은 PostgreSQL 이 "이미 있는 값"이라고 알리는 오류의 번호(SQLSTATE)다.
const uniqueViolation = "23505"

// Set 은 값을 정한다. 가격표에 줄 하나를 더한다. 없던 이름이면 새로 판다. 판매를 멈춘 이름이면 다시 판다.
// 적용 시각을 비우면 지금부터다. 미래로 두면 그때부터 바뀐다(예약).
// 행사가(Promo)면 그 이름에 이 줄보다 늦은 줄이 먼저 있어야 한다(ErrPromoNeedsEnd).
func (s *Service) Set(ctx context.Context, change Change) (Version, error) {
	if change.Credits <= 0 || change.Credits > MaxCredits {
		return Version{}, ErrInvalidCredits
	}
	credits := change.Credits
	return s.append(ctx, change, &credits)
}

// Stop 은 판매를 멈춘다. 값이 없는 줄을 더한다. 그 뒤로 이 이름으로 홀드를 걸 수 없다. 이미 건 홀드는 그대로다.
// 한 번도 판 적이 없는 이름이면 ErrUnknownCode, 행사가로 적었으면 ErrPromoStop 이다.
func (s *Service) Stop(ctx context.Context, change Change) (Version, error) {
	if change.Promo {
		return Version{}, ErrPromoStop
	}
	history, err := s.History(ctx, change.Code)
	if err != nil {
		return Version{}, err
	}
	if len(history) == 0 {
		return Version{}, ErrUnknownCode
	}
	return s.append(ctx, change, nil)
}

// append 는 바꿀 내용을 확인하고 가격표에 줄 하나를 덧붙인다. credits 가 nil 이면 판매를 멈추는 줄이다.
func (s *Service) append(ctx context.Context, change Change, credits *credit.Amount) (Version, error) {
	now := s.clock()
	effective, err := checkChange(change, now)
	if err != nil {
		return Version{}, err
	}
	queries := pricingdb.New(s.pool)
	tier, err := resolveTier(ctx, queries, change.Code, effective, change.Tier)
	if err != nil {
		return Version{}, err
	}
	if err := checkPromoEnd(ctx, queries, change.Code, effective, change.Promo); err != nil {
		return Version{}, err
	}
	row, err := queries.InsertPriceVersion(ctx, pricingdb.InsertPriceVersionParams{
		Code:        change.Code,
		Amount:      credits,
		Tier:        string(tier),
		Promo:       change.Promo,
		EffectiveAt: effective,
		Reason:      change.Reason,
		ChangedBy:   change.ChangedBy,
		Now:         now,
	})
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation {
		return Version{}, ErrSameMoment
	}
	if err != nil {
		return Version{}, err
	}
	return toVersion(row), nil
}

// checkChange 는 이름, 이유, 바꾼 사람, 적용 시각을 확인하고 적용 시각을 돌려준다. 비어 있으면 now 다.
func checkChange(change Change, now time.Time) (time.Time, error) {
	if len(change.Code) > maxCodeLength || !codePattern.MatchString(change.Code) {
		return time.Time{}, ErrInvalidCode
	}
	if !validNote(change.Reason) || !validNote(change.ChangedBy) {
		return time.Time{}, ErrMissingNote
	}
	if change.EffectiveAt.IsZero() {
		return now, nil
	}
	effective := change.EffectiveAt.UTC().Truncate(time.Microsecond)
	if effective.Before(now) {
		return time.Time{}, ErrPastEffective
	}
	return effective, nil
}

// resolveTier 는 새 줄에 적을 등급을 정한다. asked 를 적었으면 그것이고, 비웠으면 at 시각에 그 이름의 등급이다.
// at 시각에 적용된 줄이 없으면(처음 파는 이름) 비울 수 없다(ErrMissingTier).
func resolveTier(ctx context.Context, queries *pricingdb.Queries, code string, at time.Time, asked Tier) (Tier, error) {
	if asked != "" {
		if !asked.Valid() {
			return "", ErrInvalidTier
		}
		return asked, nil
	}
	row, err := queries.CurrentPrice(ctx, pricingdb.CurrentPriceParams{Code: code, Now: at})
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrMissingTier
	}
	if err != nil {
		return "", err
	}
	return Tier(row.Tier), nil
}

// checkPromoEnd 는 행사가 줄이면 그 이름에 at 보다 늦은 줄(행사가 끝나는 때)이 있는지 본다. 행사가가 아니면 보지 않는다.
func checkPromoEnd(ctx context.Context, queries *pricingdb.Queries, code string, at time.Time, promo bool) error {
	if !promo {
		return nil
	}
	later, err := queries.HasLaterVersion(ctx, pricingdb.HasLaterVersionParams{Code: code, After: at})
	if err != nil {
		return err
	}
	if !later {
		return ErrPromoNeedsEnd
	}
	return nil
}

// validNote 는 이유나 바꾼 사람이 비지 않았고 너무 길지 않은지 본다.
func validNote(text string) bool {
	return text != "" && utf8.RuneCountInString(text) <= maxNoteLength
}
