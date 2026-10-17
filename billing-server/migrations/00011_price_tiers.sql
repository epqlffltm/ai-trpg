-- billing-server/migrations/00011_price_tiers.sql
-- 가격표 이름마다 등급(tier)을 적는다. 실버(무료 크레딧)를 쓸 수 있는지를 정한다(#338).
--
--   standard  골드(산 크레딧)와 실버(무료 크레딧) 모두로 낸다. 실버를 먼저 쓰는지는 SPEND_FREE_FIRST 가 정한다
--   premium   골드로만 낸다. 실버가 아무리 많아도 골드가 모자라면 홀드가 걸리지 않는다
--
-- 등급은 값과 같은 줄에 적는다. 등급을 바꾸는 것도 새 줄을 더하는 일이다. 가격표는 덧붙이기만 한다(00006).
-- 지금의 등급은 지금의 값이 적힌 줄의 등급이다. 판매를 멈추는 줄에도 그때의 등급을 그대로 적는다.
-- 결제에 쓰는 등급은 이 표가 기준이다. 게임 서버의 모델 목록에도 분류가 있지만 그것은 화면에 묶어 보여 주는 데 쓴다.
--
-- 이미 있는 줄은 standard 로 둔다. 다만 narration.premium 은 이름 그대로 premium 이다.
-- 이 칸이 생기기 전의 줄에 처음 값을 주는 것이라 옛 기록을 고치는 것이 아니다. 그래서 이때만 덧붙이기 막음을 잠깐 끈다.
-- 기본값은 남기지 않는다. 코드가 등급을 빠뜨리면 DB 가 막는다(값을 빠뜨린 프리미엄이 실버로 팔리는 일을 막는다).
--
-- 서버를 켠 채로 적용해도 된다. 서버는 가격표를 읽기만 하고, 줄을 더하는 것은 명령(cmd/prices)뿐이다.
-- 옛 cmd/prices 는 등급을 적지 않으므로 이것을 적용한 뒤에는 실패한다. 새 것으로 돌린다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE price_versions ADD COLUMN tier TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE price_versions ADD CONSTRAINT price_versions_tier_known CHECK (tier IN ('standard', 'premium'));

ALTER TABLE price_versions DISABLE TRIGGER price_versions_no_rewrite;
UPDATE price_versions SET tier = 'premium' WHERE code = 'narration.premium';
ALTER TABLE price_versions ENABLE TRIGGER price_versions_no_rewrite;

ALTER TABLE price_versions ALTER COLUMN tier DROP DEFAULT;

-- +goose Down
-- 등급을 지운다. 언제 어느 등급으로 팔았는지의 기록도 사라진다. 개발용 DB 에서만 쓴다
ALTER TABLE price_versions DROP CONSTRAINT price_versions_tier_known;
ALTER TABLE price_versions DROP COLUMN tier;
