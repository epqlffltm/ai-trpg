// billing-server/internal/usernotice/store.go

package usernotice

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel/metric"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice/usernoticedb"
)

const (
	// Lease 는 보내는 동안 다른 정리 작업이 가져가지 않는 시간이다. 보내는 일의 시간 제한(SendTimeout)보다 넉넉하다
	Lease = 30 * time.Second
	// firstRetryDelay 와 maxRetryDelay 는 보내지 못했을 때 다시 보내기까지의 간격이다. 실패할 때마다 두 배가 된다
	firstRetryDelay = 5 * time.Second
	maxRetryDelay   = time.Hour
	// maxErrorLength 는 마지막 오류를 적는 가장 긴 길이다
	maxErrorLength = 200
)

// 로그의 operation 과 error_code(docs/observability.md). 게임 서버의 알림 보내기와 같은 이름이다
const (
	SendOperation        = "notification.send"
	ErrorCodeUnavailable = "notification.unavailable"
	ErrorCodeRejected    = "notification.rejected"
)

// Service 는 알릴 일을 적고 보낸다.
type Service struct {
	pool   *pgxpool.Pool
	clock  func() time.Time
	sender Sender
	// notices 는 적고 보낸 일을 센다(metrics.go). 처음에는 세지 않는다
	notices metric.Int64Counter
}

// NewService 는 Service 를 만든다. sender 가 nil 이면 적기만 하고 보내지 않는다(알림 서버의 주소나 비밀이 없을 때).
// 적어 둔 것은 StaleAfter 안에 설정하면 나간다.
func NewService(pool *pgxpool.Pool, now func() time.Time, sender Sender) *Service {
	return &Service{pool: pool, clock: now, sender: sender, notices: noNoticeCounter()}
}

// Round 는 한 바퀴를 돈다. 적고, 정리하고, limit 개까지 보낸다. 하나가 실패해도 나머지는 한다.
func (s *Service) Round(ctx context.Context, limit int) (Result, error) {
	var result Result
	var queueErr, tidyErr, sendErr error
	result.Queued, queueErr = s.queue(ctx)
	result.Expired, result.Purged, tidyErr = s.tidy(ctx)
	if s.sender != nil {
		result.Sent, result.Retried, result.Rejected, sendErr = s.deliver(ctx, limit)
	}
	return result, errors.Join(queueErr, tidyErr, sendErr)
}

// queue 는 최근의 결제, 청약철회, 환영 크레딧과 곧 사라질 무료 크레딧을 적는다. 새로 적은 수를 돌려준다.
func (s *Service) queue(ctx context.Context) (int, error) {
	now := s.clock()
	since := now.Add(-LookBack)
	queries := usernoticedb.New(s.pool)
	paid, paidErr := queries.QueuePaidNotices(ctx, usernoticedb.QueuePaidNoticesParams{Now: now, Since: since})
	refunded, refundedErr := queries.QueueRefundedNotices(ctx, usernoticedb.QueueRefundedNoticesParams{Now: now, Since: since})
	welcome, welcomeErr := queries.QueueWelcomeNotices(ctx, usernoticedb.QueueWelcomeNoticesParams{Now: now, Since: since})
	expiring, expiringErr := queries.QueueExpiringNotices(ctx, usernoticedb.QueueExpiringNoticesParams{
		Now: now, UpTo: now.Add(ExpiringWithin), NoticedSince: now.Add(-ExpiringWithin),
	})
	s.count(ctx, KindOrderPaid, OutcomeQueued, paid)
	s.count(ctx, KindOrderRefunded, OutcomeQueued, refunded)
	s.count(ctx, KindWelcomeCredits, OutcomeQueued, welcome)
	s.count(ctx, KindCreditsExpiring, OutcomeQueued, expiring)
	return int(paid + refunded + welcome + expiring), errors.Join(paidErr, refundedErr, welcomeErr, expiringErr)
}

// tidy 는 오래 보내지 못한 것을 보내지 않기로 하고, 끝난 지 오래된 것을 지운다. 그 두 수를 돌려준다.
func (s *Service) tidy(ctx context.Context) (int, int, error) {
	now := s.clock()
	queries := usernoticedb.New(s.pool)
	expired, expireErr := queries.ExpireStaleNotices(ctx, now.Add(-StaleAfter))
	purged, purgeErr := queries.PurgeOldNotices(ctx, now.Add(-Retention))
	return int(expired), int(purged), errors.Join(expireErr, purgeErr)
}

