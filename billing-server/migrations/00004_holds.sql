-- billing-server/migrations/00004_holds.sql
-- 홀드 테이블을 만들고, 원장이 홀드로 빠지고 돌아온 크레딧을 적을 수 있게 한다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up

-- 홀드 하나가 한 줄이다. 값을 치르기 전에 크레딧을 먼저 빼 두는 것이다.
--   held(빼 뒀다) -> captured(확정했다. 크레딧은 돌아오지 않는다) 또는 released(돌려줬다)
CREATE TABLE holds (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    -- 홀드를 건 서버의 이름(trpg-server)과, 그 서버가 붙인 이름표. 같은 이름표로 홀드를 둘 걸 수 없다
    source TEXT NOT NULL,
    reference TEXT NOT NULL,
    -- 걸 때의 가격표 이름과 값을 적어 둔다. 나중에 가격표가 바뀌어도 이미 건 홀드는 그대로다
    price_code TEXT NOT NULL,
    amount BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    -- 확정하거나 돌려준 시각
    settled_at TIMESTAMPTZ,
    CONSTRAINT holds_amount_positive CHECK (amount > 0),
    CONSTRAINT holds_status_known CHECK (status IN ('held', 'captured', 'released')),
    CONSTRAINT holds_reference_once UNIQUE (source, reference),
    CONSTRAINT holds_settled_at_matches_status CHECK ((status = 'held') = (settled_at IS NULL))
);

-- 원장의 줄이 어느 홀드의 것인지 적는다
ALTER TABLE ledger_entries ADD COLUMN hold_id UUID REFERENCES holds (id);

-- 이유에 hold(홀드로 빠짐)와 release(홀드에서 돌아옴)를 더한다. 이유와 부호, 이유와 종류의 조건을 새로 건다
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold') AND amount < 0)
);

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);

-- 홀드는 홀드의 줄에만, 그리고 반드시 적힌다
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_hold_matches_reason
    CHECK ((reason IN ('hold', 'release')) = (hold_id IS NOT NULL));

-- 한 홀드가 같은 곳(산 크레딧, 또는 지급 묶음 하나)에서 두 번 빼거나 두 번 돌려줄 수 없다.
-- 코드가 같은 홀드를 두 번 돌려주려 해도 둘째는 DB 가 거절한다.
-- 산 크레딧의 줄은 지급 묶음이 NULL 이다. NULL 끼리는 서로 다르다고 보므로 0 으로 바꿔 견준다(지급 묶음의 번호는 1 부터다)
CREATE UNIQUE INDEX ledger_entries_hold_line_once
    ON ledger_entries (hold_id, reason, COALESCE(grant_id, 0))
    WHERE hold_id IS NOT NULL;

-- +goose Down
-- 홀드의 줄이 원장에 남아 있으면 되돌릴 수 없다. 옛 조건을 다시 걸 때 그 줄들이 걸려서 실패하고, 아무것도 바뀌지 않는다.
-- 원장의 줄은 지울 수 없으므로 일부러 그렇게 둔다. 줄을 지우고 되돌리면 잔액과 원장이 어긋난다
DROP INDEX ledger_entries_hold_line_once;
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_hold_matches_reason;

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire'))
);

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant') AND amount > 0)
    OR (reason IN ('spend', 'expire') AND amount < 0)
);

ALTER TABLE ledger_entries DROP COLUMN hold_id;
DROP TABLE holds;
