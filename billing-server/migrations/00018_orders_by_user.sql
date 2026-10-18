-- billing-server/migrations/00018_orders_by_user.sql
-- 사용자가 자기 주문을 최근 것부터 읽는다(#430, GET /orders).
--
-- 지금까지는 주문 하나(GET /orders/{id})만 읽어서 사용자로 찾는 색인이 없었다. 있는 것은 (user_id, idempotency_key) 의 유일 색인뿐이다.
-- 목록은 만든 시각이 늦은 것부터고, 같은 시각이면 번호로 차례를 정한다. 다음 쪽은 앞 쪽의 마지막 주문보다 앞선 것이다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE INDEX orders_user_created_idx ON orders (user_id, created_at DESC, id DESC);

-- +goose Down
DROP INDEX orders_user_created_idx;
