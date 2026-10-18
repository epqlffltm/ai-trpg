-- billing-server/internal/pricing/queries.sql
-- 가격표를 읽고 덧붙이는 SQL. sqlc 가 이 파일을 읽어 Go 코드(pricingdb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 가격표는 덧붙이기만 한다. 고치거나 지우는 문장이 없다(DB 의 트리거도 막는다).

-- name: CurrentPrice :one
-- 그 이름의 지금 값이 적힌 줄을 읽는다. 적용 시각이 now 보다 늦지 않은 줄 가운데 가장 늦은 줄이다.
-- 줄이 없으면 그런 이름이 없는 것이고, amount 가 NULL 이면 판매를 멈춘 것이다.
SELECT * FROM price_versions
WHERE code = sqlc.arg(code) AND effective_at <= sqlc.arg(now)::TIMESTAMPTZ
ORDER BY effective_at DESC
LIMIT 1;

-- name: CurrentPrices :many
-- 이름마다 지금 값이 적힌 줄을 읽는다. 판매를 멈춘 이름도 함께 읽는다(amount 가 NULL).
SELECT DISTINCT ON (code) *
FROM price_versions
WHERE effective_at <= sqlc.arg(now)::TIMESTAMPTZ
ORDER BY code, effective_at DESC;

-- name: PriceHistory :many
-- 그 이름의 모든 줄을 적용 시각 순서로 읽는다. 아직 적용되지 않은 예약도 함께 읽는다.
SELECT * FROM price_versions
WHERE code = sqlc.arg(code)
ORDER BY effective_at, id;

-- name: InsertPriceVersion :one
-- 가격표에 줄 하나를 덧붙인다. amount 가 NULL 이면 판매를 멈추는 줄이다. 등급(tier)과 행사가 표시(promo)는 늘 적는다.
INSERT INTO price_versions (code, amount, tier, promo, effective_at, reason, changed_by, created_at)
VALUES (
    sqlc.arg(code), sqlc.narg(amount), sqlc.arg(tier), sqlc.arg(promo), sqlc.arg(effective_at), sqlc.arg(reason), sqlc.arg(changed_by), sqlc.arg(now)
)
RETURNING *;

-- name: HasLaterVersion :one
-- 그 이름에 적용 시각이 after 보다 늦은 줄이 있는지 본다. 행사가 줄은 끝나는 때(다음 줄)가 먼저 있어야 한다.
SELECT EXISTS (
    SELECT 1 FROM price_versions WHERE code = sqlc.arg(code) AND effective_at > sqlc.arg(after)::TIMESTAMPTZ
);

-- name: UpcomingPrices :many
-- 이름마다 아직 적용되지 않은 줄 가운데 가장 이른 줄을 읽는다(다음에 바뀔 값). 판매를 멈추는 예약도 함께 읽는다(amount 가 NULL).
SELECT DISTINCT ON (code) *
FROM price_versions
WHERE effective_at > sqlc.arg(now)::TIMESTAMPTZ
ORDER BY code, effective_at;