// deliver 는 보낼 때가 된 것을 limit 개까지 보낸다. 보낸 수, 다시 보낼 수, 받지 않은 수를 돌려준다.
// 하나를 보내지 못해도 나머지를 보낸다. 보내지 못한 것은 오류가 아니다. DB 의 오류만 돌려준다.
func (s *Service) deliver(ctx context.Context, limit int) (int, int, int, error) {
	counts := map[Delivery]int{}
	for range limit {
		delivery, found, err := s.deliverNext(ctx)
		if err != nil || !found {
			return counts[Delivered], counts[Unavailable], counts[Rejected], err
		}
		counts[delivery]++
	}
	return counts[Delivered], counts[Unavailable], counts[Rejected], nil
}

// deliverNext 는 보낼 때가 된 것 하나를 차지하고 보낸 뒤 결과를 적는다. 보낼 것이 없으면 found 가 거짓이다.
// 차지하기는 짧은 트랜잭션이다. 알림 서버를 부르는 동안에는 잠금을 쥐지 않는다.
func (s *Service) deliverNext(ctx context.Context) (Delivery, bool, error) {
	now := s.clock()
	row, found, err := s.claim(ctx, now)
	if err != nil || !found {
		return Delivered, false, err
	}
	notice := toNotice(row)
	sent := s.sender.Send(ctx, notice)
	logUnsent(ctx, notice, sent)
	s.count(ctx, notice.Kind, deliveryOutcome(sent.Delivery), 1)
	return sent.Delivery, true, s.record(ctx, row, sent, now)
}

// claim 은 보낼 때가 된 것 하나를 잠그고, 임대가 끝나는 때까지 다른 쪽이 가져가지 않게 적는다.
func (s *Service) claim(ctx context.Context, now time.Time) (usernoticedb.UserNotice, bool, error) {
	var claimed usernoticedb.UserNotice
	found := false
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := usernoticedb.New(tx)
		row, err := queries.LockDueNotice(ctx, now)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		claimed, found = row, true
		claimed.Attempts++
		return queries.LeaseNotice(ctx, usernoticedb.LeaseNoticeParams{Until: now.Add(Lease), ID: row.ID})
	})
	return claimed, found, err
}

// record 는 보낸 결과를 적는다. 받았으면 보냈다고, 닿지 못했으면 다음 시도 시각을, 받지 않았으면 실패로 적는다.
func (s *Service) record(ctx context.Context, row usernoticedb.UserNotice, sent Sent, now time.Time) error {
	queries := usernoticedb.New(s.pool)
	switch sent.Delivery {
	case Delivered:
		return queries.MarkNoticeSent(ctx, usernoticedb.MarkNoticeSentParams{Now: s.clock(), ID: row.ID})
	case Unavailable:
		return queries.DelayNotice(ctx, usernoticedb.DelayNoticeParams{
			NextAttemptAt: now.Add(retryDelay(int(row.Attempts))),
			LastError:     cut(sent.Reason, maxErrorLength),
			ID:            row.ID,
		})
	default:
		return queries.FailNotice(ctx, usernoticedb.FailNoticeParams{LastError: cut(sent.Reason, maxErrorLength), ID: row.ID})
	}
}

// logUnsent 는 보내지 못한 알림을 로그에 남긴다. 받는 사람과 알림의 내용은 남기지 않는다.
// 다시 보낼 일은 warning 이다. 서명이 거절된 것(401)은 설정을 고쳐야 낫는 일이라 error 다. 받지 않은 것은 버그라 error 다.
func logUnsent(ctx context.Context, notice Notice, sent Sent) {
	if sent.Delivery == Delivered {
		return
	}
	level, message := slog.LevelWarn, "알림을 보내지 못했습니다. 다시 보냅니다"
	result, code := "server_error", ErrorCodeUnavailable
	if sent.Delivery == Rejected {
		level, message = slog.LevelError, "알림 서버가 알림을 받지 않았습니다"
		result, code = "client_error", ErrorCodeRejected
	} else if sent.Reason == reasonUnauthorized {
		level = slog.LevelError
	}
	slog.Log(ctx, level, message,
		slog.String(obs.FieldOperation, SendOperation),
		slog.Int64("notice_id", notice.ID),
		slog.String("kind", string(notice.Kind)),
		slog.String(obs.FieldResult, result),
		slog.String(obs.FieldErrorCode, code),
		slog.String("reason", sent.Reason),
	)
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
func toNotice(row usernoticedb.UserNotice) Notice {
	return Notice{ID: row.ID, Key: row.SourceKey, UserID: row.UserID, Kind: Kind(row.Kind), Payload: row.Payload}
}
