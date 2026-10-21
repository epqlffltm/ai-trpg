-- billing-server/internal/wallet/queries.sql
-- 지갑, 산 크레딧의 묶음, 무료 크레딧의 지급 묶음, 원장을 읽고 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(walletdb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 테이블 이름에 스키마를 붙이지 않는다. 어느 스키마인지는 연결의 search_path 가 정한다.

-- name: EnsureWallet :exec
-- 지갑이 없으면 만든다. 있으면 아무것도 하지 않는다. 두 요청이 함께 만들려 해도 하나만 생긴다.
INSERT INTO wallets (user_id, created_at, updated_at)
VALUES (sqlc.arg(user_id), sqlc.arg(now), sqlc.arg(now))
ON CONFLICT (user_id) DO NOTHING;

-- name: LockWallet :one
-- 지갑의 줄을 잠그고 읽는다. 같은 사용자의 다른 변경은 이 트랜잭션이 끝날 때까지 여기서 기다린다.
SELECT paid_balance
FROM wallets
WHERE user_id = sqlc.arg(user_id)
FOR UPDATE;

-- name: AddPaidBalance :exec
-- 산 크레딧의 잔액에 delta 를 더한다(빼려면 음수). 0 아래로 내려가면 CHECK 가 막는다.
UPDATE wallets
SET paid_balance = paid_balance + sqlc.arg(delta), updated_at = sqlc.arg(now)
WHERE user_id = sqlc.arg(user_id);

-- name: CreatePaidLot :one
-- 산 크레딧의 묶음을 만든다. 처음에는 넣은 만큼 남아 있다.
-- order_id 는 이 크레딧을 산 주문이다. 주문 없이 들어온 것이면 NULL 이다. 주문 하나에 묶음 하나다(paid_lots_order_once).
INSERT INTO paid_lots (user_id, order_id, amount, remaining, created_at)
VALUES (sqlc.arg(user_id), sqlc.narg(order_id), sqlc.arg(amount), sqlc.arg(amount), sqlc.arg(now))
RETURNING id;

-- name: ListOpenPaidLots :many
-- 남은 것이 있는 산 크레딧의 묶음을, 먼저 들어온 것부터 읽는다. 지갑의 줄을 잠근 뒤에 부른다.
SELECT id, remaining
FROM paid_lots
WHERE user_id = sqlc.arg(user_id) AND remaining > 0
ORDER BY created_at, id;

-- name: GetOrderLot :one
-- 그 사용자의 그 주문의 묶음을 읽는다. 청약철회가 "하나도 줄지 않았나"를 본다.
-- 바꾸기 전에 부를 때는 지갑의 줄을 잠근 뒤에 부른다.
SELECT id, amount, remaining
FROM paid_lots
WHERE user_id = sqlc.arg(user_id) AND order_id = sqlc.arg(order_id)::UUID;

-- name: TakeFromPaidLot :exec
-- 산 크레딧의 묶음에서 amount 만큼 뺀다. 남은 것보다 많이 빼면 CHECK 가 막는다.
UPDATE paid_lots
SET remaining = remaining - sqlc.arg(amount)
WHERE id = sqlc.arg(id);

-- name: ReturnToPaidLot :exec
-- 산 크레딧의 묶음에 amount 만큼 돌려놓는다. 넣은 양보다 많아지면 CHECK 가 막는다.
UPDATE paid_lots
SET remaining = remaining + sqlc.arg(amount)
WHERE id = sqlc.arg(id);

-- name: CreateFreeGrant :one
-- 무료 크레딧의 지급 묶음을 만든다. 처음에는 준 만큼 남아 있다.
-- grant_key 는 한 번만 주는 지급의 이름이다. 몇 번이고 줄 수 있는 지급이면 NULL 이다.
INSERT INTO free_grants (user_id, amount, remaining, expires_at, grant_key, created_at)
VALUES (
    sqlc.arg(user_id), sqlc.arg(amount), sqlc.arg(amount), sqlc.arg(expires_at),
    sqlc.narg(grant_key), sqlc.arg(now)
)
RETURNING id;

-- name: HasFreeGrantWithKey :one
-- 이 사용자가 그 이름의 지급을 받은 적이 있는지 본다. 다 썼거나 사라진 것도 받은 것이다.
-- 지갑의 줄을 잠근 뒤에 부른다.
SELECT EXISTS (
    SELECT 1 FROM free_grants
    WHERE user_id = sqlc.arg(user_id) AND grant_key = sqlc.arg(grant_key)::TEXT
);

-- name: CountFreeGrantsWithKey :one
-- 그 이름의 지급을 받은 사람이 users 가운데 몇인지 센다. 한 사람은 같은 이름을 한 번만 받는다(free_grants_key_once).
-- 운영자가 지급하기 전에 미리 보는 것이다. 잠그지 않는다.
SELECT count(*) FROM free_grants
WHERE grant_key = sqlc.arg(grant_key)::TEXT AND user_id = ANY(sqlc.arg(user_ids)::UUID[]);

-- name: CountWallets :one
-- users 가운데 지갑이 있는 사람이 몇인지 센다. 잠그지 않는다.
SELECT count(*) FROM wallets
WHERE user_id = ANY(sqlc.arg(user_ids)::UUID[]);

-- name: ListLiveFreeGrants :many
-- 아직 사라지지 않았고 남은 것이 있는 지급 묶음을, 먼저 사라지는 것부터 읽는다.
-- 지갑의 줄을 잠근 뒤에 부른다. 지급 묶음은 따로 잠그지 않는다.
SELECT id, remaining
FROM free_grants
WHERE user_id = sqlc.arg(user_id) AND remaining > 0 AND expires_at > sqlc.arg(now)
ORDER BY expires_at, id;

-- name: ListDueFreeGrants :many
-- 사라질 시각이 지났는데 아직 남은 것이 있는 지급 묶음을 읽는다. 지갑의 줄을 잠근 뒤에 부른다.
SELECT id, remaining
FROM free_grants
WHERE user_id = sqlc.arg(user_id) AND remaining > 0 AND expires_at <= sqlc.arg(now)
ORDER BY expires_at, id;

-- name: TakeFromFreeGrant :exec
-- 지급 묶음에서 amount 만큼 뺀다. 남은 것보다 많이 빼면 CHECK 가 막는다.
UPDATE free_grants
SET remaining = remaining - sqlc.arg(amount)
WHERE id = sqlc.arg(id);

-- name: InsertEntry :exec
-- 원장에 한 줄을 덧붙인다. 무료 크레딧의 줄은 지급 묶음(grant_id)을, 산 크레딧의 줄은 묶음(lot_id)을 적는다.
INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, grant_id, lot_id, order_id, hold_id, created_at)
VALUES (
    sqlc.arg(user_id), sqlc.arg(operation_id), sqlc.arg(kind), sqlc.arg(reason),
    sqlc.arg(amount), sqlc.narg(grant_id), sqlc.narg(lot_id), sqlc.narg(order_id), sqlc.narg(hold_id), sqlc.arg(now)
);

