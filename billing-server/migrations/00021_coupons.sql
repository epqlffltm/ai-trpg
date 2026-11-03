-- billing-server/migrations/00021_coupons.sql
-- 쿠폰(#979). 운영자가 코드를 만들고(cmd/coupons), 사용자가 코드를 넣으면 실버(무료 크레딧)를 받는다.
--
--   coupons             쿠폰 하나. 한 코드를 여럿이 쓴다(공용 코드). 한 사람은 한 번만 받는다. 전체 사용 한도가 있을 수 있다
--   coupon_redemptions  누가 언제 받았나. 쿠폰과 사용자에 하나다. 같은 요청을 두 번 보내도 한 줄만 적힌다
--   coupon_attempts     사람마다 틀린 코드를 넣은 수. 한 시간 창마다 센다. 마구 넣어 보는 것을 막는다(429)
--
-- 실버는 지갑의 한 번만 주는 지급(free_grants.grant_key = 'coupon-<번호>')으로 넣는다. 받은 기록과 지갑이 두 겹으로 막는다.
-- 골드(산 크레딧)는 주지 않는다(2026-11-03 결정). 환불과 청약철회의 계산에 들어가서다.
-- 받은 기록은 탈퇴해도 남긴다(출석의 기록과 같다. 공개 ID 만 있다).
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE coupons (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- 사용자가 넣는 글. 대문자와 숫자와 붙임표다. 넣을 때 앞뒤 빈칸을 지우고 대문자로 바꿔 찾는다
    code TEXT NOT NULL UNIQUE,
    -- 한 사람이 받는 실버
    silver BIGINT NOT NULL,
    -- 받은 실버가 사라질 때까지의 날 수. 비우면 다른 무료 크레딧과 같다(FREE_CREDIT_TTL)
    silver_days INTEGER,
    -- 넣을 수 있는 때. starts_at 부터 ends_at 전까지다
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    -- 모두 합쳐 몇 명이 받을 수 있나. 비우면 한도가 없다. 1 이면 한 사람용처럼 쓴다
    max_redemptions INTEGER,
    -- 지금까지 받은 사람의 수. 받을 때 한도와 함께 본다
    redemptions INTEGER NOT NULL DEFAULT 0,
    -- 운영자가 멈춘 시각. 멈춘 쿠폰은 더 받을 수 없다. 이미 받은 실버는 그대로다
    stopped_at TIMESTAMPTZ,
    -- 만든 운영자(명령의 -by)와 까닭
    created_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT coupons_code_shape CHECK (code ~ '^[A-Z0-9-]{4,32}$'),
    CONSTRAINT coupons_silver_positive CHECK (silver > 0),
    CONSTRAINT coupons_silver_days_range CHECK (silver_days IS NULL OR silver_days BETWEEN 1 AND 365),
    CONSTRAINT coupons_period CHECK (ends_at > starts_at),
    CONSTRAINT coupons_max_positive CHECK (max_redemptions IS NULL OR max_redemptions >= 1),
    CONSTRAINT coupons_redemptions_in_range CHECK (
        redemptions >= 0 AND (max_redemptions IS NULL OR redemptions <= max_redemptions)
    )
);

CREATE TABLE coupon_redemptions (
    coupon_id BIGINT NOT NULL REFERENCES coupons (id),
    user_id UUID NOT NULL,
    silver BIGINT NOT NULL,
    -- 받은 실버가 사라지는 시각
    expires_at TIMESTAMPTZ NOT NULL,
    redeemed_at TIMESTAMPTZ NOT NULL,
    -- 한 사람은 한 쿠폰을 한 번만 받는다
    PRIMARY KEY (coupon_id, user_id),
    CONSTRAINT coupon_redemptions_silver_positive CHECK (silver > 0)
);

CREATE TABLE coupon_attempts (
    user_id UUID PRIMARY KEY,
    -- 지금 세는 창이 열린 시각. 한 시간이 지나면 새 창을 연다
    window_started_at TIMESTAMPTZ NOT NULL,
    -- 그 창에서 틀린 코드를 넣은 수
    failures INTEGER NOT NULL,
    CONSTRAINT coupon_attempts_failures_positive CHECK (failures >= 1)
);

-- +goose Down
-- 받은 사람이 있으면 멈추고 아무것도 바꾸지 않는다. 지갑의 지급(coupon-<번호>)이 이 기록을 가리킨다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM coupon_redemptions) THEN
        RAISE EXCEPTION '쿠폰을 받은 기록이 있어 되돌리지 않는다';
    END IF;
END;
$$;
-- +goose StatementEnd
DROP TABLE coupon_attempts;
DROP TABLE coupon_redemptions;
DROP TABLE coupons;
