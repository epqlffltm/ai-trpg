-- billing-server/migrations/00027_auto_charge_history.sql
-- 자동 충전(#980)의 최근 내역(GET /auto-charge/history). 한 사람의 충전할 일을 늦게 적힌 것부터 읽는다.
-- 지금 있는 색인은 끝나지 않은 일(pending, charging)뿐이라, 끝난 일까지 사람마다 읽으려면 표를 다 본다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE INDEX auto_charge_requests_user_recent ON auto_charge_requests (user_id, created_at DESC, id DESC);

-- +goose Down
DROP INDEX auto_charge_requests_user_recent;
