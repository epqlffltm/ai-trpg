-- billing-server/migrations/00020_withdrawal.sql
-- 탈퇴(#603, docs/architecture/withdrawal.md). 인증 서버가 탈퇴를 알리면 이 서버가 그 사람의 크레딧을 정리한다.
--
--   1. 걸린 홀드(held)를 돌려준다. 돌려준 이유는 withdrawn 이다. 홀드를 건 서버가 나중에 확정하려 해도 이미 돌려준 홀드다
--   2. 남은 크레딧(골드와 실버)을 원장에 소멸(forfeit)로 적는다. 묶음마다 남은 만큼이다. 원장은 지우지 않는다(법정 보존)
--
-- 원장의 이유가 하나 는다. forfeit 은 산 크레딧과 무료 크레딧 모두의 줄이고 늘 빠지는 줄(-)이다.
-- 기한이 지나 사라지는 expire 와 나눈다. 둘을 섞으면 "기한이 지나 사라진 실버"를 세는 일에 탈퇴가 섞인다.
--
-- 탈퇴한 사람의 걸린 홀드를 찾는 색인을 둔다. 지금까지 사람마다 홀드를 찾는 일이 없었다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release', 'unrefund') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold', 'refund', 'forfeit') AND amount < 0)
    OR (reason = 'regroup' AND amount <> 0)
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release', 'regroup', 'refund', 'unrefund', 'forfeit'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release', 'forfeit'))
);

ALTER TABLE holds DROP CONSTRAINT holds_release_reason_matches_status;
ALTER TABLE holds ADD CONSTRAINT holds_release_reason_matches_status CHECK (
    (status = 'released') = (release_reason IS NOT NULL)
    AND (release_reason IS NULL OR release_reason IN ('requested', 'expired', 'withdrawn'))
);

CREATE INDEX holds_held_user_idx ON holds (user_id) WHERE status = 'held';

-- +goose Down
-- 소멸의 줄이나 탈퇴로 돌려준 홀드가 하나라도 있으면 멈추고 아무것도 바꾸지 않는다.
-- 원장의 줄은 지울 수 없고, 남겨 두면 옛 조건을 다시 걸 수 없다. 처음부터 다시 하려면 스키마를 지우고 다시 만든다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ledger_entries WHERE reason = 'forfeit')
        OR EXISTS (SELECT 1 FROM holds WHERE release_reason = 'withdrawn') THEN
        RAISE EXCEPTION '탈퇴로 정리한 기록이 있어 되돌리지 않는다';
    END IF;
END;
$$;
-- +goose StatementEnd
DROP INDEX holds_held_user_idx;

ALTER TABLE holds DROP CONSTRAINT holds_release_reason_matches_status;
ALTER TABLE holds ADD CONSTRAINT holds_release_reason_matches_status CHECK (
    (status = 'released') = (release_reason IS NOT NULL)
    AND (release_reason IS NULL OR release_reason IN ('requested', 'expired'))
);

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_reason_matches_kind;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_reason_matches_kind CHECK (
    (kind = 'paid' AND reason IN ('deposit', 'spend', 'hold', 'release', 'regroup', 'refund', 'unrefund'))
    OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire', 'hold', 'release'))
);
ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_sign_matches_reason;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_sign_matches_reason CHECK (
    (reason IN ('deposit', 'grant', 'release', 'unrefund') AND amount > 0)
    OR (reason IN ('spend', 'expire', 'hold', 'refund') AND amount < 0)
    OR (reason = 'regroup' AND amount <> 0)
);
