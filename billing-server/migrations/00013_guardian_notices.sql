-- billing-server/migrations/00013_guardian_notices.sql
-- 보호자에게 알릴 미성년자의 결제(#352). 인증 서버가 보호자의 이메일로 알린다(이 서버는 보호자의 이메일을 모른다).
--
-- 알릴 일은 주문에서 찾아 적는다. 결제를 끝내는 코드(승인, 입금, 대사, 운영자의 결정)가 여럿이라
-- 그 모두에 "알릴 일 적기"를 넣으면 하나를 빠뜨리기 쉽다. 주문의 상태(paid_at, refunded_at)가 근거라 빠지지 않는다.
-- 정리 작업이 한 바퀴마다 최근 결제와 청약철회 가운데 결제한 날 미성년자였던 것을 찾아 여기에 적고, 인증 서버에 보낸다.
--
-- 미성년자였는지는 결제 자격(00012)의 성년이 되는 날과 결제한 날(한국 날짜)로 가른다. 성년이 된 뒤의 결제는 알리지 않는다.
-- 주문 하나에 결제와 청약철회가 한 번씩이다(order_id, kind). 같은 일을 두 번 적지 않고, 인증 서버도 두 번 보내지 않는다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE guardian_notices (
    order_id UUID NOT NULL REFERENCES orders (id),
    -- paid(결제가 끝났다) 또는 refunded(청약철회가 끝났다)
    kind TEXT NOT NULL,
    user_id UUID NOT NULL,
    -- 알릴 내용. 주문에서 옮겨 적는다
    product_id TEXT NOT NULL,
    price BIGINT NOT NULL,
    credits BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    -- pending(보낼 것) 또는 sent(인증 서버가 받았다)
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    -- 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    PRIMARY KEY (order_id, kind),
    CONSTRAINT guardian_notices_kind_known CHECK (kind IN ('paid', 'refunded')),
    CONSTRAINT guardian_notices_status_known CHECK (status IN ('pending', 'sent')),
    CONSTRAINT guardian_notices_sent_at_matches_status CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);

-- 정리 작업이 "보낼 때가 된 것" 을 찾을 때 쓴다. 보낸 것은 색인에 넣지 않는다
CREATE INDEX guardian_notices_due ON guardian_notices (next_attempt_at) WHERE status = 'pending';

-- 정리 작업이 최근의 결제와 청약철회를 찾을 때 쓴다
CREATE INDEX orders_paid_at ON orders (paid_at) WHERE paid_at IS NOT NULL;
CREATE INDEX orders_refunded_at ON orders (refunded_at) WHERE refunded_at IS NOT NULL;

-- +goose Down
DROP INDEX orders_refunded_at;
DROP INDEX orders_paid_at;
DROP TABLE guardian_notices;
