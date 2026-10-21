-- billing-server/internal/eligibility/queries.sql
-- 결제 자격을 적고 읽는 SQL. sqlc 가 이 파일을 읽어 Go 코드(eligibilitydb)를 만든다.
-- 이 파일을 고치면 billing-server 폴더에서 sqlc generate 를 다시 돌린다.

-- name: ApplyEligibility :execrows
-- 받은 상태를 적는다. 가진 것보다 높은 버전일 때만 덮는다. 바뀐 줄이 없으면 이미 같거나 높은 버전이 있다.
INSERT INTO payment_eligibility (user_id, version, legal_adult_from, guardian_consent, updated_at)
VALUES (sqlc.arg(user_id), sqlc.arg(version), sqlc.narg(legal_adult_from), sqlc.arg(guardian_consent), sqlc.arg(now))
ON CONFLICT (user_id) DO UPDATE
SET version = EXCLUDED.version,
    legal_adult_from = EXCLUDED.legal_adult_from,
    guardian_consent = EXCLUDED.guardian_consent,
    updated_at = EXCLUDED.updated_at
WHERE payment_eligibility.version < EXCLUDED.version;

-- name: GetEligibility :one
SELECT * FROM payment_eligibility WHERE user_id = sqlc.arg(user_id);

-- name: DeleteEligibility :execrows
-- 그 사람의 결제 자격을 지운다(탈퇴). 없으면 지운 줄이 0 이다.
DELETE FROM payment_eligibility WHERE user_id = sqlc.arg(user_id);
