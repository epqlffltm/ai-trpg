-- billing-server/migrations/00026_auto_charge_consents.sql
-- 자동 충전(#980)을 켤 때 받는 자동 결제 동의의 기록. 가입 때가 아니라 켤 때 따로 받는다(2026-11-04 결정).
-- 누가, 어느 판(docs/legal/auto-charge.md)에, 언제, 어떤 조건(기준 골드, 상품과 값, 한 달 상한)으로 동의했는지 적는다.
-- 켜는 설정을 적을 때마다 한 줄을 더한다(조건이 바뀌면 그 조건에 다시 동의한 것이다). 덮어쓰지 않고 지우지 않는다.
-- 탈퇴해도 남긴다. 결제의 근거다(주문처럼).
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE auto_charge_consents (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    terms_version INTEGER NOT NULL,
    -- 동의한 조건. 화면이 동의 문구에 보인 것과 같다
    threshold BIGINT NOT NULL,
    product_id TEXT NOT NULL,
    price BIGINT NOT NULL,
    monthly_limit BIGINT NOT NULL,
    agreed_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT auto_charge_consents_version_positive CHECK (terms_version > 0),
    CONSTRAINT auto_charge_consents_amounts CHECK (threshold >= 0 AND price > 0 AND monthly_limit > 0)
);

-- 그 사람의 마지막 동의를 찾을 때 쓴다
CREATE INDEX auto_charge_consents_user ON auto_charge_consents (user_id, agreed_at DESC, id DESC);

-- +goose Down
-- 동의의 기록이 하나라도 있으면 되돌리지 않는다. 지우면 결제의 근거가 사라진다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM auto_charge_consents) THEN
        RAISE EXCEPTION '자동 결제 동의의 기록이 있어 되돌리지 않는다';
    END IF;
END $$;
-- +goose StatementEnd
DROP TABLE auto_charge_consents;
