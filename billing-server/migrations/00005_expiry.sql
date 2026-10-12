-- billing-server/migrations/00005_expiry.sql
-- 홀드와 주문에 만료를 둔다. 끝이 열린 것을 남기지 않는다.
--   홀드: 정해 둔 시간(HOLD_TTL) 안에 확정하거나 연장하지 않으면 정리 작업이 돌려준다
--   주문: 정해 둔 시간(ORDER_TTL) 안에 치르지 않으면 정리 작업이 expired 로 끝낸다
-- 무료 크레딧의 사라진 묶음을 정리 작업이 찾을 수 있게 색인을 더한다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up

-- 홀드의 만료 시각. 이미 있는 held 홀드는 지금부터 하루를 준다.
-- 만든 시각으로부터 세면, 이 파일을 적용하자마자 오래된 것이 한꺼번에 풀려 부르는 쪽이 대비할 틈이 없다
ALTER TABLE holds ADD COLUMN expires_at TIMESTAMPTZ;
UPDATE holds SET expires_at = CASE
    WHEN status = 'held' THEN GREATEST(created_at, now()) + interval '24 hours'
    ELSE created_at + interval '24 hours'
END;
ALTER TABLE holds ALTER COLUMN expires_at SET NOT NULL;
ALTER TABLE holds ADD CONSTRAINT holds_expires_after_created CHECK (expires_at > created_at);

-- 돌려준 이유. requested(부르는 쪽이 돌려 달라고 했다) 또는 expired(만료되어 정리 작업이 돌려줬다).
-- 이미 돌려준 것은 모두 부르는 쪽이 돌려 달라고 한 것이다
ALTER TABLE holds ADD COLUMN release_reason TEXT;
UPDATE holds SET release_reason = 'requested' WHERE status = 'released';
ALTER TABLE holds ADD CONSTRAINT holds_release_reason_matches_status CHECK (
    (status = 'released') = (release_reason IS NOT NULL)
    AND (release_reason IS NULL OR release_reason IN ('requested', 'expired'))
);

-- 정리 작업이 "만료된 held 홀드"를 찾는다. 끝난 홀드는 색인에 넣지 않는다
CREATE INDEX holds_held_expiry_idx ON holds (expires_at) WHERE status = 'held';

-- 주문의 만료 시각. 이미 있는 주문은 만든 시각으로부터 센다. pending 주문은 돈이 오간 적이 없어 바로 끝나도 안전하다
ALTER TABLE orders ADD COLUMN expires_at TIMESTAMPTZ;
UPDATE orders SET expires_at = created_at + interval '24 hours';
ALTER TABLE orders ALTER COLUMN expires_at SET NOT NULL;
ALTER TABLE orders ADD CONSTRAINT orders_expires_after_created CHECK (expires_at > created_at);

-- expired(치르지 않은 채 만료됨)를 더한다. pending 에서만 간다. 결제 번호가 없다
ALTER TABLE orders DROP CONSTRAINT orders_status_known;
ALTER TABLE orders ADD CONSTRAINT orders_status_known
    CHECK (status IN ('pending', 'confirming', 'paid', 'failed', 'expired'));
ALTER TABLE orders DROP CONSTRAINT orders_payment_key_matches_status;
ALTER TABLE orders ADD CONSTRAINT orders_payment_key_matches_status
    CHECK ((status IN ('pending', 'expired')) = (payment_key IS NULL));

-- 정리 작업이 "만료된 pending 주문"을, 대사가 "오래된 confirming 주문"을 찾는다
CREATE INDEX orders_pending_expiry_idx ON orders (expires_at) WHERE status = 'pending';
CREATE INDEX orders_confirming_idx ON orders (updated_at) WHERE status = 'confirming';

-- 정리 작업이 "사라질 시각이 지났는데 남은 것이 있는 지급 묶음"을 찾는다.
-- 있는 색인(free_grants_open_idx)은 사용자로 먼저 갈라서, 사용자를 모르고 시각으로만 찾을 때 쓰지 못한다
CREATE INDEX free_grants_due_idx ON free_grants (expires_at) WHERE remaining > 0;

-- +goose Down
-- expired 주문이나 만료로 돌려준 홀드가 있으면 옛 조건을 다시 걸 때 그 줄들이 걸려서 실패하고, 아무것도 바뀌지 않는다.
-- 지우지 않는다. 기록을 지우고 되돌리면 지난 일이 사라진다
DROP INDEX free_grants_due_idx;
DROP INDEX orders_confirming_idx;
DROP INDEX orders_pending_expiry_idx;

ALTER TABLE orders DROP CONSTRAINT orders_payment_key_matches_status;
ALTER TABLE orders ADD CONSTRAINT orders_payment_key_matches_status CHECK ((status = 'pending') = (payment_key IS NULL));
ALTER TABLE orders DROP CONSTRAINT orders_status_known;
ALTER TABLE orders ADD CONSTRAINT orders_status_known CHECK (status IN ('pending', 'confirming', 'paid', 'failed'));
ALTER TABLE orders DROP CONSTRAINT orders_expires_after_created;
ALTER TABLE orders DROP COLUMN expires_at;

DROP INDEX holds_held_expiry_idx;
-- 만료로 돌려준 홀드가 있으면 여기서 멈춘다. 돌려준 이유를 버리면 그것이 만료였는지 알 수 없게 된다
ALTER TABLE holds ADD CONSTRAINT holds_no_expired_release_on_down CHECK (release_reason IS DISTINCT FROM 'expired');
ALTER TABLE holds DROP CONSTRAINT holds_no_expired_release_on_down;
ALTER TABLE holds DROP CONSTRAINT holds_release_reason_matches_status;
ALTER TABLE holds DROP COLUMN release_reason;
ALTER TABLE holds DROP CONSTRAINT holds_expires_after_created;
ALTER TABLE holds DROP COLUMN expires_at;
