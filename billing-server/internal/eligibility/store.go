// billing-server/internal/eligibility/store.go

package eligibility

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility/eligibilitydb"
)

// Service 는 결제 자격을 적고 읽는다.
type Service struct {
	pool  *pgxpool.Pool
	clock func() time.Time
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려준다(테스트가 바꿔 넣는다).
func NewService(pool *pgxpool.Pool, now func() time.Time) *Service {
	return &Service{pool: pool, clock: now}
}

// Apply 는 인증 서버가 알려 준 상태를 적는다. 가진 것보다 높은 버전이면 Applied, 아니면 Stale 이다.
// 같은 요청을 다시 받아도(인증 서버가 답을 못 받고 다시 보냈다) Stale 로 끝난다.
func (s *Service) Apply(ctx context.Context, update Update) (Outcome, error) {
	if err := checkUpdate(update); err != nil {
		return "", err
	}
	changed, err := eligibilitydb.New(s.pool).ApplyEligibility(ctx, eligibilitydb.ApplyEligibilityParams{
		UserID:          update.UserID,
		Version:         update.Version,
		LegalAdultFrom:  update.LegalAdultFrom,
		GuardianConsent: update.GuardianConsent,
		Now:             s.clock(),
	})
	if err != nil {
		return "", err
	}
	if changed == 0 {
		return Stale, nil
	}
	return Applied, nil
}

// Check 는 그 사용자가 지금 결제할 수 있는지 본다. 된다면 nil 이다.
// 본인인증 전이면 ErrVerificationRequired, 보호자의 동의가 없는 미성년자면 ErrGuardianConsentRequired 다.
func (s *Service) Check(ctx context.Context, userID uuid.UUID) error {
	record, err := s.find(ctx, userID)
	if err != nil {
		return err
	}
	return Decide(record, KoreanDate(s.clock()))
}

// Verified 는 그 사용자가 본인인증을 했는지 본다. 인증 서버는 본인인증을 한 사용자만 알려 준다.
// 나이와 보호자 동의는 보지 않는다. 출석(#339)처럼 결제가 아닌 일이 쓴다.
func (s *Service) Verified(ctx context.Context, userID uuid.UUID) (bool, error) {
	record, err := s.find(ctx, userID)
	if err != nil {
		return false, err
	}
	return record != nil, nil
}

// find 는 적어 둔 것을 읽는다. 없으면 nil 이다.
func (s *Service) find(ctx context.Context, userID uuid.UUID) (*Record, error) {
	row, err := eligibilitydb.New(s.pool).GetEligibility(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &Record{LegalAdultFrom: row.LegalAdultFrom, GuardianConsent: row.GuardianConsent}, nil
}

// Erase 는 그 사용자의 결제 자격을 지운다(탈퇴, #603). 지웠으면 true, 없었으면 false 다. 몇 번을 불러도 같다.
// 인증 서버도 탈퇴를 마칠 때 보낼 결제 자격을 함께 지운다. 그래서 지운 뒤에 다시 적히지 않는다.
func (s *Service) Erase(ctx context.Context, userID uuid.UUID) (bool, error) {
	deleted, err := eligibilitydb.New(s.pool).DeleteEligibility(ctx, userID)
	if err != nil {
		return false, err
	}
	return deleted > 0, nil
}
