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
-- 길(channel)에는 기본값이 있지만 늘 적는다. 기본값은 옛 서버가 떠 있는 동안을 위한 것이다(00009).
INSERT INTO orders (id, user_id, product_id, channel, price, credits, status, idempotency_key, created_at, updated_at, expires_at)
VALUES (
    sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(product_id), sqlc.arg(channel), sqlc.arg(price), sqlc.arg(credits),
    'pending', sqlc.arg(idempotency_key), sqlc.arg(now), sqlc.arg(now), sqlc.arg(expires_at)
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
-- 만료 시각이 지난 주문은 바꾸지 않는다. 정리 작업이 아직 expired 로 바꾸지 않았어도 치를 수 없다.
UPDATE orders
SET status = 'confirming', payment_key = sqlc.arg(payment_key)::TEXT, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND user_id = sqlc.arg(user_id) AND status = 'pending'
    AND expires_at > sqlc.arg(now)::TIMESTAMPTZ
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

-- name: ExpireOrder :one
-- 만료 시각이 지난 pending 주문 하나를 expired 로 바꾼다. 승인을 요청한 쪽이 늦었을 때 쓴다.
UPDATE orders
SET status = 'expired', updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'pending' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ
RETURNING *;

-- name: ExpireDueOrders :execrows
-- 만료 시각이 지난 pending 주문을 오래된 것부터 row_limit 개까지 expired 로 바꾼다(정리 작업).
-- 다른 정리 작업이나 승인 요청이 잠근 줄은 기다리지 않고 건너뛴다. 크레딧과 상관없는 주문이라 한 문장으로 한꺼번에 바꾼다.
-- 고른 줄은 이 문장이 잠그므로 그사이에 바뀌지 않는다. 그래도 pending 조건을 한 번 더 단다.
--
-- 고르는 일을 MATERIALIZED 로 한 번만 한다. "id IN (SELECT ... LIMIT ... FOR UPDATE SKIP LOCKED)" 로 쓰면, DB 가 바깥 줄마다
-- 안의 SELECT 를 다시 돌리는 계획(Nested Loop)을 고를 수 있다. 다시 돌 때는 방금 바꾼 줄을 건너뛰고 그다음 줄을 골라서
-- row_limit 보다 많이 바꾼다. 표가 작을 때 실제로 그랬다
WITH due AS MATERIALIZED (
    SELECT id FROM orders
    WHERE status = 'pending' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ
    ORDER BY expires_at, id
    LIMIT sqlc.arg(row_limit)
    FOR UPDATE SKIP LOCKED
)
UPDATE orders
SET status = 'expired', updated_at = sqlc.arg(now)::TIMESTAMPTZ
FROM due
WHERE orders.id = due.id AND orders.status = 'pending';

-- name: ListStaleConfirming :many
-- before 보다 먼저 confirming 이 된 주문을 오래된 것부터 읽는다(대사). 결제 대행사에 결과를 물어 끝낸다.
SELECT * FROM orders
WHERE status = 'confirming' AND updated_at <= sqlc.arg(before)::TIMESTAMPTZ
ORDER BY updated_at, id
LIMIT sqlc.arg(row_limit);

-- name: StartRefunding :one
-- paid 인 주문을 refunding 으로 바꾼다. 치른 시각이 paid_after 보다 늦은 것(청약철회 기한 안)만 바꾼다.
-- 그 주문의 묶음을 비우는 일과 같은 트랜잭션에서 한다. 결제 대행사를 부르기 전에 한다.
UPDATE orders
SET status = 'refunding', updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND user_id = sqlc.arg(user_id) AND status = 'paid'
    AND paid_at > sqlc.arg(paid_after)::TIMESTAMPTZ
RETURNING *;

-- name: MarkRefunded :one
-- refunding 인 주문을 refunded 로 바꾼다. 결제 대행사가 취소했을 때 한다.
UPDATE orders
SET status = 'refunded', refunded_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'refunding'
RETURNING *;

-- name: RestorePaid :one
-- refunding 인 주문을 paid 로 되돌린다. 결제 대행사가 취소를 확실히 거절했을 때, 묶음을 다시 채우는 일과 같은 트랜잭션에서 한다.
UPDATE orders
SET status = 'paid', updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'refunding'
RETURNING *;

-- name: ListStaleRefunding :many
-- before 보다 먼저 refunding 이 된 주문을 오래된 것부터 읽는다(대사). 같은 취소를 다시 보내 끝낸다.
SELECT * FROM orders
WHERE status = 'refunding' AND updated_at <= sqlc.arg(before)::TIMESTAMPTZ
ORDER BY updated_at, id
LIMIT sqlc.arg(row_limit);
