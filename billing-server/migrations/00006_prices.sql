-- billing-server/migrations/00006_prices.sql
-- 가격표를 코드에서 DB 로 옮긴다. 값을 바꾸려고 배포하지 않는다(#151).
--
-- 가격표는 덧붙이기만 한다. 값을 바꾸면 새 줄을 더하고, 옛 줄은 고치거나 지우지 않는다.
-- "그때 왜 그 값을 받았나"를 나중에도 답할 수 있게 한다. 원장과 같은 생각이다.
-- 지금의 값은 "적용 시각이 지금보다 앞선 줄 가운데 가장 늦은 줄"이다. 그 줄의 값이 없으면(NULL) 판매를 멈춘 것이다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE price_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- 무엇의 값인지. "narration.standard", "narration.gemma4-26b" 처럼 점으로 나눈 소문자 이름이다
    code TEXT NOT NULL,
    -- 한 번에 받는 크레딧. NULL 이면 이 시각부터 판매를 멈춘다
    amount BIGINT,
    -- 이 값이 적용되기 시작하는 시각
    effective_at TIMESTAMPTZ NOT NULL,
    -- 왜 바꿨는지와 누가 바꿨는지. 비우지 못한다
    reason TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT price_versions_code_shape CHECK (
        code ~ '^[a-z][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$' AND char_length(code) <= 64
    ),
    -- 값은 1 부터 100만까지. 0 으로는 홀드를 걸 수 없고, 0 을 몇 개 더 붙인 실수를 막는다
    CONSTRAINT price_versions_amount_in_range CHECK (amount IS NULL OR (amount > 0 AND amount <= 1000000)),
    CONSTRAINT price_versions_reason_not_empty CHECK (reason <> ''),
    CONSTRAINT price_versions_changed_by_not_empty CHECK (changed_by <> ''),
    -- 같은 이름에 같은 적용 시각이 둘이면 어느 쪽이 지금의 값인지 정할 수 없다
    CONSTRAINT price_versions_one_per_moment UNIQUE (code, effective_at)
);

-- 이름마다 가장 늦은 줄을 찾는다
CREATE INDEX price_versions_lookup_idx ON price_versions (code, effective_at DESC);

-- +goose StatementBegin
CREATE FUNCTION forbid_price_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'price_versions 는 덧붙이기만 한다 (% 는 할 수 없다)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER price_versions_no_rewrite
    BEFORE UPDATE OR DELETE ON price_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_price_change();

CREATE TRIGGER price_versions_no_truncate
    BEFORE TRUNCATE ON price_versions
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_price_change();

-- 코드에 있던 값을 첫 줄로 옮긴다. 적용 시각은 이 서버가 생기기 전으로 둔다. 이미 건 홀드와 테스트의 옛 시각에도 값이 있게 한다
INSERT INTO price_versions (code, amount, effective_at, reason, changed_by, created_at)
VALUES ('narration.standard', 50, TIMESTAMPTZ '2000-01-01 00:00:00+00', '코드의 가격표에서 옮김', 'migration', now());

-- +goose Down
-- 마이그레이션이 넣은 첫 줄 말고 다른 줄이 있으면 멈추고 아무것도 바꾸지 않는다.
-- 지우고 되돌리면 언제 무엇을 얼마에 받았는지의 기록이 사라진다. 처음부터 다시 하려면 스키마를 지우고 다시 만든다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM price_versions WHERE changed_by <> 'migration') THEN
        RAISE EXCEPTION '가격표에 바꾼 기록이 있어 되돌리지 않는다';
    END IF;
END;
$$;
-- +goose StatementEnd
DROP TABLE price_versions;
DROP FUNCTION forbid_price_change();
