-- billing-server/migrations/00023_auto_charge.sql
-- 자동 충전(#980)의 첫 단계. 카드를 등록해 두고(빌링키), 골드가 정한 값 아래로 떨어지면 살 상품과 한 달 상한을 적어 둔다.
-- 실제로 결제하는 일(떨어진 것을 적고, 따로 도는 작업이 결제한다)은 다음 단계다. 이 표들은 그때도 그대로 쓴다.
--
-- 고객 키(customer_key)는 결제 대행사가 카드의 주인을 가르는 이름이다. 사용자마다 하나를 무작위로 만든다.
-- 공개 ID 를 그대로 쓰지 않는다. 결제 대행사의 문서가 짐작할 수 있는 값을 쓰지 말라고 한다.
-- 빌링키는 시크릿 키와 함께여야 결제할 수 있다. 그래도 응답과 로그에는 싣지 않는다. 카드 번호는 결제 대행사가 가린 것만 적는다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE billing_customers (
    user_id UUID PRIMARY KEY,
    customer_key UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

-- 등록한 카드. 사람마다 하나다. 다시 등록하면 바꾼다
CREATE TABLE payment_cards (
    user_id UUID PRIMARY KEY REFERENCES billing_customers (user_id),
    billing_key TEXT NOT NULL,
    -- 카드를 낸 곳의 코드(결제 대행사의 issuerCode). 화면이 이름으로 바꾼다
    issuer_code TEXT NOT NULL,
    -- 결제 대행사가 가린 카드 번호(43301234****123* 같은 것)
    card_number TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT payment_cards_billing_key_present CHECK (billing_key <> '')
);

CREATE TABLE auto_charge_settings (
    user_id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    -- 골드가 이 값 아래로 떨어지면 산다
    threshold BIGINT NOT NULL,
    -- 살 상품(catalog 의 번호)
    product_id TEXT NOT NULL,
    -- 한 달(한국 날짜의 달)에 자동으로 결제하는 돈의 상한. 원(KRW)이다
    monthly_limit BIGINT NOT NULL,
    -- 이어서 실패한 수. 성공하거나 다시 켜면 0 이다. 정한 수가 되면 끈다(다음 단계)
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT auto_charge_threshold_not_negative CHECK (threshold >= 0),
    CONSTRAINT auto_charge_monthly_limit_positive CHECK (monthly_limit > 0),
    CONSTRAINT auto_charge_failures_not_negative CHECK (consecutive_failures >= 0)
);

-- +goose Down
DROP TABLE auto_charge_settings;
DROP TABLE payment_cards;
DROP TABLE billing_customers;
