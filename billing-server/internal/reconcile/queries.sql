-- billing-server/internal/reconcile/queries.sql
-- 대사가 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(reconciledb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 모두 읽기만 한다. "지금의 값"(지갑, 산 크레딧의 묶음, 지급 묶음, 주문, 홀드)과 "왜 그렇게 되었는가"(원장)가 맞는지 본다.
-- 맞지 않는 줄의 번호를 돌려준다. 고치지 않는다. 원장은 지울 수 없고, 무엇이 맞는지는 사람이 정한다.

-- name: PaidBalanceMismatches :many
-- 산 크레딧의 잔액이 원장의 paid 줄의 합과 다른 지갑.
SELECT w.user_id
FROM wallets w
LEFT JOIN (
    SELECT user_id, SUM(amount)::BIGINT AS total FROM ledger_entries WHERE kind = 'paid' GROUP BY user_id
) l ON l.user_id = w.user_id
WHERE w.paid_balance <> COALESCE(l.total, 0)
ORDER BY w.user_id
LIMIT sqlc.arg(row_limit);

-- name: GrantRemainingMismatches :many
-- 남은 양이 그 묶음을 가리키는 원장 줄의 합과 다른 지급 묶음.
SELECT g.id
FROM free_grants g
LEFT JOIN (
    SELECT grant_id, SUM(amount)::BIGINT AS total FROM ledger_entries WHERE grant_id IS NOT NULL GROUP BY grant_id
) l ON l.grant_id = g.id
WHERE g.remaining <> COALESCE(l.total, 0)
ORDER BY g.id
LIMIT sqlc.arg(row_limit);

-- name: PaidLotRemainingMismatches :many
-- 남은 양이 그 묶음을 가리키는 원장 줄의 합과 다른 산 크레딧의 묶음.
SELECT p.id
FROM paid_lots p
LEFT JOIN (
    SELECT lot_id, SUM(amount)::BIGINT AS total FROM ledger_entries WHERE lot_id IS NOT NULL GROUP BY lot_id
) l ON l.lot_id = p.id
WHERE p.remaining <> COALESCE(l.total, 0)
ORDER BY p.id
LIMIT sqlc.arg(row_limit);

-- name: PaidLotTotalMismatches :many
-- 산 크레딧의 잔액이 그 사용자의 묶음들의 남은 양의 합과 다른 지갑.
SELECT w.user_id
FROM wallets w
LEFT JOIN (
    SELECT user_id, SUM(remaining)::BIGINT AS total FROM paid_lots GROUP BY user_id
) p ON p.user_id = w.user_id
WHERE w.paid_balance <> COALESCE(p.total, 0)
ORDER BY w.user_id
LIMIT sqlc.arg(row_limit);

-- name: PaidOrdersWithoutLot :many
-- 치렀는데(paid, 환불 중, 환불됨) 그 주문의 묶음이 없거나, 묶음의 양이나 주인이 주문과 다른 주문. 청약철회가 이 묶음을 본다.
SELECT o.id
FROM orders o
LEFT JOIN paid_lots p ON p.order_id = o.id
WHERE o.status IN ('paid', 'refunding', 'refunded') AND (p.id IS NULL OR p.amount <> o.credits OR p.user_id <> o.user_id)
ORDER BY o.id
LIMIT sqlc.arg(row_limit);

-- name: PaidOrdersWithoutDeposit :many
-- 치렀는데(paid, 환불 중, 환불됨) 크레딧이 들어온 줄이 없거나, 들어온 양이 주문의 크레딧과 다른 주문.
-- 환불한 주문도 들어온 줄은 그대로 있다. 원장은 지우지 않고, 빠진 것은 refund 줄로 따로 적는다.
SELECT o.id
FROM orders o
LEFT JOIN ledger_entries e ON e.order_id = o.id
WHERE o.status IN ('paid', 'refunding', 'refunded') AND (e.id IS NULL OR e.amount <> o.credits)
ORDER BY o.id
LIMIT sqlc.arg(row_limit);

-- name: DepositsWithoutPaidOrder :many
-- 크레딧이 들어온 줄인데 그 주문이 치른 상태(paid, 환불 중, 환불됨)가 아닌 원장의 줄.
SELECT e.id
FROM ledger_entries e
JOIN orders o ON o.id = e.order_id
WHERE o.status NOT IN ('paid', 'refunding', 'refunded')
ORDER BY e.id
LIMIT sqlc.arg(row_limit);

-- name: LotRefundMismatches :many
-- 청약철회의 줄(refund, unrefund)이 주문의 상태와 맞지 않는 산 크레딧의 묶음.
--   - 주문이 환불 중이거나 환불되었으면: 두 줄의 합이 -묶음의 양이고, 묶음은 비어 있다
--   - 그 밖(치른 주문, 주문 없는 묶음): 두 줄의 합이 0 이다. 거절되어 되돌렸으면 refund 와 unrefund 가 짝을 이룬다
SELECT p.id
FROM paid_lots p
LEFT JOIN orders o ON o.id = p.order_id
LEFT JOIN (
    SELECT lot_id, SUM(amount)::BIGINT AS total
    FROM ledger_entries
    WHERE reason IN ('refund', 'unrefund') AND lot_id IS NOT NULL
    GROUP BY lot_id
) r ON r.lot_id = p.id
WHERE COALESCE(r.total, 0) <> CASE WHEN o.status IN ('refunding', 'refunded') THEN -p.amount ELSE 0 END
   OR (o.status IN ('refunding', 'refunded') AND p.remaining <> 0)
ORDER BY p.id
LIMIT sqlc.arg(row_limit);

-- name: HoldLineMismatches :many
-- 원장의 줄이 상태와 맞지 않는 홀드. 빠진 줄(hold)의 합은 늘 -값이고,
-- 돌아온 줄(release)의 합은 돌려준 홀드면 값, 아니면 0 이어야 한다.
SELECT h.id
FROM holds h
LEFT JOIN (
    SELECT hold_id,
           (SUM(amount) FILTER (WHERE reason = 'hold'))::BIGINT AS taken,
           (SUM(amount) FILTER (WHERE reason = 'release'))::BIGINT AS returned
    FROM ledger_entries
    WHERE hold_id IS NOT NULL
    GROUP BY hold_id
) l ON l.hold_id = h.id
WHERE COALESCE(l.taken, 0) <> -h.amount
   OR COALESCE(l.returned, 0) <> CASE WHEN h.status = 'released' THEN h.amount ELSE 0 END
ORDER BY h.id
LIMIT sqlc.arg(row_limit);

-- name: CountOverdue :one
-- 정리 작업이 아직 손대지 못한 것의 수. 만료 시각이 지난 held 홀드, 만료 시각이 지난 pending 주문,
-- 사라질 시각이 지났는데 원장에 아직 적히지 않은 지급 묶음. 많으면 정리 작업이 멈춰 있는 것이다.
SELECT
    (SELECT COUNT(*) FROM holds WHERE status = 'held' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ)::BIGINT AS held_holds,
    (SELECT COUNT(*) FROM orders WHERE status = 'pending' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ)::BIGINT AS pending_orders,
    (SELECT COUNT(*) FROM free_grants WHERE remaining > 0 AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ)::BIGINT AS free_grants;
