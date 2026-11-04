-- billing-server/migrations/00024_auto_charge_requests.sql
-- 자동 충전(#980)의 둘째 단계. 골드가 기준 아래로 떨어지면 "충전할 일"을 적고, 따로 도는 작업(cmd/autocharge)이 결제한다.
--
-- 떨어진 것은 홀드를 거는 트랜잭션이 적는다(지갑을 잠근 채). 결제 대행사는 부르지 않는다. 요청의 길이 느려지지 않는다.
-- 한 번 떨어지면 한 번만 산다(armed). 적으면 armed 가 꺼지고, 골드가 다시 기준 이상인 것을 보면(또는 다시 켜면) 켜진다.
-- 그래서 결제가 실패해도 다음 홀드마다 다시 결제하지 않는다.
--
-- 충전할 일의 번호(id)가 결제 대행사의 주문 번호이자 멱등키다. 답을 받지 못하면 같은 번호로 같은 결제를 다시 보낸다.
-- 결제 대행사는 같은 멱등키에 처음의 답을 준다. 그래서 돈이 두 번 나가지 않는다.
-- 승인되면 같은 번호로 주문(channel auto, paid)을 적고 골드를 넣는다. 한 트랜잭션이다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE auto_charge_settings ADD COLUMN armed BOOLEAN NOT NULL DEFAULT false;
-- 이미 켠 사람은 다음에 떨어질 때 산다
UPDATE auto_charge_settings SET armed = true WHERE enabled;

CREATE TABLE auto_charge_requests (
    -- 결제 대행사의 주문 번호이자 멱등키. 승인되면 같은 번호의 주문이 생긴다
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    -- 적을 때의 상품과 값. 설정이 바뀌어도 이 일은 이 값으로 끝난다
    product_id TEXT NOT NULL,
    price BIGINT NOT NULL,
    credits BIGINT NOT NULL,
    -- pending(아직 보내지 않았다), charging(보냈다. 답을 받거나 다시 보낸다),
    -- paid(승인), declined(거절), skipped(보내기 전에 그만뒀다: 꺼짐, 카드 없음, 결제 자격, 한 달 상한)
    status TEXT NOT NULL DEFAULT 'pending',
    skip_reason TEXT NOT NULL DEFAULT '',
    failure_code TEXT NOT NULL DEFAULT '',
    -- 보낼 때 정한 카드. 다시 보낼 때 같은 카드로 보낸다(그새 카드를 바꾸거나 지워도). 끝나면 지운다
    billing_key TEXT,
    customer_key UUID,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    -- 이 시각부터 보낼 수 있다. 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    CONSTRAINT auto_charge_requests_status_known CHECK (status IN ('pending', 'charging', 'paid', 'declined', 'skipped')),
    CONSTRAINT auto_charge_requests_price_positive CHECK (price > 0 AND credits > 0),
    CONSTRAINT auto_charge_requests_finished_matches_status
        CHECK ((status IN ('paid', 'declined', 'skipped')) = (finished_at IS NOT NULL)),
    -- 보낸 일은 카드를 들고 있다. 끝난 일은 들고 있지 않다
    CONSTRAINT auto_charge_requests_card_while_charging
        CHECK ((status = 'charging') = (billing_key IS NOT NULL AND customer_key IS NOT NULL))
);

-- 한 사람에게 끝나지 않은 일은 하나다
CREATE UNIQUE INDEX auto_charge_requests_one_open ON auto_charge_requests (user_id) WHERE status IN ('pending', 'charging');
-- 작업이 "보낼 때가 된 것" 을 찾을 때 쓴다
CREATE INDEX auto_charge_requests_due ON auto_charge_requests (next_attempt_at) WHERE status IN ('pending', 'charging');

-- 자동 충전으로 치른 주문의 길
ALTER TABLE orders DROP CONSTRAINT orders_channel_known;
ALTER TABLE orders ADD CONSTRAINT orders_channel_known CHECK (channel IN ('web', 'auto'));

-- +goose Down
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM orders WHERE channel = 'auto') OR EXISTS (SELECT 1 FROM auto_charge_requests WHERE status = 'charging') THEN
        RAISE EXCEPTION '자동 충전으로 치른 주문이나 결과를 모르는 자동 결제가 있어 되돌리지 않는다';
    END IF;
END $$;
-- +goose StatementEnd
ALTER TABLE orders DROP CONSTRAINT orders_channel_known;
ALTER TABLE orders ADD CONSTRAINT orders_channel_known CHECK (channel IN ('web'));
DROP TABLE auto_charge_requests;
ALTER TABLE auto_charge_settings DROP COLUMN armed;
