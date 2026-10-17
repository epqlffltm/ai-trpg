-- billing-server/migrations/00010_price_reviews.sql
-- 공급사 가격 변경의 할 일. 공급사(AI 모델 회사)가 값을 올리기 전에 우리 쪽에서 할 일을 날짜와 함께 적어 둔다.
--
-- 공급사가 값을 바꾸는 날(changes_at)을 기준으로 할 일이 셋이다.
--   announce  D-30  첫 공지(오를 수 있다는 것)
--   notice    D-14  자세한 공지와 함께 새 값을 가격표에 미래 시각으로 넣는다(cmd/prices set -at, import)
--   final     D-1   마지막 알림
-- 하루 한 번 도는 대사(cmd/reconcile)가 때가 된 할 일 가운데 끝내지 않은 것을 경고한다(pricing.review_due).
-- 이미 연 라운드는 건드리지 않는다. 홀드는 걸 때의 값을 적어 둔다(00004).
--
-- 할 일을 끝냈다는 표시는 고치지 않고 줄을 더한다(price_review_marks). 언제, 누가, 무엇을 했는지 남긴다.
-- 공급사가 인상을 거둬들였으면 cancel 줄을 더해 닫는다. 지우지 않는다.
-- 돈의 기록이 아니라 운영자의 할 일이라 price_versions 처럼 트리거로 막지는 않는다. 코드에 고치거나 지우는 문장이 없다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE price_reviews (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- 무엇의 값이 바뀌는지. "GPT-5.6 Sol 입력·출력 단가" 처럼 사람이 읽는 글이다
    subject TEXT NOT NULL,
    -- 공급사가 값을 바꾸는 시각. 할 일의 날짜는 모두 이 시각에서 거꾸로 센다
    changes_at TIMESTAMPTZ NOT NULL,
    -- 출처(공지 주소), 바뀌는 값 같은 것. 비워도 된다
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT price_reviews_subject_shape CHECK (subject <> '' AND char_length(subject) <= 200),
    CONSTRAINT price_reviews_note_length CHECK (char_length(note) <= 1000),
    CONSTRAINT price_reviews_created_by_not_empty CHECK (created_by <> '')
);

-- 할 일을 끝냈다는 표시, 또는 닫았다는 표시(cancel). 할 일 하나에 한 줄뿐이다
CREATE TABLE price_review_marks (
    review_id BIGINT NOT NULL REFERENCES price_reviews (id),
    mark TEXT NOT NULL,
    -- 공지의 주소, 넣은 값, 닫은 이유 같은 것. cancel 이면 비울 수 없다
    note TEXT NOT NULL DEFAULT '',
    marked_by TEXT NOT NULL,
    marked_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (review_id, mark),
    CONSTRAINT price_review_marks_known CHECK (mark IN ('announce', 'notice', 'final', 'cancel')),
    CONSTRAINT price_review_marks_note_length CHECK (char_length(note) <= 1000),
    CONSTRAINT price_review_marks_cancel_has_reason CHECK (mark <> 'cancel' OR note <> ''),
    CONSTRAINT price_review_marks_marked_by_not_empty CHECK (marked_by <> '')
);

-- +goose Down
DROP TABLE price_review_marks;
DROP TABLE price_reviews;
