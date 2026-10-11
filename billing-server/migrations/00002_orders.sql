-- billing-server/migrations/00002_orders.sql
-- 주문 테이블을 만들고, 원장의 줄이 어느 주문으로 들어온 크레딧인지 가리키게 한다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up

-- 크레딧을 사려는 주문 하나가 한 줄이다. 상태는 한 방향으로만 흐른다.
--   pending(만듦) -> confirming(결제 대행사에 승인을 요청함) -> paid(승인됨, 크레딧이 들어감) 또는 failed(거절됨)
-- 지갑과 외래 키로 잇지 않는다. 한 번도 충전하지 않은 사용자는 지갑이 없다
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    -- 주문할 때의 상품과 값을 적어 둔다. 나중에 가격표가 바뀌어도 지난 주문은 그대로다
    product_id TEXT NOT NULL,
    -- 값은 원(KRW)이다. 원에는 소수가 없다
    price BIGINT NOT NULL,
    credits BIGINT NOT NULL,
    status TEXT NOT NULL,
    -- 클라이언트가 요청마다 붙이는 키. 같은 요청이 다시 와도 주문이 하나만 생긴다
    idempotency_key TEXT NOT NULL,
    -- 결제 대행사가 결제 한 건에 붙인 번호. 승인을 요청할 때 적힌다
    payment_key TEXT,
    -- 거절된 이유. 결제 대행사가 준 글자를 그대로 적는다
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    CONSTRAINT orders_price_positive CHECK (price > 0),
    CONSTRAINT orders_credits_positive CHECK (credits > 0),
    CONSTRAINT orders_status_known CHECK (status IN ('pending', 'confirming', 'paid', 'failed')),
    -- 한 사용자가 같은 키로 주문을 둘 만들 수 없다
    CONSTRAINT orders_idempotency_key_once UNIQUE (user_id, idempotency_key),
    -- 결제 한 건으로 주문 둘을 치를 수 없다
    CONSTRAINT orders_payment_key_once UNIQUE (payment_key),
    -- 상태와 칸이 맞아야 한다. 승인을 요청하기 전에는 결제 번호가 없고, 요청한 뒤에는 반드시 있다
    CONSTRAINT orders_payment_key_matches_status CHECK ((status = 'pending') = (payment_key IS NULL)),
    CONSTRAINT orders_paid_at_matches_status CHECK ((status = 'paid') = (paid_at IS NOT NULL)),
    CONSTRAINT orders_failure_code_matches_status CHECK ((status = 'failed') = (failure_code IS NOT NULL))
);

-- 원장의 충전 줄이 어느 주문의 것인지 적는다
ALTER TABLE ledger_entries ADD COLUMN order_id UUID REFERENCES orders (id);

-- 주문은 산 크레딧이 들어온 줄에만 적힌다
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_order_only_on_deposit
    CHECK (order_id IS NULL OR (kind = 'paid' AND reason = 'deposit'));

-- 주문 하나로 크레딧이 두 번 들어올 수 없다. 코드가 같은 주문을 두 번 처리해도 둘째 줄은 DB 가 거절한다
CREATE UNIQUE INDEX ledger_entries_order_once ON ledger_entries (order_id) WHERE order_id IS NOT NULL;

-- +goose Down
DROP INDEX ledger_entries_order_once;
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_order_only_on_deposit;
ALTER TABLE ledger_entries DROP COLUMN order_id;
DROP TABLE orders;
