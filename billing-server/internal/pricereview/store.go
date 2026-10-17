// billing-server/internal/pricereview/store.go

package pricereview

import (
	"context"
	"errors"
	"slices"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview/pricereviewdb"
)

// Add 는 할 일을 새로 적는다. 공급사가 값을 바꾸는 시각은 지금보다 뒤여야 한다.
// 이미 30일 안으로 다가온 변경이면, 다음 대사부터 바로 경고가 나온다(늦게 안 것이다).
func (s *Service) Add(ctx context.Context, draft Draft) (Review, error) {
	now := s.clock()
	if err := checkDraft(draft, now); err != nil {
		return Review{}, err
	}
	row, err := pricereviewdb.New(s.pool).InsertReview(ctx, pricereviewdb.InsertReviewParams{
		Subject:   draft.Subject,
		ChangesAt: draft.ChangesAt.UTC(),
		Note:      draft.Note,
		CreatedBy: draft.CreatedBy,
		Now:       now,
	})
	if err != nil {
		return Review{}, err
	}
	return toReview(row, nil), nil
}

// Done 은 할 일 하나를 끝냈다고 적는다. 끝낸 할 일들이 셋이 되면 그 변경은 닫힌다.
// 차례를 따지지 않는다. notice 를 announce 보다 먼저 끝내도 된다. 때가 되기 전에 끝내도 된다.
func (s *Service) Done(ctx context.Context, id int64, step Step, by string, note string) (Review, error) {
	if !knownStep(step) {
		return Review{}, ErrUnknownStep
	}
	return s.mark(ctx, id, string(step), by, note)
}

// Cancel 은 할 일을 닫는다. 공급사가 인상을 거둬들였거나 잘못 적은 것이다. 닫는 이유를 적어야 한다.
// 이미 끝낸 할 일의 표시는 그대로 남는다.
func (s *Service) Cancel(ctx context.Context, id int64, by string, reason string) (Review, error) {
	if reason == "" {
		return Review{}, ErrMissingReason
	}
	return s.mark(ctx, id, cancelMark, by, reason)
}

// List 는 할 일들을 공급사가 값을 바꾸는 시각 순서로 돌려준다. all 이 false 면 남은 것이 있는 할 일만 돌려준다.
func (s *Service) List(ctx context.Context, all bool) ([]Review, error) {
	reviews, err := s.load(ctx)
	if err != nil {
		return nil, err
	}
	if all {
		return reviews, nil
	}
	return slices.DeleteFunc(reviews, func(r Review) bool { return !r.Open() }), nil
}

// Due 는 지금 때가 되었는데 끝내지 않은 할 일들이다. 대사가 하루 한 번 부른다.
func (s *Service) Due(ctx context.Context) ([]Due, error) {
	reviews, err := s.load(ctx)
	if err != nil {
		return nil, err
	}
	return dueSteps(reviews, s.clock()), nil
}

// mark 는 할 일 하나에 표시를 더한다. 할 일을 잠그고, 닫혔는지 본 뒤 더한다.
func (s *Service) mark(ctx context.Context, id int64, mark string, by string, note string) (Review, error) {
	if err := checkMark(by, note); err != nil {
		return Review{}, err
	}
	var marked Review
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := pricereviewdb.New(tx)
		row, marks, err := lockWithMarks(ctx, queries, id)
		if err != nil {
			return err
		}
		if current := toReview(row, marks); current.Cancelled != nil {
			return ErrClosed
		}
		added, err := queries.InsertMark(ctx, pricereviewdb.InsertMarkParams{ReviewID: id, Mark: mark, Note: note, MarkedBy: by, Now: s.clock()})
		// 줄을 돌려받지 못했으면 같은 표시가 이미 있다는 뜻이다
		if errors.Is(err, pgx.ErrNoRows) {
			return ErrAlreadyMarked
		}
		if err != nil {
			return err
		}
		marked = toReview(row, append(marks, added))
		return nil
	})
	return marked, err
}

// lockWithMarks 는 할 일 하나를 잠그고, 그 표시들과 함께 읽는다.
func lockWithMarks(ctx context.Context, queries *pricereviewdb.Queries, id int64) (pricereviewdb.PriceReview, []pricereviewdb.PriceReviewMark, error) {
	row, err := queries.LockReview(ctx, id)
	if errors.Is(err, pgx.ErrNoRows) {
		return row, nil, ErrNotFound
	}
	if err != nil {
		return row, nil, err
	}
	marks, err := queries.MarksOf(ctx, id)
	return row, marks, err
}

// load 는 모든 할 일과 표시를 읽어 묶는다. 한 트랜잭션에서 읽어 같은 순간을 본다.
func (s *Service) load(ctx context.Context) ([]Review, error) {
	var reviews []Review
	options := pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly}
	err := pgx.BeginTxFunc(ctx, s.pool, options, func(tx pgx.Tx) error {
		queries := pricereviewdb.New(tx)
		rows, err := queries.ListReviews(ctx)
		if err != nil {
			return err
		}
		marks, err := queries.ListMarks(ctx)
		if err != nil {
			return err
		}
		reviews = joinMarks(rows, marks)
		return nil
	})
	return reviews, err
}

// joinMarks 는 할 일마다 그 표시들을 붙인다. 할 일의 차례를 지킨다.
func joinMarks(rows []pricereviewdb.PriceReview, marks []pricereviewdb.PriceReviewMark) []Review {
	byReview := make(map[int64][]pricereviewdb.PriceReviewMark)
	for _, m := range marks {
		byReview[m.ReviewID] = append(byReview[m.ReviewID], m)
	}
	reviews := make([]Review, len(rows))
	for i, row := range rows {
		reviews[i] = toReview(row, byReview[row.ID])
	}
	return reviews
}

// toReview 는 DB 의 줄과 표시들을 Review 로 바꾼다.
func toReview(row pricereviewdb.PriceReview, marks []pricereviewdb.PriceReviewMark) Review {
	review := Review{
		ID:        row.ID,
		Subject:   row.Subject,
		ChangesAt: row.ChangesAt,
		Note:      row.Note,
		CreatedBy: row.CreatedBy,
		CreatedAt: row.CreatedAt,
		Done:      make(map[Step]Mark),
	}
	for _, m := range marks {
		mark := Mark{Note: m.Note, MarkedBy: m.MarkedBy, MarkedAt: m.MarkedAt}
		if m.Mark == cancelMark {
			review.Cancelled = &mark
			continue
		}
		review.Done[Step(m.Mark)] = mark
	}
	return review
}

// checkDraft 는 새로 적을 할 일의 값을 본다.
func checkDraft(draft Draft, now time.Time) error {
	switch {
	case draft.Subject == "" || len([]rune(draft.Subject)) > maxSubjectLength:
		return ErrInvalidSubject
	case len([]rune(draft.Note)) > maxNoteLength:
		return ErrInvalidNote
	case !validName(draft.CreatedBy):
		return ErrMissingName
	case !draft.ChangesAt.After(now):
		return ErrPastChange
	}
	return nil
}

// checkMark 는 표시를 더하는 사람과 글을 본다.
func checkMark(by string, note string) error {
	if !validName(by) {
		return ErrMissingName
	}
	if len([]rune(note)) > maxNoteLength {
		return ErrInvalidNote
	}
	return nil
}

// validName 은 적은 사람의 이름이 비지 않았고 너무 길지 않은지다.
func validName(name string) bool {
	return name != "" && len([]rune(name)) <= maxNameLength
}
