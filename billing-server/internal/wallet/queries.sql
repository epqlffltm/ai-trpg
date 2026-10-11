-- billing-server/internal/wallet/queries.sql
-- 지갑, 무료 크레딧의 지급 묶음, 원장을 읽고 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(walletdb)를 만든다.
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

-- name: CreateFreeGrant :one
-- 무료 크레딧의 지급 묶음을 만든다. 처음에는 준 만큼 남아 있다.
INSERT INTO free_grants (user_id, amount, remaining, expires_at, created_at)
VALUES (sqlc.arg(user_id), sqlc.arg(amount), sqlc.arg(amount), sqlc.arg(expires_at), sqlc.arg(now))
RETURNING id;

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
-- 원장에 한 줄을 덧붙인다.
INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, grant_id, order_id, created_at)
VALUES (
    sqlc.arg(user_id), sqlc.arg(operation_id), sqlc.arg(kind), sqlc.arg(reason),
    sqlc.arg(amount), sqlc.narg(grant_id), sqlc.narg(order_id), sqlc.arg(now)
);

-- name: GetBalance :one
-- 산 크레딧과, 아직 사라지지 않은 무료 크레딧을 한 번에 읽는다.
-- 문장 하나라서 두 값이 같은 순간의 것이다. 지갑이 없는 사용자는 모두 0 이다.
SELECT
    COALESCE((SELECT w.paid_balance FROM wallets w WHERE w.user_id = sqlc.arg(user_id)), 0)::BIGINT AS paid,
    COALESCE(SUM(g.remaining), 0)::BIGINT AS free
FROM free_grants g
WHERE g.user_id = sqlc.arg(user_id) AND g.remaining > 0 AND g.expires_at > sqlc.arg(now);

-- name: ListEntries :many
-- 한 사용자의 원장을 최근 것부터 읽는다. before 보다 앞선(번호가 작은) 줄만 읽는다.
SELECT id, operation_id, kind, reason, amount, order_id, created_at
FROM ledger_entries
WHERE user_id = sqlc.arg(user_id) AND id < sqlc.arg(before)
ORDER BY id DESC
LIMIT sqlc.arg(row_limit);
