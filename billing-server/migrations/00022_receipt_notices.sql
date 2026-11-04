-- billing-server/migrations/00022_receipt_notices.sql
-- 결제한 본인에게 메일로 알릴 결제와 청약철회(#553). 인증 서버가 그 계정의 이메일로 알린다(이 서버는 이메일을 모른다).
--
-- 결제 영수증은 결제 대행사(토스페이먼츠)가 보낸다. 우리 메일은 그 메일에 없는 것(받은 크레딧, 청약철회 기한과 하는 길)만 싣는다.
-- 보호자 결제 알림(00013)과 같은 길이다. 알릴 일은 주문에서 찾아 적고(paid_at, refunded_at), 정리 작업이 인증 서버에 보낸다.
-- 결제를 끝내는 코드(승인, 입금, 대사, 운영자의 결정)가 여럿이라 그 모두에 "알릴 일 적기"를 넣지 않는다.
-- 주문 하나에 결제와 청약철회가 한 번씩이다(order_id, kind). 인증 서버도 주문과 종류로 한 번만 보낸다.
--
-- 이 표가 생기기 전의 결제와 청약철회는 알리지 않는다(skipped 로 적어 둔다). 정리 작업은 지난 30일을 거슬러 보므로,
-- 적어 두지 않으면 이 표를 처음 만든 날에 지난 결제의 메일이 한꺼번에 나간다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE receipt_notices (
    order_id UUID NOT NULL REFERENCES orders (id),
    -- paid(결제가 끝났다) 또는 refunded(청약철회가 끝났다)
    kind TEXT NOT NULL,
    user_id UUID NOT NULL,
    -- 알릴 내용. 주문에서 옮겨 적는다
    product_id TEXT NOT NULL,
    price BIGINT NOT NULL,
    credits BIGINT NOT NULL,
    -- 결제가 끝난 시각. 청약철회의 기한은 이 시각부터 센다
    paid_at TIMESTAMPTZ NOT NULL,
    -- 결제나 청약철회가 끝난 시각
    occurred_at TIMESTAMPTZ NOT NULL,
    -- pending(보낼 것), sent(인증 서버가 받았다), skipped(이 표가 생기기 전의 것이라 보내지 않는다)
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    -- 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    PRIMARY KEY (order_id, kind),
    CONSTRAINT receipt_notices_kind_known CHECK (kind IN ('paid', 'refunded')),
    CONSTRAINT receipt_notices_status_known CHECK (status IN ('pending', 'sent', 'skipped')),
    CONSTRAINT receipt_notices_sent_at_matches_status CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);

-- 정리 작업이 "보낼 때가 된 것" 을 찾을 때 쓴다. 보냈거나 건너뛴 것은 색인에 넣지 않는다
CREATE INDEX receipt_notices_due ON receipt_notices (next_attempt_at) WHERE status = 'pending';

-- 이미 끝난 결제와 청약철회는 알리지 않는다고 적어 둔다
INSERT INTO receipt_notices (order_id, kind, user_id, product_id, price, credits, paid_at, occurred_at, status, next_attempt_at, created_at)
SELECT id, 'paid', user_id, product_id, price, credits, paid_at, paid_at, 'skipped', now(), now()
FROM orders WHERE paid_at IS NOT NULL;

INSERT INTO receipt_notices (order_id, kind, user_id, product_id, price, credits, paid_at, occurred_at, status, next_attempt_at, created_at)
SELECT id, 'refunded', user_id, product_id, price, credits, paid_at, refunded_at, 'skipped', now(), now()
FROM orders WHERE refunded_at IS NOT NULL AND paid_at IS NOT NULL;

-- +goose Down
DROP TABLE receipt_notices;
