-- billing-server/migrations/00025_auto_charge_notices.sql
-- 자동 충전(#980)이 되지 않은 것을 사용자의 알림함에 알린다(autocharge.failed).
-- 결제가 거절되었거나, 보내기 전에 그만뒀을 때다(한 달 상한, 결제 자격, 카드 없음). 사용자가 끈 것(disabled)과 탈퇴(withdrawn)는 알리지 않는다.
-- 다른 알림처럼 정리 작업이 충전할 일(auto_charge_requests)에서 찾아 적는다. 열쇠는 "autocharge.failed:<일의 번호>" 다.
-- 이어서 실패해 자동 충전을 끈 거절이면 그것도 함께 알린다(turned_off). 그 거절에 적어 둔다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE auto_charge_requests ADD COLUMN turned_off BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE user_notices DROP CONSTRAINT user_notices_kind_known;
ALTER TABLE user_notices ADD CONSTRAINT user_notices_kind_known
    CHECK (kind IN ('order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring', 'credit.short', 'autocharge.failed'));

-- 정리 작업이 최근에 끝난 일을 찾을 때 쓴다
CREATE INDEX auto_charge_requests_finished ON auto_charge_requests (finished_at) WHERE finished_at IS NOT NULL;

-- +goose Down
-- 되돌리면 아직 보내지 않은 것을 포함해 autocharge.failed 의 줄을 지운다. 남겨 두면 옛 조건을 다시 걸 수 없다
DELETE FROM user_notices WHERE kind = 'autocharge.failed';
ALTER TABLE user_notices DROP CONSTRAINT user_notices_kind_known;
ALTER TABLE user_notices ADD CONSTRAINT user_notices_kind_known
    CHECK (kind IN ('order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring', 'credit.short'));
DROP INDEX auto_charge_requests_finished;
ALTER TABLE auto_charge_requests DROP COLUMN turned_off;
