-- billing-server/internal/usernotice/queries.sql
-- 사용자의 알림함에 보낼 일을 적고, 꺼내고, 보낸 결과를 적는 SQL. sqlc 가 이 파일을 읽어 Go 코드(usernoticedb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 알림의 금액은 크레딧은 글자("300"), 원은 숫자다. 지갑과 주문의 API 와 같은 모양이다.
-- 시각은 UTC 의 RFC 3339 글자다(2026-10-25T03:00:00Z). DB 의 시간대 설정과 상관없이 같은 글자가 나오게 직접 만든다.

-- name: QueuePaidNotices :execrows
-- since 뒤에 결제가 끝난 주문을 적는다. 이미 적은 것은 건너뛴다. 청약철회된 주문도 결제는 있었다(paid_at 이 남는다).
INSERT INTO user_notices (source_key, user_id, kind, payload, next_attempt_at, created_at)
SELECT 'order.paid:' || o.id::text, o.user_id, 'order.paid',
       jsonb_build_object('order_id', o.id::text, 'product_id', o.product_id, 'price', o.price, 'credits', o.credits::text),
       sqlc.arg(now), sqlc.arg(now)
FROM orders o
WHERE o.paid_at >= sqlc.arg(since)::timestamptz
ON CONFLICT (source_key) DO NOTHING;

-- name: QueueRefundedNotices :execrows
-- since 뒤에 청약철회가 끝난 주문을 적는다.
INSERT INTO user_notices (source_key, user_id, kind, payload, next_attempt_at, created_at)
SELECT 'order.refunded:' || o.id::text, o.user_id, 'order.refunded',
       jsonb_build_object('order_id', o.id::text, 'product_id', o.product_id, 'price', o.price, 'credits', o.credits::text),
       sqlc.arg(now), sqlc.arg(now)
FROM orders o
WHERE o.refunded_at >= sqlc.arg(since)::timestamptz
ON CONFLICT (source_key) DO NOTHING;

-- name: QueueWelcomeNotices :execrows
-- since 뒤에 준 환영 크레딧(grant_key 가 welcome 인 지급 묶음)을 적는다.
INSERT INTO user_notices (source_key, user_id, kind, payload, next_attempt_at, created_at)
SELECT 'credit.welcome:' || g.id::text, g.user_id, 'credit.welcome',
       jsonb_build_object(
           'amount', g.amount::text,
           'expires_at', to_char(g.expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
       ),
       sqlc.arg(now), sqlc.arg(now)
FROM free_grants g
WHERE g.grant_key = 'welcome' AND g.created_at >= sqlc.arg(since)::timestamptz
ON CONFLICT (source_key) DO NOTHING;

-- name: QueueExpiringNotices :execrows
-- up_to 까지 사라질 무료 크레딧이 남은 사람을 적는다. 사람마다 그 크레딧을 모두 더한 양과 가장 먼저 사라지는 시각이다.
-- noticed_since 뒤에 이미 알렸으면 적지 않는다. 출석으로 날마다 받는 사람에게 날마다 알리지 않는다.
-- 열쇠는 사람과 적는 날(한국 날짜)이다. 같은 날 두 바퀴가 함께 적어도 한 줄이다.
INSERT INTO user_notices (source_key, user_id, kind, payload, next_attempt_at, created_at)
SELECT 'credit.expiring:' || g.user_id::text || ':' || to_char(sqlc.arg(now)::timestamptz AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD'),
       g.user_id, 'credit.expiring',
       jsonb_build_object(
           'amount', sum(g.remaining)::text,
           'first_expires_at', to_char(min(g.expires_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
       ),
       sqlc.arg(now), sqlc.arg(now)
FROM free_grants g
WHERE g.remaining > 0
  AND g.expires_at > sqlc.arg(now)::timestamptz
  AND g.expires_at <= sqlc.arg(up_to)::timestamptz
  AND NOT EXISTS (
      SELECT 1 FROM user_notices n
      WHERE n.user_id = g.user_id AND n.kind = 'credit.expiring'
        AND n.created_at > sqlc.arg(noticed_since)::timestamptz
  )
GROUP BY g.user_id
ON CONFLICT (source_key) DO NOTHING;

-- name: QueueShortNotice :execrows
-- 크레딧이 모자라 홀드를 걸지 못한 사람을 적는다. 홀드를 걸지 못한 그 자리에서 부른다(정리 작업이 찾지 않는다).
-- 열쇠는 사람과 적는 날(한국 날짜)이다. 그날 이미 적었으면 적지 않는다. 라운드마다 모자라도 하루에 한 번만 알린다.
-- 그날 처음 모자란 것의 가격표 이름과 값을 싣는다. 크레딧의 양은 글자다.
INSERT INTO user_notices (source_key, user_id, kind, payload, next_attempt_at, created_at)
VALUES (
    'credit.short:' || sqlc.arg(user_id)::uuid::text || ':' || to_char(sqlc.arg(now)::timestamptz AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD'),
    sqlc.arg(user_id)::uuid, 'credit.short',
    jsonb_build_object(
        'price_code', sqlc.arg(price_code)::text,
        'amount', sqlc.arg(amount)::bigint::text,
        'gold_required', sqlc.arg(gold_required)::boolean
    ),
    sqlc.arg(now), sqlc.arg(now)
)
ON CONFLICT (source_key) DO NOTHING;

-- name: ExpireStaleNotices :execrows
-- before 전에 적고 아직 보내지 못한 것을 보내지 않기로 한다. 그만큼 지난 알림은 쓸모가 없다.
UPDATE user_notices SET status = 'expired'
WHERE status = 'pending' AND created_at < sqlc.arg(before)::timestamptz;

-- name: PurgeOldNotices :execrows
-- before 전에 적고 끝난 것(sent, failed, expired)을 지운다. 기다리는 것은 지우지 않는다.
DELETE FROM user_notices
WHERE status <> 'pending' AND created_at < sqlc.arg(before)::timestamptz;

-- name: LockDueNotice :one
-- 보낼 때가 된 것 하나를 잠근다. 다른 정리 작업이 잠근 줄은 건너뛴다.
SELECT * FROM user_notices
WHERE status = 'pending' AND next_attempt_at <= sqlc.arg(now)
ORDER BY next_attempt_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- name: LeaseNotice :exec
-- 차지했다고 적는다. 보내는 동안 다른 정리 작업이 가져가지 않게 다음 시도 시각을 임대가 끝나는 때로 민다.
UPDATE user_notices SET next_attempt_at = sqlc.arg(until), attempts = attempts + 1
WHERE id = sqlc.arg(id);

-- name: MarkNoticeSent :exec
UPDATE user_notices SET status = 'sent', sent_at = sqlc.arg(now)::timestamptz, last_error = ''
WHERE id = sqlc.arg(id) AND status = 'pending';

-- name: DelayNotice :exec
-- 보내지 못했다고 적고 다음 시도 시각을 정한다.
UPDATE user_notices SET next_attempt_at = sqlc.arg(next_attempt_at), last_error = sqlc.arg(last_error)
WHERE id = sqlc.arg(id) AND status = 'pending';

-- name: FailNotice :exec
-- 알림 서버가 받지 않았다고 적는다. 다시 보내지 않는다.
UPDATE user_notices SET status = 'failed', last_error = sqlc.arg(last_error)
WHERE id = sqlc.arg(id) AND status = 'pending';
