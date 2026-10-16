-- billing-server/migrations/00009_order_channel.sql
-- 주문을 치른 길(channel). 결제 경로를 나누는 첫 단계다. 동작은 바뀌지 않는다.
--
-- 지금은 web 하나뿐이다. 웹에서 결제창을 열어 결제 대행사(토스페이먼츠, 가짜)가 승인하는 길이다.
-- 앱 안의 스토어 결제(구글 플레이)를 붙일 때 그 마이그레이션이 이 CHECK 에 값을 더한다.
-- 결제 대행사를 부르는 곳(승인, 조회, 취소)은 주문의 길을 보고 그 길의 결제 대행사를 고른다.
--
-- 기본값을 둔다. 00005 와 달리 이 칸은 지금 값이 하나뿐이라 빠뜨려도 틀린 값이 들어가지 않고,
-- 기본값이 있으면 옛 서버가 떠 있는 채로 적용해도 주문을 만들 수 있다. 코드는 그래도 값을 늘 적는다.
-- 다른 길을 더할 때 그 길의 주문은 다른 INSERT 로 만든다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE orders ADD COLUMN channel TEXT NOT NULL DEFAULT 'web';
ALTER TABLE orders ADD CONSTRAINT orders_channel_known CHECK (channel IN ('web'));

-- +goose Down
ALTER TABLE orders DROP CONSTRAINT orders_channel_known;
ALTER TABLE orders DROP COLUMN channel;
