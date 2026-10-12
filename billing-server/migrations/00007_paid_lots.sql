-- billing-server/migrations/00007_paid_lots.sql
-- 산 크레딧을 주문마다 따로 남긴다(#150 의 1단계). 청약철회(2단계)가 "그 주문의 크레딧이 하나도 줄지 않았나"를 알아야 한다.
--
-- 지금까지 산 크레딧은 지갑의 한 칸(paid_balance)이었다. 이제 들어올 때마다 묶음(paid_lots) 하나가 생기고,
-- 쓸 때는 먼저 들어온 묶음부터 뺀다. 무료 크레딧의 지급 묶음(free_grants)과 같은 모양이다. 다만 사라지지 않는다.
-- 지갑의 칸은 그대로 둔다. 잔액을 한 번에 읽으려는 것이다. "지갑의 칸 = 묶음들의 남은 양의 합"이다.
--
-- 원장의 산 크레딧 줄은 어느 묶음에서 빠지거나 들어왔는지(lot_id)를 적는다. "묶음의 남은 양 = 그 묶음의 원장 줄의 합"이다.
--
-- 이미 있던 잔액은 이 파일이 묶음으로 나눈다. 먼저 산 것부터 써 왔다고 보면 남은 잔액은 가장 최근 주문들의 몫이다.
--   1. 치른 주문마다 묶음을 만든다. 남은 양은 잔액을 최근 주문부터 채운 만큼이다(다 쓴 주문은 0)
--   2. 그래도 남는 잔액(주문 없이 들어온 것)은 주문이 없는 묶음 하나로 둔다. 가장 먼저 쓰이게 지갑을 만든 시각을 준다
--   3. 원장에 옮긴 기록(regroup)을 덧붙인다. 지갑마다 "묶음 없는 잔액에서 -잔액", "묶음마다 +남은 양". 합은 0 이다
-- 원장의 옛 줄은 고치지 않는다(고칠 수도 없다). 그래서 옛 산 크레딧 줄에는 묶음이 없다.
--
-- 이 파일을 적용할 때 걸려 있던 홀드는 묶음 없이 뺀 줄을 가지고 있다. 그 홀드를 돌려주면 크레딧은 묶음 없이 돌아오고,
-- 곧바로 주문 없는 새 묶음으로 옮긴다(regroup). 코드(wallet)가 한다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE paid_lots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES wallets (user_id),
    -- 이 크레딧을 산 주문. 주문 없이 들어온 것(옮겨 온 잔액, 돌아온 옛 홀드)은 NULL 이다
    order_id UUID REFERENCES orders (id),
    amount BIGINT NOT NULL,
    remaining BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT paid_lots_amount_positive CHECK (amount > 0),
    CONSTRAINT paid_lots_remaining_in_range CHECK (remaining >= 0 AND remaining <= amount)
);

-- 주문 하나에 묶음 하나다
CREATE UNIQUE INDEX paid_lots_order_once ON paid_lots (order_id) WHERE order_id IS NOT NULL;
-- 쓸 수 있는 묶음을 먼저 들어온 것부터 찾는다
CREATE INDEX paid_lots_open_idx ON paid_lots (user_id, created_at, id) WHERE remaining > 0;

ALTER TABLE ledger_entries ADD COLUMN lot_id BIGINT REFERENCES paid_lots (id);
CREATE INDEX ledger_entries_lot_idx ON ledger_entries (lot_id) WHERE lot_id IS NOT NULL;

-- 옮긴 기록(regroup)은 산 크레딧의 줄이다. 묶음 없는 잔액에서 빠지는 줄(-)과 묶음으로 들어가는 줄(+)이 짝을 이룬다
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold') AND amount < 0)
    OR (reason = 'regroup' AND amount <> 0)
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release', 'regroup'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);
-- 묶음은 산 크레딧의 줄에만 적힌다
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_lot_only_on_paid CHECK (lot_id IS NULL OR kind = 'paid');
-- 옮긴 기록은 빠지는 줄에 묶음이 없고 들어가는 줄에 묶음이 있다
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_regroup_lot CHECK (
    reason <> 'regroup' OR ((amount < 0) = (lot_id IS NULL))
);

