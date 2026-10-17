-- billing-server/internal/pricereview/queries.sql
-- 공급사 가격 변경의 할 일을 적고 읽는 SQL. sqlc 가 이 파일을 읽어 Go 코드(pricereviewdb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.
--
-- 덧붙이기만 한다. 고치거나 지우는 문장이 없다.

-- name: InsertReview :one
INSERT INTO price_reviews (subject, changes_at, note, created_by, created_at)
VALUES (sqlc.arg(subject), sqlc.arg(changes_at), sqlc.arg(note), sqlc.arg(created_by), sqlc.arg(now))
RETURNING *;

-- name: LockReview :one
-- 할 일 하나를 잠그고 읽는다. 표시를 더하는 동안 다른 쪽이 같은 할 일을 닫지 못하게 한다.
SELECT * FROM price_reviews WHERE id = sqlc.arg(id) FOR UPDATE;

-- name: ListReviews :many
-- 모든 할 일을 공급사가 값을 바꾸는 시각 순서로 읽는다. 할 일은 한 해에 몇십 개뿐이라 다 읽는다.
SELECT * FROM price_reviews ORDER BY changes_at, id;

-- name: ListMarks :many
SELECT * FROM price_review_marks ORDER BY review_id, marked_at;

-- name: MarksOf :many
SELECT * FROM price_review_marks WHERE review_id = sqlc.arg(review_id) ORDER BY marked_at;

-- name: InsertMark :one
-- 표시를 하나 더한다. 같은 할 일에 같은 표시가 이미 있으면 아무것도 하지 않고 줄을 돌려주지 않는다.
INSERT INTO price_review_marks (review_id, mark, note, marked_by, marked_at)
VALUES (sqlc.arg(review_id), sqlc.arg(mark), sqlc.arg(note), sqlc.arg(marked_by), sqlc.arg(now))
ON CONFLICT (review_id, mark) DO NOTHING
RETURNING *;
