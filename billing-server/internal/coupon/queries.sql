-- billing-server/internal/coupon/queries.sql
-- 쿠폰을 적고 읽는 SQL(#979). sqlc 가 이 파일을 읽어 Go 코드(coupondb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.

-- name: CreateCoupon :one
-- 쿠폰을 만든다. 같은 코드가 있으면 유일 제약이 막는다.
INSERT INTO coupons (code, silver, silver_days, starts_at, ends_at, max_redemptions, created_by, reason, created_at)
VALUES (
    sqlc.arg(code), sqlc.arg(silver), sqlc.narg(silver_days), sqlc.arg(starts_at), sqlc.arg(ends_at),
    sqlc.narg(max_redemptions), sqlc.arg(created_by), sqlc.arg(reason), sqlc.arg(now)
)
RETURNING *;

-- name: ListCoupons :many
-- 최근에 만든 쿠폰부터 limit 개.
SELECT * FROM coupons ORDER BY id DESC LIMIT sqlc.arg(row_limit);

-- name: LockCouponByCode :one
-- 받을 쿠폰을 잠그고 읽는다. 같은 쿠폰을 받는 요청들이 차례로 지나가며, 뒤의 것은 앞의 것이 늘린 수를 본다(전체 한도).
SELECT * FROM coupons WHERE code = sqlc.arg(code) FOR UPDATE;

-- name: StopCoupon :execrows
-- 쿠폰을 멈춘다. 이미 멈췄으면 시각을 바꾸지 않는다(바뀐 줄이 0 이다).
UPDATE coupons SET stopped_at = sqlc.arg(now)::TIMESTAMPTZ WHERE code = sqlc.arg(code) AND stopped_at IS NULL;

-- name: CouponExists :one
SELECT EXISTS (SELECT 1 FROM coupons WHERE code = sqlc.arg(code));

-- name: InsertRedemption :execrows
-- 받은 것을 적는다. 그 사람이 이미 받았으면 적지 않는다(바뀐 줄이 0 이다).
INSERT INTO coupon_redemptions (coupon_id, user_id, silver, expires_at, redeemed_at)
VALUES (sqlc.arg(coupon_id), sqlc.arg(user_id), sqlc.arg(silver), sqlc.arg(expires_at), sqlc.arg(now))
ON CONFLICT (coupon_id, user_id) DO NOTHING;

-- name: CountRedemption :exec
-- 받은 사람의 수를 하나 늘린다. 쿠폰을 잠근 트랜잭션 안에서 부른다. 한도를 넘으면 제약(coupons_redemptions_in_range)이 막는다.
UPDATE coupons SET redemptions = redemptions + 1 WHERE id = sqlc.arg(id);

-- name: GetAttempts :one
-- 그 사람의 지금 창의 틀린 수.
SELECT window_started_at, failures FROM coupon_attempts WHERE user_id = sqlc.arg(user_id);

-- name: RecordFailure :exec
-- 틀린 코드를 하나 센다. 창이 끝났으면(window_started_at 이 stale_before 이전) 새 창을 열고 1 부터 센다.
INSERT INTO coupon_attempts (user_id, window_started_at, failures)
VALUES (sqlc.arg(user_id), sqlc.arg(now), 1)
ON CONFLICT (user_id) DO UPDATE SET
    window_started_at = CASE
        WHEN coupon_attempts.window_started_at <= sqlc.arg(stale_before) THEN EXCLUDED.window_started_at
        ELSE coupon_attempts.window_started_at
    END,
    failures = CASE
        WHEN coupon_attempts.window_started_at <= sqlc.arg(stale_before) THEN 1
        ELSE coupon_attempts.failures + 1
    END;
