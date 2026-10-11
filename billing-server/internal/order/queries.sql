-- billing-server/internal/order/queries.sql
-- 주문을 읽고 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(orderdb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- NULL 일 수 있는 칸에 넣는 값에는 타입을 적어 둔다(::TEXT). 적지 않으면 sqlc 가 NULL 을 담는 타입으로 받는다.
--
-- 상태를 바꾸는 문장은 모두 "지금 이 상태일 때만"이라는 조건을 단다. 두 요청이 함께 와도 한쪽만 바꾼다.
-- 바꾼 쪽은 줄을 돌려받고, 못 바꾼 쪽은 아무 줄도 돌려받지 못한다.

-- name: InsertOrder :one
-- 주문을 만든다. 같은 사용자가 같은 키로 이미 만들었으면 아무것도 하지 않고 줄도 돌려주지 않는다.
INSERT INTO orders (id, user_id, product_id, price, credits, status, idempotency_key, created_at, updated_at)
VALUES (
    sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(product_id), sqlc.arg(price), sqlc.arg(credits),
    'pending', sqlc.arg(idempotency_key), sqlc.arg(now), sqlc.arg(now)
)
ON CONFLICT (user_id, idempotency_key) DO NOTHING
RETURNING *;

-- name: GetOrderByKey :one
-- 사용자가 그 키로 만든 주문을 읽는다.
SELECT * FROM orders
WHERE user_id = sqlc.arg(user_id) AND idempotency_key = sqlc.arg(idempotency_key);

-- name: GetOrderOfUser :one
-- 사용자의 주문 하나를 읽는다. 남의 주문은 없는 것과 같다.
SELECT * FROM orders
WHERE id = sqlc.arg(id) AND user_id = sqlc.arg(user_id);

-- name: GetOrder :one
-- 주문 하나를 읽는다. 누구의 것인지 따지지 않는다. 결제 대행사의 알림을 처리할 때만 쓴다.
SELECT * FROM orders
WHERE id = sqlc.arg(id);

-- name: StartConfirming :one
-- pending 인 주문에 결제 번호를 적고 confirming 으로 바꾼다. 결제 대행사를 부르기 전에 한다.
UPDATE orders
SET status = 'confirming', payment_key = sqlc.arg(payment_key)::TEXT, updated_at = sqlc.arg(now)
WHERE id = sqlc.arg(id) AND user_id = sqlc.arg(user_id) AND status = 'pending'
RETURNING *;

-- name: MarkPaid :one
-- confirming 인 주문을 paid 로 바꾼다. 크레딧을 넣는 일과 같은 트랜잭션에서 한다.
UPDATE orders
SET status = 'paid', paid_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'confirming'
RETURNING *;

-- name: MarkFailed :one
-- confirming 인 주문을 failed 로 바꾸고 거절된 이유를 적는다.
UPDATE orders
SET status = 'failed', failure_code = sqlc.arg(failure_code)::TEXT, updated_at = sqlc.arg(now)
WHERE id = sqlc.arg(id) AND status = 'confirming'
RETURNING *;
