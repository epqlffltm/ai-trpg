-- billing-server/internal/hold/queries.sql
-- 홀드를 읽고 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(holddb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 상태를 바꾸는 문장은 "지금 held 일 때만"이라는 조건을 단다. 두 요청이 함께 와도 한쪽만 바꾼다.

-- name: InsertHold :one
-- 홀드를 만든다. 같은 서버가 같은 이름표로 이미 걸었으면 아무것도 하지 않고 줄도 돌려주지 않는다.
INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at)
VALUES (
    sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(source), sqlc.arg(reference), sqlc.arg(price_code),
    sqlc.arg(amount), 'held', sqlc.arg(now), sqlc.arg(now)
)
ON CONFLICT (source, reference) DO NOTHING
RETURNING *;

-- name: GetHoldByReference :one
-- 그 서버가 그 이름표로 건 홀드를 읽는다.
SELECT * FROM holds
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference);

-- name: SettleHold :one
-- held 인 홀드를 captured 나 released 로 바꾼다.
UPDATE holds
SET status = sqlc.arg(status), settled_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference) AND status = 'held'
RETURNING *;
