-- billing-server/migrations/00001_wallet_ledger.sql
-- 지갑, 무료 크레딧의 지급 묶음, 원장을 만든다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.
-- 어느 스키마에 놓일지는 연결의 search_path 가 정한다(internal/database).
--
-- 크레딧의 양은 모두 BIGINT 다. 가장 작은 단위의 개수를 적는다(internal/credit).
-- 시각은 DB 의 now() 를 쓰지 않고 서버가 넘긴다. 만료를 따지는 시계가 하나여야 한다.

-- +goose Up

-- 사용자마다 한 줄. 산 크레딧의 잔액을 들고 있고, 이 사용자의 크레딧을 바꾸는 모든 일이 이 줄을 잠근다.
-- 인증 서버의 사용자 테이블과 외래 키로 잇지 않는다. 다른 스키마이고, 결제 계정은 거기에 들어가지 못한다
CREATE TABLE wallets (
    user_id UUID PRIMARY KEY,
    paid_balance BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    -- 코드가 틀려도 잔액이 0 아래로 내려가지 않는다
    CONSTRAINT wallets_paid_balance_not_negative CHECK (paid_balance >= 0)
);

-- 무료 크레딧을 한 번 준 것이 한 줄이다. 줄마다 사라지는 시각이 따로 있어서 잔액 하나로 합치지 못한다.
-- 무료 크레딧의 잔액은 아직 사라지지 않은 줄의 remaining 을 더한 값이다
CREATE TABLE free_grants (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES wallets (user_id),
    amount BIGINT NOT NULL,
    remaining BIGINT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT free_grants_amount_positive CHECK (amount > 0),
    CONSTRAINT free_grants_remaining_in_range CHECK (remaining >= 0 AND remaining <= amount),
    CONSTRAINT free_grants_expires_after_created CHECK (expires_at > created_at)
);

-- 남은 것이 있는 줄만 찾는다. 다 쓴 줄과 사라진 줄은 색인에 넣지 않는다
CREATE INDEX free_grants_open_idx ON free_grants (user_id, expires_at) WHERE remaining > 0;

-- 크레딧이 늘거나 준 일을 한 줄씩 적는다. 덧붙이기만 한다.
-- 지갑과 지급 묶음은 "지금 얼마인가"이고, 원장은 "왜 그렇게 되었는가"다
CREATE TABLE ledger_entries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES wallets (user_id),
    -- 한 번의 변경이 여러 줄을 남길 때 그 줄들을 묶는다(무료 20 + 산 것 10 을 함께 쓴 경우)
    operation_id UUID NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT NOT NULL,
    -- 늘면 양수, 줄면 음수다
    amount BIGINT NOT NULL,
    -- 무료 크레딧의 줄은 어느 지급 묶음의 것인지 적는다
    grant_id BIGINT REFERENCES free_grants (id),
    created_at TIMESTAMPTZ NOT NULL,
    -- 이유와 부호가 맞아야 한다. 여기에 없는 이유와 양이 0 인 줄도 이 조건이 함께 막는다
    CONSTRAINT ledger_entries_sign_matches_reason CHECK (
        (reason IN ('deposit', 'grant') AND amount > 0)
        OR (reason IN ('spend', 'expire') AND amount < 0)
    ),
    -- 이유와 종류가 맞아야 한다. 산 크레딧은 지급되거나 사라지지 않고, 무료 크레딧은 충전되지 않는다.
    -- 여기에 없는 종류도 이 조건이 함께 막는다
    CONSTRAINT ledger_entries_reason_matches_kind CHECK (
        (kind = 'paid' AND reason IN ('deposit', 'spend'))
        OR (kind = 'free' AND reason IN ('grant', 'spend', 'expire'))
    ),
    -- 무료 크레딧의 줄에만, 그리고 반드시 지급 묶음이 적힌다
    CONSTRAINT ledger_entries_grant_matches_kind CHECK ((kind = 'free') = (grant_id IS NOT NULL))
);

-- 한 사용자의 원장을 최근 것부터 읽는다
CREATE INDEX ledger_entries_user_idx ON ledger_entries (user_id, id DESC);

-- 원장의 줄을 고치거나 지우지 못하게 한다. 틀린 줄은 지우지 않고 반대 줄을 덧붙여 바로잡는다.
-- 코드의 실수로 지난 기록이 바뀌는 일을 DB 가 막는다
-- +goose StatementBegin
CREATE FUNCTION forbid_ledger_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries 는 덧붙이기만 한다 (% 는 할 수 없다)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER ledger_entries_no_rewrite
    BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change();

CREATE TRIGGER ledger_entries_no_truncate
    BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_ledger_change();

-- +goose Down
DROP TABLE ledger_entries;
DROP FUNCTION forbid_ledger_change();
DROP TABLE free_grants;
DROP TABLE wallets;
