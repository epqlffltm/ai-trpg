-- billing-server/migrations/00028_auto_charge_dates.sql
-- 자동 충전의 날짜 기준(#1167). 매달 정한 날(한국 날짜, 1~28일)에 정한 상품을 산다.
-- 잔액 기준(#980)과 날짜 기준 중 하나를 고른다(mode). 상품, 한 달 상한, 동의, 카드는 둘이 함께 쓴다.
--
-- 같은 날에 두 번 사지 않는다. 날짜 기준의 일은 그날(charge_date)을 적고, 한 사람에게 한 날의 일은 하나다(색인).
-- 결제 작업이 그날 멈췄다 다시 떠도, 다시 켜도 그날은 다시 적지 않는다. 그날이 지나면 보내지 않는다(그 달은 건너뛴다).
-- 29~31일은 고르지 못한다. 모든 달에 그날이 있게 한다(2026-11-08 결정).
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
ALTER TABLE auto_charge_settings
    -- balance(골드가 기준 아래로 떨어지면), date(매달 charge_day 에)
    ADD COLUMN mode TEXT NOT NULL DEFAULT 'balance',
    -- 날짜 기준의 날. 잔액 기준으로 바꿔도 남긴다(다시 고를 때 보인다)
    ADD COLUMN charge_day SMALLINT,
    ADD CONSTRAINT auto_charge_mode_known CHECK (mode IN ('balance', 'date')),
    ADD CONSTRAINT auto_charge_day_in_month CHECK (charge_day BETWEEN 1 AND 28),
    ADD CONSTRAINT auto_charge_date_needs_day CHECK (mode <> 'date' OR charge_day IS NOT NULL);

-- 날짜 기준의 일이 산 날(한국 날짜). 잔액 기준의 일은 비어 있다
ALTER TABLE auto_charge_requests ADD COLUMN charge_date DATE;
-- 한 사람에게 한 날의 날짜 기준의 일은 하나다. 끝난 일(paid, declined, skipped)도 센다
CREATE UNIQUE INDEX auto_charge_requests_one_per_day ON auto_charge_requests (user_id, charge_date) WHERE charge_date IS NOT NULL;

-- 동의한 조건에 방식과 날을 더한다. 이 전의 동의는 모두 잔액 기준이다
ALTER TABLE auto_charge_consents
    ADD COLUMN mode TEXT NOT NULL DEFAULT 'balance',
    ADD COLUMN charge_day SMALLINT,
    ADD CONSTRAINT auto_charge_consents_mode_known CHECK (mode IN ('balance', 'date')),
    ADD CONSTRAINT auto_charge_consents_day_in_month CHECK (charge_day BETWEEN 1 AND 28),
    ADD CONSTRAINT auto_charge_consents_date_needs_day CHECK (mode <> 'date' OR charge_day IS NOT NULL);

-- +goose Down
-- 날짜 기준의 동의나 일이 하나라도 있으면 되돌리지 않는다. 지우면 그 결제의 근거와 "그날 한 번"의 기록이 사라진다
-- +goose StatementBegin
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM auto_charge_consents WHERE mode = 'date') OR EXISTS (SELECT 1 FROM auto_charge_requests WHERE charge_date IS NOT NULL) THEN
        RAISE EXCEPTION '날짜 기준의 자동 결제 동의나 충전할 일이 있어 되돌리지 않는다';
    END IF;
END $$;
-- +goose StatementEnd
-- 날짜 기준으로 켜 둔 사람은 끈다. 잔액 기준만 남은 표에서 그 설정은 뜻이 다르다
UPDATE auto_charge_settings SET enabled = false WHERE mode = 'date';
ALTER TABLE auto_charge_consents DROP COLUMN charge_day, DROP COLUMN mode;
DROP INDEX auto_charge_requests_one_per_day;
ALTER TABLE auto_charge_requests DROP COLUMN charge_date;
ALTER TABLE auto_charge_settings DROP COLUMN charge_day, DROP COLUMN mode;
