// billing-server/internal/wallet/read.go

package wallet

import (
	"context"
	"errors"
	"math"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

const (
	// FirstPage 는 원장을 가장 최근 줄부터 읽을 때 before 에 넣는 값이다.
	FirstPage int64 = math.MaxInt64
	// MaxPageSize 는 원장을 한 번에 읽을 수 있는 가장 많은 줄 수다.
	MaxPageSize = 100
)

// ErrInvalidPage 는 원장을 읽는 범위가 틀렸다는 오류다.
var ErrInvalidPage = errors.New("원장을 읽는 범위가 틀렸습니다")

// Page 는 원장의 한 쪽이다.
type Page struct {
	// Entries 는 최근 것부터 놓인 줄들이다.
	Entries []Entry
	// NextBefore 는 다음 쪽을 읽을 때 before 에 넣을 값이다. 더 읽을 것이 없으면 0 이다.
	NextBefore int64
}

// Balance 는 사용자가 지금 쓸 수 있는 크레딧과, 무료 크레딧 중 가장 먼저 사라지는 것을 돌려준다.
// 지갑이 없는 사용자는 모두 0 이다. 읽기만 한다. 기한이 지난 무료 크레딧은 세지 않지만, 사라졌다는 기록은 다음 변경 때 남는다.
//
// 두 쿼리를 읽기 전용 REPEATABLE READ 트랜잭션 하나에서 읽는다. 두 값이 같은 순간의 것이어야
// "가장 먼저 사라지는 양"이 "무료 크레딧"보다 많아 보이는 일이 없다. 시각도 하나(now)로 정한다.
func (s *Service) Balance(ctx context.Context, userID uuid.UUID) (Balance, error) {
	now := s.clock()
	var balance Balance
	options := pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly}
	err := pgx.BeginTxFunc(ctx, s.pool, options, func(tx pgx.Tx) error {
		var err error
		balance, err = readBalance(ctx, walletdb.New(tx), userID, now)
		return err
	})
	if err != nil {
		return Balance{}, err
	}
	return balance, nil
}

// readBalance 는 잔액과 가장 먼저 사라지는 무료 크레딧을 읽는다. 부른 쪽의 트랜잭션(queries) 안에서 한다.
func readBalance(ctx context.Context, queries *walletdb.Queries, userID uuid.UUID, now time.Time) (Balance, error) {
	row, err := queries.GetBalance(ctx, walletdb.GetBalanceParams{UserID: userID, Now: now})
	if err != nil {
		return Balance{}, err
	}
	next, err := nextExpiry(ctx, queries, userID, now)
	if err != nil {
		return Balance{}, err
	}
	return Balance{Paid: credit.Amount(row.Paid), Free: credit.Amount(row.Free), NextExpiry: next}, nil
}

// nextExpiry 는 무료 크레딧 중 가장 먼저 사라지는 것을 읽는다. 무료 크레딧이 없으면 nil 이다.
func nextExpiry(ctx context.Context, queries *walletdb.Queries, userID uuid.UUID, now time.Time) (*Expiry, error) {
	row, err := queries.GetNextFreeExpiry(ctx, walletdb.GetNextFreeExpiryParams{UserID: userID, Now: now})
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &Expiry{Amount: credit.Amount(row.Amount), At: row.ExpiresAt}, nil
}

// Entries 는 사용자의 원장을 최근 것부터 limit 줄까지 돌려준다. before 보다 번호가 작은 줄만 읽는다.
// 처음에는 before 에 FirstPage 를 넣고, 다음부터는 받은 Page.NextBefore 를 넣는다.
func (s *Service) Entries(ctx context.Context, userID uuid.UUID, before int64, limit int) (Page, error) {
	if before < 1 || limit < 1 || limit > MaxPageSize {
		return Page{}, ErrInvalidPage
	}
	// 한 줄을 더 읽어서 다음 쪽이 있는지 안다. 개수를 세는 쿼리를 따로 보내지 않는다
	rows, err := walletdb.New(s.pool).ListEntries(ctx, walletdb.ListEntriesParams{
		UserID: userID, Before: before, RowLimit: int32(limit) + 1,
	})
	if err != nil {
		return Page{}, err
	}
	return toPage(rows, limit), nil
}

// toPage 는 한 줄을 더 읽어 온 결과를 한 쪽으로 자른다. 더 읽어 온 줄이 있으면 다음 쪽이 있다는 뜻이다.
func toPage(rows []walletdb.ListEntriesRow, limit int) Page {
	var next int64
	if len(rows) > limit {
		rows = rows[:limit]
		next = rows[limit-1].ID
	}
	entries := make([]Entry, 0, len(rows))
	for _, row := range rows {
		entries = append(entries, toEntry(row))
	}
	return Page{Entries: entries, NextBefore: next}
}

// toEntry 는 DB 의 줄을 이 패키지의 모양으로 바꾼다.
func toEntry(row walletdb.ListEntriesRow) Entry {
	return Entry{
		ID:          row.ID,
		OperationID: row.OperationID,
		Kind:        Kind(row.Kind),
		Reason:      Reason(row.Reason),
		Amount:      row.Amount,
		OrderID:     row.OrderID,
		HoldID:      row.HoldID,
		CreatedAt:   row.CreatedAt,
	}
}
