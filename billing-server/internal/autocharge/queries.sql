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
INSERT INTO auto_charge_settings (user_id, enabled, threshold, product_id, monthly_limit, consecutive_failures, updated_at)
VALUES (sqlc.arg(user_id), sqlc.arg(enabled), sqlc.arg(threshold), sqlc.arg(product_id), sqlc.arg(monthly_limit), 0, sqlc.arg(now))
ON CONFLICT (user_id) DO UPDATE SET
    enabled = EXCLUDED.enabled, threshold = EXCLUDED.threshold, product_id = EXCLUDED.product_id,
    monthly_limit = EXCLUDED.monthly_limit, updated_at = EXCLUDED.updated_at,
    consecutive_failures = CASE WHEN EXCLUDED.enabled THEN 0 ELSE auto_charge_settings.consecutive_failures END
RETURNING *;

-- name: DisableSettings :exec
-- 끈다. 카드를 지웠을 때 쓴다. 설정이 없으면 아무것도 하지 않는다.
UPDATE auto_charge_settings SET enabled = false, updated_at = sqlc.arg(now) WHERE user_id = sqlc.arg(user_id) AND enabled;

-- name: DeleteSettings :execrows
DELETE FROM auto_charge_settings WHERE user_id = sqlc.arg(user_id);

-- name: DeleteCustomer :execrows
DELETE FROM billing_customers WHERE user_id = sqlc.arg(user_id);
