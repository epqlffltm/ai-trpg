-- billing-server/internal/receiptnotice/queries.sql
-- 결제한 본인에게 알릴 결제를 적고, 꺼내고, 보냈다고 적는 SQL(#553). sqlc 가 이 파일을 읽어 Go 코드(receiptnoticedb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.

-- name: QueuePaidReceipts :execrows
-- since 뒤에 결제가 끝난 주문을 적는다. 이미 적은 것은 건너뛴다. 청약철회된 주문도 결제는 있었다(paid_at 이 남는다).
INSERT INTO receipt_notices (order_id, kind, user_id, product_id, price, credits, paid_at, occurred_at, next_attempt_at, created_at)
SELECT o.id, 'paid', o.user_id, o.product_id, o.price, o.credits, o.paid_at, o.paid_at, sqlc.arg(now), sqlc.arg(now)
FROM orders o
WHERE o.paid_at >= sqlc.arg(since)::timestamptz
ON CONFLICT (order_id, kind) DO NOTHING;

-- name: QueueRefundedReceipts :execrows
-- since 뒤에 청약철회가 끝난 주문을 적는다.
INSERT INTO receipt_notices (order_id, kind, user_id, product_id, price, credits, paid_at, occurred_at, next_attempt_at, created_at)
SELECT o.id, 'refunded', o.user_id, o.product_id, o.price, o.credits, o.paid_at, o.refunded_at, sqlc.arg(now), sqlc.arg(now)
FROM orders o
WHERE o.refunded_at >= sqlc.arg(since)::timestamptz AND o.paid_at IS NOT NULL
ON CONFLICT (order_id, kind) DO NOTHING;

-- name: LockDueReceipt :one
-- 보낼 때가 된 것 하나를 잠근다. 다른 정리 작업이 잠근 줄은 건너뛴다.
SELECT * FROM receipt_notices
WHERE status = 'pending' AND next_attempt_at <= sqlc.arg(now)
ORDER BY next_attempt_at, order_id, kind
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- name: LeaseReceipt :exec
-- 차지했다고 적는다. 보내는 동안 다른 정리 작업이 가져가지 않게 다음 시도 시각을 임대가 끝나는 때로 민다.
UPDATE receipt_notices SET next_attempt_at = sqlc.arg(until), attempts = attempts + 1
WHERE order_id = sqlc.arg(order_id) AND kind = sqlc.arg(kind);

-- name: MarkReceiptSent :exec
UPDATE receipt_notices SET status = 'sent', sent_at = sqlc.arg(now)::timestamptz, last_error = ''
WHERE order_id = sqlc.arg(order_id) AND kind = sqlc.arg(kind) AND status = 'pending';

-- name: DelayReceipt :exec
-- 보내지 못했다고 적고 다음 시도 시각을 정한다. 버리지 않는다.
UPDATE receipt_notices SET next_attempt_at = sqlc.arg(next_attempt_at), last_error = sqlc.arg(last_error)
WHERE order_id = sqlc.arg(order_id) AND kind = sqlc.arg(kind) AND status = 'pending';
