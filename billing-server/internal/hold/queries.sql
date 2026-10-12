-- billing-server/internal/hold/queries.sql
-- 홀드를 읽고 쓰는 SQL. sqlc 가 이 파일을 읽어 Go 코드(holddb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 상태를 바꾸는 문장은 "지금 held 일 때만"이라는 조건을 단다. 두 요청이 함께 와도 한쪽만 바꾼다.

-- name: InsertHold :one
-- 홀드를 만든다. 같은 서버가 같은 이름표로 이미 걸었으면 아무것도 하지 않고 줄도 돌려주지 않는다.
INSERT INTO holds (id, user_id, source, reference, price_code, amount, status, created_at, updated_at, expires_at)
VALUES (
    sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(source), sqlc.arg(reference), sqlc.arg(price_code),
    sqlc.arg(amount), 'held', sqlc.arg(now), sqlc.arg(now), sqlc.arg(expires_at)
)
ON CONFLICT (source, reference) DO NOTHING
RETURNING *;

-- name: GetHoldByReference :one
-- 그 서버가 그 이름표로 건 홀드를 읽는다.
SELECT * FROM holds
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference);

-- name: CaptureHold :one
-- held 인 홀드를 captured 로 바꾼다. 만료 시각이 지났어도 정리 작업이 아직 돌려주지 않았으면 확정할 수 있다.
UPDATE holds
SET status = 'captured', settled_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference) AND status = 'held'
RETURNING *;

-- name: ReleaseHold :one
-- 부르는 쪽이 돌려 달라고 한 held 홀드를 released 로 바꾼다.
UPDATE holds
SET status = 'released', release_reason = 'requested',
    settled_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference) AND status = 'held'
RETURNING *;

-- name: ExpireHold :one
-- 만료 시각이 지난 held 홀드를 released 로 바꾼다(정리 작업). 그사이에 연장되었으면 바꾸지 않는다.
UPDATE holds
SET status = 'released', release_reason = 'expired',
    settled_at = sqlc.arg(now)::TIMESTAMPTZ, updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE id = sqlc.arg(id) AND status = 'held' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ
RETURNING *;

-- name: ExtendHold :one
-- held 인 홀드의 만료 시각을 뒤로 민다. 앞으로 당기지는 않는다(GREATEST).
UPDATE holds
SET expires_at = GREATEST(expires_at, sqlc.arg(expires_at)::TIMESTAMPTZ), updated_at = sqlc.arg(now)::TIMESTAMPTZ
WHERE source = sqlc.arg(source) AND reference = sqlc.arg(reference) AND status = 'held'
RETURNING *;

-- name: ListExpiredHolds :many
-- 만료 시각이 지났는데 아직 held 인 홀드를 오래된 것부터 읽는다(정리 작업).
SELECT id FROM holds
WHERE status = 'held' AND expires_at <= sqlc.arg(now)::TIMESTAMPTZ
ORDER BY expires_at, id
LIMIT sqlc.arg(row_limit);
