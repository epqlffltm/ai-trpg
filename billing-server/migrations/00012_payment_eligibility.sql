-- billing-server/migrations/00012_payment_eligibility.sql
-- 사용자마다 결제할 수 있는지(결제 자격)를 적는다(#337). 인증 서버가 알려 준다(인증 서버의 payment_eligibility.py).
--
-- 결제는 성년(만 19세 생일부터)이거나, 미성년자면 보호자가 동의했을 때만 된다. 본인인증을 하지 않은 사용자는 결제하지 못한다.
-- 결제할 때 인증 서버를 부르지 않는다. 이 표만 본다. 인증 서버가 죽어 있어도 결제는 멈추지 않는다.
--
-- 인증 서버는 사건이 아니라 지금의 상태를 버전과 함께 보낸다. 가진 것보다 높은 버전만 받는다.
-- 늦게, 두 번, 건너뛰어 도착해도 마지막 상태로 맞는다. 그래서 고치는 문장(UPDATE)이 있다. 돈의 기록이 아니다.
-- 줄이 없는 사용자는 본인인증 전이다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE payment_eligibility (
    -- 인증 서버의 public_id
    user_id UUID PRIMARY KEY,
    -- 인증 서버가 붙인 버전. 상태가 바뀔 때마다 오른다
    version BIGINT NOT NULL,
    -- 성년이 되는 날(한국 날짜). 비어 있으면 이미 성년이다. 그날부터 결제할 수 있다
    legal_adult_from DATE,
    -- 보호자가 결제에 동의했다. 성년이면 보지 않는다
    guardian_consent BOOLEAN NOT NULL,
    -- 마지막으로 받아 적은 시각
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT payment_eligibility_version_positive CHECK (version > 0)
);

-- +goose Down
DROP TABLE payment_eligibility;
