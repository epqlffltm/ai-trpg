-- billing-server/migrations/00008_refunds.sql
-- 청약철회(#150 의 2단계). 치른 지 7일 안이고 그 주문의 크레딧이 하나도 줄지 않았으면 사용자가 직접 전액을 취소한다.
--
-- 주문의 상태가 둘 늘어난다.
--   paid -> refunding -> refunded
--                     -> paid       결제 대행사가 취소를 확실히 거절했다. 크레딧을 묶음으로 돌려놓는다
--   - refunding: 그 주문의 묶음을 비웠고, 결제 대행사에 취소를 요청했다. 답을 받기 전이거나 받지 못했다
--   - refunded: 결제 대행사가 취소했다. 돈이 돌아갔다. 묶음은 빈 채로 남는다
--
-- 원장의 이유가 둘 늘어난다. 둘 다 산 크레딧의 줄이고 그 주문의 묶음을 가리킨다.
--   - refund: 청약철회로 묶음을 비웠다(-)
--   - unrefund: 결제 대행사가 취소를 거절해 묶음으로 돌려놓았다(+)
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE orders ADD COLUMN refunded_at TIMESTAMPTZ;

ALTER TABLE orders DROP CONSTRAINT orders_status_known;
ALTER TABLE orders ADD CONSTRAINT orders_status_known
    CHECK (status IN ('pending', 'confirming', 'paid', 'failed', 'expired', 'refunding', 'refunded'));
-- 치른 시각은 치른 뒤의 상태(환불 중, 환불됨)에도 남는다. 7일을 이 시각부터 센다
ALTER TABLE orders DROP CONSTRAINT orders_paid_at_matches_status;
ALTER TABLE orders ADD CONSTRAINT orders_paid_at_matches_status
    CHECK ((status IN ('paid', 'refunding', 'refunded')) = (paid_at IS NOT NULL));
ALTER TABLE orders ADD CONSTRAINT orders_refunded_at_matches_status
    CHECK ((status = 'refunded') = (refunded_at IS NOT NULL));

-- 결과를 모르는 환불을 대사가 찾는다
CREATE INDEX orders_refunding_idx ON orders (updated_at) WHERE status = 'refunding';

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release', 'unrefund') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold', 'refund') AND amount < 0)
    OR (reason = 'regroup' AND amount <> 0)
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release', 'regroup', 'refund', 'unrefund'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);

-- +goose Down
-- 환불을 요청한 주문이나 환불의 원장 줄이 하나라도 있으면 멈추고 아무것도 바꾸지 않는다.
-- 지우고 되돌리면 돈을 돌려준 기록이 사라진다. 처음부터 다시 하려면 스키마를 지우고 다시 만든다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM orders WHERE status IN ('refunding', 'refunded'))
        OR EXISTS (SELECT 1 FROM ledger_entries WHERE reason IN ('refund', 'unrefund')) THEN
        RAISE EXCEPTION '환불의 기록이 있어 되돌리지 않는다';
    END IF;
END;
$$;
-- +goose StatementEnd
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release', 'regroup'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold') AND amount < 0)
    OR (reason = 'regroup' AND amount <> 0)
);

DROP INDEX orders_refunding_idx;
ALTER TABLE orders DROP CONSTRAINT orders_refunded_at_matches_status;
ALTER TABLE orders DROP CONSTRAINT orders_paid_at_matches_status;
ALTER TABLE orders ADD CONSTRAINT orders_paid_at_matches_status CHECK ((status = 'paid') = (paid_at IS NOT NULL));
ALTER TABLE orders DROP CONSTRAINT orders_status_known;
ALTER TABLE orders ADD CONSTRAINT orders_status_known
    CHECK (status IN ('pending', 'confirming', 'paid', 'failed', 'expired'));
ALTER TABLE orders DROP COLUMN refunded_at;