-- 홀드 하나가 산 크레딧의 묶음 여럿에서 뺄 수 있다. 같은 홀드, 같은 이유, 같은 묶음의 줄은 하나다
DROP INDEX ledger_entries_hold_line_once;
CREATE UNIQUE INDEX ledger_entries_hold_line_once
    ON ledger_entries (hold_id, reason, COALESCE(grant_id, 0), COALESCE(lot_id, 0))
    WHERE hold_id IS NOT NULL;

-- 1. 치른 주문마다 묶음. 잔액을 최근 주문부터 채운다
INSERT INTO paid_lots (user_id, order_id, amount, remaining, created_at)
SELECT o.user_id, o.id, o.credits,
       GREATEST(0, LEAST(o.credits, w.paid_balance - COALESCE((SUM(o.credits) OVER (
           PARTITION BY o.user_id ORDER BY o.paid_at DESC, o.id DESC
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
       ))::BIGINT, 0))),
       o.paid_at
FROM orders o
JOIN wallets w ON w.user_id = o.user_id
WHERE o.status = 'paid'
ORDER BY o.paid_at, o.id;

-- 2. 주문으로 다 채우고도 남는 잔액은 주문 없는 묶음 하나로
INSERT INTO paid_lots (user_id, order_id, amount, remaining, created_at)
SELECT w.user_id, NULL, w.paid_balance - COALESCE(l.total, 0), w.paid_balance - COALESCE(l.total, 0), w.created_at
FROM wallets w
LEFT JOIN (SELECT user_id, SUM(remaining)::BIGINT AS total FROM paid_lots GROUP BY user_id) l ON l.user_id = w.user_id
WHERE w.paid_balance > COALESCE(l.total, 0);

-- 3. 원장에 옮긴 기록. 지갑마다 작업 번호 하나로 묶는다
INSERT INTO ledger_entries (user_id, operation_id, kind, reason, amount, lot_id, created_at)
WITH moved AS MATERIALIZED (
    SELECT user_id, gen_random_uuid() AS operation_id, paid_balance FROM wallets WHERE paid_balance > 0
)
SELECT user_id, operation_id, 'paid', 'regroup', amount, lot_id, now()
FROM (
    SELECT m.user_id, m.operation_id, -m.paid_balance AS amount, NULL::BIGINT AS lot_id FROM moved m
    UNION ALL
    SELECT l.user_id, m.operation_id, l.remaining, l.id FROM paid_lots l JOIN moved m ON m.user_id = l.user_id
    WHERE l.remaining > 0
) lines
ORDER BY user_id, lot_id NULLS FIRST;

-- 이제부터 적는 산 크레딧의 줄에는 묶음이 있어야 한다. 옛 줄은 묶음이 없으므로 새 줄에만 건다(NOT VALID).
-- 묶음 없는 줄은 옮긴 기록의 빠지는 줄과, 옛 홀드가 돌아오는 줄뿐이다
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_paid_has_lot
    CHECK (kind <> 'paid' OR lot_id IS NOT NULL OR reason IN ('regroup', 'release')) NOT VALID;

-- +goose Down
-- 묶음이 하나라도 있으면 멈추고 아무것도 바꾸지 않는다. 묶음과 옮긴 기록을 지우면 주문마다의 몫이 사라지고,
-- 원장의 줄은 지울 수 없어서 옛 조건을 다시 걸 수도 없다. 처음부터 다시 하려면 스키마를 지우고 다시 만든다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM paid_lots) THEN
        RAISE EXCEPTION '산 크레딧의 묶음이 있어 되돌리지 않는다';
    END IF;
END;
$$;
-- +goose StatementEnd
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_paid_has_lot;

DROP INDEX ledger_entries_hold_line_once;
CREATE UNIQUE INDEX ledger_entries_hold_line_once
    ON ledger_entries (hold_id, reason, COALESCE(grant_id, 0))
    WHERE hold_id IS NOT NULL;

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_regroup_lot;
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_lot_only_on_paid;
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold') AND amount < 0)
);

DROP INDEX ledger_entries_lot_idx;
ALTER TABLE ledger_entries DROP COLUMN lot_id;
DROP TABLE paid_lots;