-- name: ListHoldLines :many
-- 홀드로 뺀 줄들을 읽는다. 어디서 얼마를 뺐는지가 여기에 있다. 돌려줄 때 이 줄들을 거꾸로 한다.
-- 산 크레딧의 줄인데 묶음(lot_id)이 없으면 묶음을 두기 전(00007)에 건 홀드다.
-- 지갑의 줄을 잠근 뒤에 부른다.
SELECT kind, grant_id, lot_id, amount
FROM ledger_entries
WHERE user_id = sqlc.arg(user_id) AND hold_id = sqlc.arg(hold_id)::UUID AND reason = 'hold'
ORDER BY id;

-- name: ReturnToFreeGrant :exec
-- 지급 묶음에 amount 만큼 돌려놓는다. 준 양보다 많아지면 CHECK 가 막는다.
-- 사라지는 시각은 고치지 않는다. 그사이에 기한이 지났으면 돌아온 것도 함께 사라진다.
UPDATE free_grants
SET remaining = remaining + sqlc.arg(amount)
WHERE id = sqlc.arg(id);

-- name: GetBalance :one
-- 산 크레딧과, 아직 사라지지 않은 무료 크레딧을 한 번에 읽는다.
-- 문장 하나라서 두 값이 같은 순간의 것이다. 지갑이 없는 사용자는 모두 0 이다.
SELECT
    COALESCE((SELECT w.paid_balance FROM wallets w WHERE w.user_id = sqlc.arg(user_id)), 0)::BIGINT AS paid,
    COALESCE(SUM(g.remaining), 0)::BIGINT AS free
FROM free_grants g
WHERE g.user_id = sqlc.arg(user_id) AND g.remaining > 0 AND g.expires_at > sqlc.arg(now);

-- name: GetNextFreeExpiry :one
-- 아직 사라지지 않은 무료 크레딧 중 가장 먼저 사라지는 시각과, 그 시각에 사라지는 양을 읽는다.
-- 같은 시각에 사라지는 묶음이 여럿이면 그 양을 더한다. 무료 크레딧이 없으면 줄이 없다.
-- 잔액(GetBalance)과 같은 트랜잭션에서 읽어 같은 순간의 값이 되게 한다(read.go 의 Balance).
SELECT g.expires_at, SUM(g.remaining)::BIGINT AS amount
FROM free_grants g
WHERE g.user_id = sqlc.arg(user_id) AND g.remaining > 0 AND g.expires_at > sqlc.arg(now)
GROUP BY g.expires_at
ORDER BY g.expires_at
LIMIT 1;

-- name: ListEntries :many
-- 한 사용자의 원장을 최근 것부터 읽는다. before 보다 앞선(번호가 작은) 줄만 읽는다.
-- 홀드의 줄(hold, release)에는 그 홀드의 지금 상태(held, captured, released)를 붙인다(#430). 홀드의 줄이 아니면 NULL 이다.
-- 확정은 원장에 줄을 남기지 않으므로, hold 줄만 보고는 아직 기다리는지 쓰였는지 알 수 없다.
SELECT e.id, e.operation_id, e.kind, e.reason, e.amount, e.order_id, e.hold_id, e.created_at, h.status AS hold_status
FROM ledger_entries e
LEFT JOIN holds h ON h.id = e.hold_id
WHERE e.user_id = sqlc.arg(user_id) AND e.id < sqlc.arg(before)
ORDER BY e.id DESC
LIMIT sqlc.arg(row_limit);

-- name: ListUsersWithDueFreeGrants :many
-- 사라질 시각이 지났는데 남은 것이 있는 지급 묶음을 가진 사용자를 limit 명까지 읽는다(정리 작업).
-- 그 사용자의 지갑에 변경이 없어서 "사라졌다"는 원장의 줄이 아직 적히지 않은 것이다.
SELECT DISTINCT user_id FROM free_grants
WHERE remaining > 0 AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ
LIMIT sqlc.arg(row_limit);
