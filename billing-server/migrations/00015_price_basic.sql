-- billing-server/migrations/00015_price_basic.sql
-- 가격표의 등급에 basic 을 더한다. 가장 싼 모델(무료 API 나 그 유료판처럼 원가가 거의 없는 모델)을 판다.
--
--   basic     골드와 실버 모두로 낸다(standard 와 같다). 스탠다드보다 싼 값을 받는 묶음을 따로 보이려고 둔다
--   standard  골드와 실버 모두로 낸다
--   premium   골드로만 낸다
--
-- 실버를 쓸 수 있는지는 standard 와 같다. 등급이 다른 것은 화면에서 묶어 보이고, 이벤트로 그 묶음만 내리거나 무료로 열기 위해서다.
-- 이미 있는 줄은 바뀌지 않는다. CHECK 만 넓힌다.
--
-- 서버를 켠 채로 적용해도 된다. 서버는 가격표를 읽기만 한다.
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE price_versions DROP CONSTRAINT price_versions_tier_known;
ALTER TABLE price_versions ADD CONSTRAINT price_versions_tier_known CHECK (tier IN ('basic', 'standard', 'premium'));

-- +goose Down
-- basic 줄이 하나라도 있으면 실패한다(CHECK 를 다시 좁힐 수 없다). 가격표는 덧붙이기만 하므로 그 줄을 지울 수도 없다
ALTER TABLE price_versions DROP CONSTRAINT price_versions_tier_known;
ALTER TABLE price_versions ADD CONSTRAINT price_versions_tier_known CHECK (tier IN ('standard', 'premium'));
