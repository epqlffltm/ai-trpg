-- billing-server/internal/autocharge/queries.sql
-- 자동 충전(#980)의 카드와 설정을 적고 읽는 SQL. sqlc 가 이 파일을 읽어 Go 코드(autochargedb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.

-- name: InsertCustomer :exec
-- 고객 키를 만든다. 이미 있으면 그대로 둔다(함께 온 두 요청이 서로 다른 키를 만들지 않는다).
INSERT INTO billing_customers (user_id, customer_key, created_at)
VALUES (sqlc.arg(user_id), sqlc.arg(customer_key), sqlc.arg(now))
ON CONFLICT (user_id) DO NOTHING;

-- name: GetCustomerKey :one
SELECT customer_key FROM billing_customers WHERE user_id = sqlc.arg(user_id);

-- name: UpsertCard :exec
-- 카드를 적는다. 이미 있으면 바꾼다(사람마다 하나).
INSERT INTO payment_cards (user_id, billing_key, issuer_code, card_number, registered_at)
VALUES (sqlc.arg(user_id), sqlc.arg(billing_key), sqlc.arg(issuer_code), sqlc.arg(card_number), sqlc.arg(now))
ON CONFLICT (user_id) DO UPDATE SET
    billing_key = EXCLUDED.billing_key, issuer_code = EXCLUDED.issuer_code,
    card_number = EXCLUDED.card_number, registered_at = EXCLUDED.registered_at;

-- name: GetCard :one
-- 화면에 보일 것만 읽는다. 빌링키는 읽지 않는다.
SELECT issuer_code, card_number, registered_at FROM payment_cards WHERE user_id = sqlc.arg(user_id);

-- name: LockCard :one
-- 카드의 줄을 잠근다. 켜는 동안 카드를 지우는 요청이 끼어들지 못하게 한다(지우는 쪽은 기다렸다가 끈다).
SELECT user_id FROM payment_cards WHERE user_id = sqlc.arg(user_id) FOR UPDATE;

-- name: DeleteCard :execrows
DELETE FROM payment_cards WHERE user_id = sqlc.arg(user_id);

-- name: GetSettings :one
SELECT * FROM auto_charge_settings WHERE user_id = sqlc.arg(user_id);

-- name: UpsertSettings :one
-- 설정을 적는다. 켜면 이어서 실패한 수를 0 으로 되돌린다(사용자가 다시 켰다). 끄면 그대로 둔다.
-- 방식(mode)과 날(charge_day)은 날짜 기준(#1167)이다. 잔액 기준이어도 날을 남긴다(비어 있을 수 있다).
INSERT INTO auto_charge_settings (
    user_id, enabled, threshold, product_id, monthly_limit, mode, charge_day, consecutive_failures, armed, updated_at
)
VALUES (
    sqlc.arg(user_id), sqlc.arg(enabled), sqlc.arg(threshold), sqlc.arg(product_id), sqlc.arg(monthly_limit),
    sqlc.arg(mode), sqlc.narg(charge_day), 0, sqlc.arg(enabled), sqlc.arg(now)
)
ON CONFLICT (user_id) DO UPDATE SET
    enabled = EXCLUDED.enabled, threshold = EXCLUDED.threshold, product_id = EXCLUDED.product_id,
    monthly_limit = EXCLUDED.monthly_limit, mode = EXCLUDED.mode, charge_day = EXCLUDED.charge_day,
    updated_at = EXCLUDED.updated_at,
    consecutive_failures = CASE WHEN EXCLUDED.enabled THEN 0 ELSE auto_charge_settings.consecutive_failures END,
    -- 켤 때마다 다음에 떨어지면 산다(#980 의 둘째 단계). 이미 기준 아래여도 다음 홀드에서 산다
    armed = EXCLUDED.enabled
RETURNING *;

-- name: DisableSettings :exec
-- 끈다. 카드를 지웠을 때 쓴다. 설정이 없으면 아무것도 하지 않는다.
UPDATE auto_charge_settings SET enabled = false, updated_at = sqlc.arg(now) WHERE user_id = sqlc.arg(user_id) AND enabled;

-- name: DeleteSettings :execrows
DELETE FROM auto_charge_settings WHERE user_id = sqlc.arg(user_id);

-- name: DeleteCustomer :execrows
DELETE FROM billing_customers WHERE user_id = sqlc.arg(user_id);

-- --- 충전할 일(#980 의 둘째 단계) ---

-- name: GetTrigger :one
-- 홀드를 건 트랜잭션 안에서 그 사람의 설정과 지금의 골드를 읽는다. 지갑은 이미 잠겨 있다.
SELECT s.enabled, s.threshold, s.armed, s.product_id, s.mode,
    COALESCE((SELECT w.paid_balance FROM wallets w WHERE w.user_id = s.user_id), 0)::BIGINT AS paid
FROM auto_charge_settings s WHERE s.user_id = sqlc.arg(user_id);

-- name: SetArmed :exec
UPDATE auto_charge_settings SET armed = sqlc.arg(armed) WHERE user_id = sqlc.arg(user_id);

-- name: InsertRequest :execrows
-- 충전할 일을 적는다. 그 사람에게 끝나지 않은 일이 있으면 적지 않는다(바뀐 줄이 0 이다).
INSERT INTO auto_charge_requests (id, user_id, product_id, price, credits, next_attempt_at, created_at)
VALUES (sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(product_id), sqlc.arg(price), sqlc.arg(credits), sqlc.arg(now), sqlc.arg(now))
ON CONFLICT (user_id) WHERE status IN ('pending', 'charging') DO NOTHING;

-- name: ListScheduledDue :many
-- 날짜 기준(#1167)으로 켜 두었고 오늘(한국 날짜의 날 day, 날짜 charge_date)이 그날인데, 오늘의 일도 끝나지 않은 일도 없는 사람.
-- 끝나지 않은 일(잔액 기준에서 바꾸기 전의 것)이 있으면 그 일이 끝난 뒤의 바퀴에서 적는다.
SELECT s.user_id, s.product_id FROM auto_charge_settings s
WHERE s.enabled AND s.mode = 'date' AND s.charge_day = sqlc.arg(day)::SMALLINT
  AND NOT EXISTS (
      SELECT 1 FROM auto_charge_requests r
      WHERE r.user_id = s.user_id AND (r.charge_date = sqlc.arg(charge_date)::DATE OR r.status IN ('pending', 'charging'))
  )
ORDER BY s.user_id
LIMIT sqlc.arg(row_limit);

-- name: InsertScheduledRequest :execrows
-- 날짜 기준의 충전할 일을 적는다. 그날의 일이나 끝나지 않은 일이 이미 있으면 적지 않는다(바뀐 줄이 0 이다).
-- 두 색인(auto_charge_requests_one_per_day, auto_charge_requests_one_open)이 함께 막는다. 결제 작업이 둘이어도 한 번이다.
INSERT INTO auto_charge_requests (id, user_id, product_id, price, credits, charge_date, next_attempt_at, created_at)
VALUES (
    sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(product_id), sqlc.arg(price), sqlc.arg(credits), sqlc.arg(charge_date)::DATE,
    sqlc.arg(now), sqlc.arg(now)
)
ON CONFLICT DO NOTHING;

-- name: LockDueRequest :one
-- 보낼 때가 된 일 하나를 잠근다. 다른 작업이 잠근 줄은 건너뛴다.
SELECT * FROM auto_charge_requests
WHERE status IN ('pending', 'charging') AND next_attempt_at <= sqlc.arg(now)
ORDER BY next_attempt_at, id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- name: LeaseRequest :exec
-- 차지했다고 적는다. 보내는 동안 다른 작업이 가져가지 않게 다음 시도 시각을 임대가 끝나는 때로 민다.
UPDATE auto_charge_requests SET next_attempt_at = sqlc.arg(until), attempts = attempts + 1 WHERE id = sqlc.arg(id);

-- name: GetChargeCard :one
-- 보낼 카드. 빌링키와 고객 키를 함께 읽는다.
SELECT c.billing_key, b.customer_key FROM payment_cards c JOIN billing_customers b ON b.user_id = c.user_id
WHERE c.user_id = sqlc.arg(user_id);

-- name: StartCharging :execrows
-- 보내기 전에 적는다. 그 뒤로 이 일은 그만두지 않고 답을 받을 때까지 같은 카드로 다시 보낸다.
UPDATE auto_charge_requests SET status = 'charging', billing_key = sqlc.arg(billing_key), customer_key = sqlc.arg(customer_key)
WHERE id = sqlc.arg(id) AND status = 'pending';

-- name: SkipRequest :execrows
UPDATE auto_charge_requests SET status = 'skipped', skip_reason = sqlc.arg(reason), finished_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'pending';

-- name: FinishRequest :execrows
-- 결제 대행사의 답(승인, 거절)을 적는다. 카드를 지운다. 보낸 일(charging)만 끝낸다.
UPDATE auto_charge_requests
SET status = sqlc.arg(status), failure_code = sqlc.arg(failure_code), finished_at = sqlc.arg(now)::TIMESTAMPTZ,
    billing_key = NULL, customer_key = NULL, last_error = ''
WHERE id = sqlc.arg(id) AND status = 'charging';

-- name: DelayRequest :exec
-- 답을 받지 못했다고 적고 다음 시도 시각을 정한다. 버리지 않는다.
UPDATE auto_charge_requests SET next_attempt_at = sqlc.arg(next_attempt_at), last_error = sqlc.arg(last_error)
WHERE id = sqlc.arg(id) AND status IN ('pending', 'charging');

-- name: CountSucceeded :exec
UPDATE auto_charge_settings SET consecutive_failures = 0 WHERE user_id = sqlc.arg(user_id);

-- name: CountFailed :one
-- 이어서 실패한 수를 늘린다. 정한 수가 되면 끈다. 늘린 뒤의 수와 켜져 있는지를 돌려준다.
UPDATE auto_charge_settings
SET consecutive_failures = consecutive_failures + 1,
    enabled = enabled AND consecutive_failures + 1 < sqlc.arg(max_failures)::INTEGER,
    armed = false, updated_at = sqlc.arg(now)
WHERE user_id = sqlc.arg(user_id)
RETURNING consecutive_failures, enabled;

-- name: SkipOpenRequests :execrows
-- 아직 보내지 않은 일을 그만둔다. 탈퇴할 때 쓴다. 보낸 일(charging)은 답을 받을 때까지 둔다.
UPDATE auto_charge_requests SET status = 'skipped', skip_reason = 'withdrawn', finished_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE user_id = sqlc.arg(user_id) AND status = 'pending';

-- name: MarkTurnedOff :exec
-- 이 거절로 자동 충전을 껐다고 적는다. 알림에 함께 싣는다(#980).
UPDATE auto_charge_requests SET turned_off = true WHERE id = sqlc.arg(id);


-- name: GetRequest :one
-- 충전할 일 하나. 사람이 결과를 정할 때 읽는다.
SELECT * FROM auto_charge_requests WHERE id = sqlc.arg(id);

-- name: ListRecentRequests :many
-- 그 사람의 충전할 일을 늦게 적힌 것부터. 지갑의 최근 자동 결제 내역이다. 카드와 결제 대행사의 답은 읽지 않는다.
SELECT id, product_id, price, credits, status, skip_reason, turned_off, created_at, finished_at
FROM auto_charge_requests
WHERE user_id = sqlc.arg(user_id)
ORDER BY created_at DESC, id DESC
LIMIT sqlc.arg(row_limit);

-- name: ListOpenRequests :many
-- 끝나지 않은 채(pending, charging) before 보다 먼저 적힌 일. 사람이 볼 일의 목록이다(cmd/autocharges stuck).
SELECT * FROM auto_charge_requests
WHERE status IN ('pending', 'charging') AND created_at <= sqlc.arg(before)::TIMESTAMPTZ
ORDER BY created_at, id
LIMIT sqlc.arg(row_limit);

-- name: InsertConsent :exec
-- 자동 결제 동의를 한 줄 더한다. 켜는 설정을 적는 트랜잭션 안에서 한다.
-- 방식과 날(#1167)도 조건이다. 잔액 기준이면 날을 적지 않는다.
INSERT INTO auto_charge_consents (user_id, terms_version, threshold, product_id, price, monthly_limit, mode, charge_day, agreed_at)
VALUES (sqlc.arg(user_id), sqlc.arg(terms_version), sqlc.arg(threshold), sqlc.arg(product_id), sqlc.arg(price),
        sqlc.arg(monthly_limit), sqlc.arg(mode), sqlc.narg(charge_day), sqlc.arg(now));

-- name: LatestConsentVersion :one
-- 그 사람이 마지막으로 동의한 판. 동의한 적이 없으면 줄이 없다.
SELECT terms_version FROM auto_charge_consents
WHERE user_id = sqlc.arg(user_id)
ORDER BY agreed_at DESC, id DESC
LIMIT 1;
