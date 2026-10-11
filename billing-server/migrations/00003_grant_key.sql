-- billing-server/migrations/00003_grant_key.sql
-- 무료 크레딧의 지급 묶음에 "무엇으로 준 것인가"를 적는 칸을 더한다. 같은 것을 한 사용자에게 두 번 주지 않게 한다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up

-- 한 번만 주는 지급에 붙이는 이름이다(환영 크레딧은 'welcome'). 몇 번이고 줄 수 있는 지급은 비워 둔다
ALTER TABLE free_grants ADD COLUMN grant_key TEXT;

-- 비어 있는 것과 이름이 없는 것(NULL)을 섞어 쓰지 않는다
ALTER TABLE free_grants ADD CONSTRAINT free_grants_grant_key_not_empty CHECK (grant_key <> '');

-- 한 사용자는 같은 이름의 지급을 한 번만 받는다. 다 쓰거나 사라진 뒤에도 다시 받지 못한다.
-- 이름이 없는 지급(NULL)은 이 색인에 들어가지 않아서 몇 번이고 줄 수 있다
CREATE UNIQUE INDEX free_grants_key_once ON free_grants (user_id, grant_key) WHERE grant_key IS NOT NULL;

-- +goose Down
DROP INDEX free_grants_key_once;
ALTER TABLE free_grants DROP CONSTRAINT free_grants_grant_key_not_empty;
ALTER TABLE free_grants DROP COLUMN grant_key;
