// billing-server/internal/guardiannotice/store.go

package guardiannotice

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/guardiannotice/guardiannoticedb"
)

const (
	// LookBack 은 적을 때 거슬러 보는 기간이다. 정리 작업이 이만큼 멈춰 있었어도 그 사이의 결제를 놓치지 않는다.
	// 더 오래된 것은 보지 않는다. 한 바퀴마다 주문을 처음부터 훑지 않으려는 것이다
	LookBack = 30 * 24 * time.Hour
	// Lease 는 보내는 동안 다른 정리 작업이 가져가지 않는 시간이다. 보내는 일의 시간 제한(SendTimeout)보다 넉넉하다
	Lease = 30 * time.Second
	// firstRetryDelay 와 maxRetryDelay 는 보내지 못했을 때 다시 보내기까지의 간격이다. 실패할 때마다 두 배가 된다
	firstRetryDelay = 5 * time.Second
	maxRetryDelay   = time.Hour
	// maxErrorLength 는 마지막 오류를 적는 가장 긴 길이다
	maxErrorLength = 200
)

// Service 는 알릴 일을 적고 보낸다.
type Service struct {
	pool   *pgxpool.Pool
	clock  func() time.Time
	sender Sender
}

// NewService 는 Service 를 만든다. sender 가 nil 이면 적기만 하고 보내지 않는다(인증 서버의 주소나 비밀이 없을 때).
// 적어 둔 것은 설정한 뒤에 나간다.
func NewService(pool *pgxpool.Pool, now func() time.Time, sender Sender) *Service {
	return &Service{pool: pool, clock: now, sender: sender}
}

// Round 는 한 바퀴를 돈다. 적고, limit 개까지 보낸다. 적기가 실패해도 보내기는 한다.
func (s *Service) Round(ctx context.Context, limit int) (Result, error) {
	var result Result
	queued, queueErr := s.queue(ctx)
	result.Queued = queued
	if s.sender == nil {
		return result, queueErr
	}
	sent, retried, sendErr := s.deliver(ctx, limit)
	result.Sent, result.Retried = sent, retried
	return result, errors.Join(queueErr, sendErr)
}

// queue 는 최근의 결제와 청약철회 가운데 미성년자의 것을 적는다. 새로 적은 수를 돌려준다.
func (s *Service) queue(ctx context.Context) (int, error) {
	now := s.clock()
	since := now.Add(-LookBack)
	queries := guardiannoticedb.New(s.pool)
	paid, paidErr := queries.QueuePaidNotices(ctx, guardiannoticedb.QueuePaidNoticesParams{Now: now, Since: since})
	refunded, refundedErr := queries.QueueRefundedNotices(ctx, guardiannoticedb.QueueRefundedNoticesParams{Now: now, Since: since})
	return int(paid + refunded), errors.Join(paidErr, refundedErr)
}

// deliver 는 보낼 때가 된 것을 limit 개까지 보낸다. 보낸 수와 다시 보낼 수를 돌려준다.
// 하나를 보내지 못해도 나머지를 보낸다. 다시 보낼 것은 오류가 아니다. DB 의 오류만 돌려준다.
func (s *Service) deliver(ctx context.Context, limit int) (int, int, error) {
	sent, retried := 0, 0
	for range limit {
		outcome, err := s.deliverNext(ctx)
		if err != nil {
			return sent, retried, err
		}
		switch outcome {
		case outcomeNone:
			return sent, retried, nil
		case outcomeSent:
			sent++
		case outcomeRetried:
			retried++
		}
	}
	return sent, retried, nil
}

type outcome int

const (
	outcomeNone outcome = iota
	outcomeSent
	outcomeRetried
)

// deliverNext 는 보낼 때가 된 것 하나를 차지하고 보낸다.
// 차지하기는 짧은 트랜잭션이다. 인증 서버를 부르는 동안에는 잠금을 쥐지 않는다.
func (s *Service) deliverNext(ctx context.Context) (outcome, error) {
	now := s.clock()
	row, found, err := s.claim(ctx, now)
	if err != nil || !found {
		return outcomeNone, err
	}
	notice := toNotice(row)
	if sendErr := s.sender.Send(ctx, notice); sendErr != nil {
		return outcomeRetried, s.delay(ctx, row, sendErr, now)
	}
	return outcomeSent, guardiannoticedb.New(s.pool).MarkNoticeSent(ctx, guardiannoticedb.MarkNoticeSentParams{
		Now: s.clock(), OrderID: row.OrderID, Kind: row.Kind,
	})
}

// claim 은 보낼 때가 된 것 하나를 잠그고, 임대가 끝나는 때까지 다른 쪽이 가져가지 않게 적는다.
func (s *Service) claim(ctx context.Context, now time.Time) (guardiannoticedb.GuardianNotice, bool, error) {
	var claimed guardiannoticedb.GuardianNotice
	found := false
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := guardiannoticedb.New(tx)
		row, err := queries.LockDueNotice(ctx, now)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		claimed, found = row, true
		claimed.Attempts++
		return queries.LeaseNotice(ctx, guardiannoticedb.LeaseNoticeParams{Until: now.Add(Lease), OrderID: row.OrderID, Kind: row.Kind})
	})
	return claimed, found, err
}

// delay 는 보내지 못했다고 적고 다음 시도 시각을 정한다.
func (s *Service) delay(ctx context.Context, row guardiannoticedb.GuardianNotice, cause error, now time.Time) error {
	return guardiannoticedb.New(s.pool).DelayNotice(ctx, guardiannoticedb.DelayNoticeParams{
		NextAttemptAt: now.Add(retryDelay(int(row.Attempts))),
		LastError:     cut(cause.Error(), maxErrorLength),
		OrderID:       row.OrderID,
		Kind:          row.Kind,
	})
}

// retryDelay 는 attempts 번 시도한 뒤에 기다릴 시간이다. 처음이 firstRetryDelay 이고 두 배씩 늘어 maxRetryDelay 에서 멈춘다.
func retryDelay(attempts int) time.Duration {
	delay := firstRetryDelay
	for i := 1; i < attempts && delay < maxRetryDelay; i++ {
		delay *= 2
	}
	return min(delay, maxRetryDelay)
}

// cut 은 글을 n 바이트 안으로 자른다. 글자 가운데서 자르지 않는다.
func cut(text string, n int) string {
	if len(text) <= n {
		return text
	}
	runes := []rune(text)
	for len(string(runes)) > n {
		runes = runes[:len(runes)-1]
	}
	return string(runes)
}

// toNotice 는 DB 의 줄을 알릴 일로 바꾼다.
func toNotice(row guardiannoticedb.GuardianNotice) Notice {
	return Notice{
		OrderID: row.OrderID, Kind: Kind(row.Kind), UserID: row.UserID, ProductID: row.ProductID,
		Price: row.Price, Credits: row.Credits, OccurredAt: row.OccurredAt,
	}
}

// String 은 오류와 로그에 쓰는 짧은 이름이다. 사용자는 넣지 않는다.
func (n Notice) String() string {
	return fmt.Sprintf("%s/%s", n.OrderID, n.Kind)
}
