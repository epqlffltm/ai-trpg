-- billing-server/migrations/00016_price_promo.sql
-- 가격표의 줄에 "행사가" 표시를 더한다.
--
-- 행사가는 끝나는 때가 정해진 값이다. 끝나는 때는 따로 적지 않고 그 이름의 다음 줄(예약)이 정한다.
-- 그래서 행사가 줄을 넣을 때는 그보다 늦은 줄이 먼저 있어야 한다(코드가 막는다. DB 는 줄 사이의 관계를 보지 않는다).
-- 가격 목록이 지금 값의 promo 와 다음 값을 함께 보이므로, 사용자는 처음부터 "언제까지의 값"인지 안다.
-- 행사가 끝나 정가로 오르는 것은 미리 알린 값이라 공급사 인상과 달리 따로 공지할 일이 아니다.
--
-- 판매를 멈추는 줄(amount 가 NULL)은 행사가일 수 없다.
-- 이미 있는 줄은 행사가가 아니다(false). 기본값은 남기지 않는다. 코드가 표시를 빠뜨리면 DB 가 막는다.
--
-- 서버를 켠 채로 적용해도 된다. 서버는 가격표를 읽기만 하고, 줄을 더하는 것은 명령(cmd/prices)뿐이다.
-- 옛 cmd/prices 는 promo 를 적지 않으므로 이것을 적용한 뒤에는 실패한다. 새 것으로 돌린다.
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE price_versions ADD COLUMN promo BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE price_versions ADD CONSTRAINT price_versions_promo_on_sale CHECK (amount IS NOT NULL OR NOT promo);
ALTER TABLE price_versions ALTER COLUMN promo DROP DEFAULT;

-- +goose Down
-- 행사가 표시를 지운다. 언제 행사가로 팔았는지의 기록도 사라진다. 개발용 DB 에서만 쓴다
ALTER TABLE price_versions DROP CONSTRAINT price_versions_promo_on_sale;
ALTER TABLE price_versions DROP COLUMN promo;
