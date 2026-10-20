-- billing-server/migrations/00019_user_notices_credit_short.sql
-- 사용자의 알림함에 보낼 일에 "크레딧이 모자라 홀드를 걸지 못했다"(credit.short)를 더한다(#525).
--
-- 다른 종류와 달리 정리 작업이 찾아 적지 않는다. 홀드를 걸지 못한 그 자리에서 적는다(internal/hold/shortfall.go).
-- 걸지 못한 홀드는 트랜잭션이 되돌려져 줄이 남지 않으므로 나중에 찾을 곳이 없다.
-- 사람마다 하루(한국 날짜) 한 번이다. 열쇠가 "credit.short:<사람>:<한국 날짜>" 다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE user_notices DROP CONSTRAINT user_notices_kind_known;
ALTER TABLE user_notices ADD CONSTRAINT user_notices_kind_known
    CHECK (kind IN ('order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring', 'credit.short'));

-- +goose Down
-- 되돌리면 아직 보내지 않은 것을 포함해 credit.short 의 줄을 지운다. 남겨 두면 옛 조건을 다시 걸 수 없다
DELETE FROM user_notices WHERE kind = 'credit.short';
ALTER TABLE user_notices DROP CONSTRAINT user_notices_kind_known;
ALTER TABLE user_notices ADD CONSTRAINT user_notices_kind_known
    CHECK (kind IN ('order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring'));
