-- billing-server/migrations/00014_attendance.sql
-- 출석과 보물 상자(#339). 사용자가 하루에 한 번 "출석"을 누르면 실버(무료 크레딧)를 받는다.
-- 주기의 마지막 날(7일째)에는 보물 상자를 함께 연다.
--
-- 출석한 날마다 한 줄이다. "며칠째 연속"을 따로 적지 않는다. 오늘이 며칠째인지는 어제의 줄로 센다.
-- 숫자를 따로 두면 기록과 어긋날 수 있다. 줄이 곧 기록이고, 다툼이 생기면 이 줄들을 보여 준다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up

CREATE TABLE attendance_claims (
    user_id UUID NOT NULL,
    -- 출석한 날. 한국 날짜다(Asia/Seoul 의 자정에 바뀐다)
    day DATE NOT NULL,
    -- 주기의 며칠째인가. 1 부터다
    cycle_day SMALLINT NOT NULL,
    -- 그날 받은 실버
    silver BIGINT NOT NULL,
    -- 보물 상자. 연 날에만 셋이 함께 있다. table 은 확률표의 버전(v1), outcome 은 나온 결과의 이름이다.
    -- 확률표를 바꾸면 버전을 올린다. 이 줄은 연 때의 표를 가리킨다
    chest_table TEXT,
    chest_outcome TEXT,
    chest_silver BIGINT,
    claimed_at TIMESTAMPTZ NOT NULL,
    -- 한 사용자는 하루에 한 번만 받는다. 같은 날의 두 요청이 함께 와도 하나만 적힌다
    PRIMARY KEY (user_id, day),
    CONSTRAINT attendance_claims_cycle_day_positive CHECK (cycle_day >= 1),
    CONSTRAINT attendance_claims_silver_positive CHECK (silver > 0),
    CONSTRAINT attendance_claims_chest_together CHECK (
        (chest_table IS NULL) = (chest_outcome IS NULL)
        AND (chest_outcome IS NULL) = (chest_silver IS NULL)
    ),
    -- 꽝(미믹에게 물렸다)은 0 이다
    CONSTRAINT attendance_claims_chest_silver_not_negative CHECK (chest_silver >= 0)
);

-- +goose Down
-- 기록을 지운다. 받은 실버는 지갑에 남는다(원장과 지급 묶음은 그대로다)
DROP TABLE attendance_claims;
