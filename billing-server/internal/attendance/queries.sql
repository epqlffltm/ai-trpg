-- billing-server/internal/attendance/queries.sql
-- 출석을 적고 읽는 SQL. sqlc 가 이 파일을 읽어 Go 코드(attendancedb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.

-- name: LockUserAttendance :exec
-- 한 사용자의 출석을 차례로 처리한다. 트랜잭션이 끝나면 풀린다.
-- 자정 무렵에 두 요청이 함께 와도 뒤의 것은 앞의 것이 적은 줄을 보고 며칠째인지 센다.
-- 다른 사용자와 열쇠가 겹치면 서로 기다릴 뿐이다. 틀린 값이 적히지는 않는다
SELECT pg_advisory_xact_lock(hashtextextended('attendance:' || (sqlc.arg(user_id)::uuid)::text, 0));

-- name: LastClaim :one
-- 그 사용자의 가장 최근 출석.
SELECT day, cycle_day
FROM attendance_claims
WHERE user_id = sqlc.arg(user_id)
ORDER BY day DESC
LIMIT 1;

-- name: GetClaim :one
-- 그 사용자가 그날 받은 출석.
SELECT * FROM attendance_claims WHERE user_id = sqlc.arg(user_id) AND day = sqlc.arg(day);

-- name: InsertClaim :execrows
-- 출석을 적는다. 그날 이미 받았으면 적지 않는다(바뀐 줄이 0 이다).
INSERT INTO attendance_claims (user_id, day, cycle_day, silver, chest_table, chest_outcome, chest_silver, claimed_at)
VALUES (
    sqlc.arg(user_id), sqlc.arg(day), sqlc.arg(cycle_day), sqlc.arg(silver),
    sqlc.narg(chest_table), sqlc.narg(chest_outcome), sqlc.narg(chest_silver), sqlc.arg(now)
)
ON CONFLICT (user_id, day) DO NOTHING;
