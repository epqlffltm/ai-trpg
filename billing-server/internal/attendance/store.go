// billing-server/internal/attendance/store.go

package attendance

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/attendance/attendancedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// Granter 는 한 번만 주는 실버를 부르는 쪽의 트랜잭션 안에서 주는 것의 모양이다. *wallet.Service 가 이 모양이다.
type Granter interface {
	GrantFreeOnceInTx(ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error)
}

// Verifier 는 사용자가 본인인증을 했는지 보는 것의 모양이다. *eligibility.Service 가 이 모양이다.
type Verifier interface {
	Verified(ctx context.Context, userID uuid.UUID) (bool, error)
}

// Options 는 바꿀 수 있는 규칙이다. 비운 것은 기본값이다.
type Options struct {
	// Schedule 은 하루 양의 목록이다. 비우면 DefaultSchedule 이다.
	Schedule Schedule
	// Chest 는 보물 상자의 확률표다. 비우면 CurrentChest 다.
	Chest *ChestTable
	// Roll 은 상자의 수를 고른다. 비우면 CryptoRoll 이다. 테스트가 정해진 수를 넣는다.
	Roll Roll
}

// Service 는 출석을 받고 읽는다.
type Service struct {
	pool     *pgxpool.Pool
	clock    func() time.Time
	wallet   Granter
	verifier Verifier
	schedule Schedule
	chest    ChestTable
	roll     Roll
}

// NewService 는 Service 를 만든다. 하루 양이나 확률표가 틀렸으면 오류다. 서버가 뜨지 않는다.
func NewService(pool *pgxpool.Pool, now func() time.Time, granter Granter, verifier Verifier, options Options) (*Service, error) {
	schedule, chest, roll := withDefaults(options)
	if err := errors.Join(schedule.Validate(), chest.Validate()); err != nil {
		return nil, err
	}
	return &Service{
		pool: pool, clock: now, wallet: granter, verifier: verifier,
		schedule: schedule, chest: chest, roll: roll,
	}, nil
}

// withDefaults 는 비운 규칙을 기본값으로 채운다.
func withDefaults(options Options) (Schedule, ChestTable, Roll) {
	schedule := options.Schedule
	if len(schedule) == 0 {
		schedule = DefaultSchedule()
	}
	chest := CurrentChest
	if options.Chest != nil {
		chest = *options.Chest
	}
	roll := options.Roll
	if roll == nil {
		roll = CryptoRoll
	}
	return schedule, chest, roll
}

// Rewards 는 하루 양의 목록과 보물 상자의 확률표다. 공개하는 주소가 그대로 보여 준다.
func (s *Service) Rewards() (Schedule, ChestTable) {
	return s.schedule, s.chest
}

// Status 는 그 사용자의 오늘 출석이다. 본인인증을 하지 않았어도 오류가 아니다(Verified 가 false 다).
func (s *Service) Status(ctx context.Context, userID uuid.UUID) (Status, error) {
	today := eligibility.KoreanDate(s.clock())
	verified, err := s.verifier.Verified(ctx, userID)
	if err != nil {
		return Status{}, err
	}
	queries := attendancedb.New(s.pool)
	claimed, err := findClaim(ctx, queries, userID, today)
	if err != nil {
		return Status{}, err
	}
	if claimed != nil {
		return claimedStatus(today, verified, *claimed), nil
	}
	last, err := lastClaim(ctx, queries, userID)
	if err != nil {
		return Status{}, err
	}
	day := CycleDayOn(last, today, s.schedule.Length())
	return Status{
		Today: today, Verified: verified, CycleDay: day,
		Silver: s.schedule.SilverOn(day), Chest: s.schedule.OpensChest(day),
	}, nil
}

// claimedStatus 는 오늘 이미 받은 사용자의 상태다. 적어 둔 줄의 값을 그대로 보인다(그 사이 설정이 바뀌었어도).
func claimedStatus(today time.Time, verified bool, row attendancedb.AttendanceClaim) Status {
	return Status{
		Today: today, Verified: verified, Claimed: true, CycleDay: int(row.CycleDay),
		Silver: row.Silver, Chest: row.ChestTable != nil,
	}
}

// Claim 은 오늘의 출석 보상을 준다. 본인인증 전이면 ErrVerificationRequired, 오늘 이미 받았으면 ErrAlreadyClaimed 다.
// 출석의 줄과 실버(하루 양, 상자)를 한 트랜잭션에서 적는다. 함께 되거나 함께 안 된다.
func (s *Service) Claim(ctx context.Context, userID uuid.UUID) (Claim, error) {
	verified, err := s.verifier.Verified(ctx, userID)
	if err != nil {
		return Claim{}, err
	}
	if !verified {
		return Claim{}, ErrVerificationRequired
	}
	now := s.clock()
	var claim Claim
	// 지갑이 원장에 적은 일은 커밋한 뒤에 세어진다(txn.Run)
	err = txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		var err error
		claim, err = s.claimIn(ctx, tx, userID, now)
		return err
	})
	if err != nil {
		return Claim{}, err
	}
	return claim, nil
}

// claimIn 은 트랜잭션 안에서 출석을 적고 실버를 준다.
// 그 사용자의 출석을 먼저 잠근다. 자정 무렵에 두 요청이 함께 와도 차례로 지나가며, 뒤의 것은 앞의 것이 적은 줄을 본다.
func (s *Service) claimIn(ctx context.Context, tx pgx.Tx, userID uuid.UUID, now time.Time) (Claim, error) {
	queries := attendancedb.New(tx)
	if err := queries.LockUserAttendance(ctx, userID); err != nil {
		return Claim{}, err
	}
	today := eligibility.KoreanDate(now)
	last, err := lastClaim(ctx, queries, userID)
	if err != nil {
		return Claim{}, err
	}
	if last != nil && !last.Day.Before(today) {
		return Claim{}, ErrAlreadyClaimed
	}
	claim := Claim{Day: today, CycleDay: CycleDayOn(last, today, s.schedule.Length())}
	claim.Silver = s.schedule.SilverOn(claim.CycleDay)
	if claim.Chest, err = s.openChest(claim.CycleDay); err != nil {
		return Claim{}, err
	}
	if err := insertClaim(ctx, queries, userID, claim, now); err != nil {
		return Claim{}, err
	}
	if claim.ExpiresAt, err = s.grant(ctx, tx, userID, claim); err != nil {
		return Claim{}, err
	}
	return claim, nil
}

// openChest 는 상자를 여는 날이면 연다. 아니면 nil 이다.
func (s *Service) openChest(cycleDay int) (*ChestResult, error) {
	if !s.schedule.OpensChest(cycleDay) {
		return nil, nil
	}
	n, err := s.roll()
	if err != nil {
		return nil, err
	}
	return &ChestResult{Table: s.chest.Version, Outcome: s.chest.Pick(n)}, nil
}

// grant 는 하루 양과 상자의 실버를 준다. 하루 양이 사라지는 시각을 돌려준다(상자의 것도 같다).
// 꽝(0 실버)은 주지 않는다. 그 이름의 지급이 이미 있으면 오늘 받은 것이다(ErrAlreadyClaimed).
func (s *Service) grant(ctx context.Context, tx pgx.Tx, userID uuid.UUID, claim Claim) (time.Time, error) {
	daily, err := s.wallet.GrantFreeOnceInTx(ctx, tx, userID, claim.Silver, GrantKey(claim.Day))
	if err != nil {
		return time.Time{}, alreadyClaimedIfGranted(err)
	}
	if claim.Chest == nil || claim.Chest.Outcome.Silver == 0 {
		return daily.ExpiresAt, nil
	}
	_, err = s.wallet.GrantFreeOnceInTx(ctx, tx, userID, claim.Chest.Outcome.Silver, ChestGrantKey(claim.Day))
	if err != nil {
		return time.Time{}, alreadyClaimedIfGranted(err)
	}
	return daily.ExpiresAt, nil
}

// alreadyClaimedIfGranted 는 지갑이 "이미 준 이름"이라고 하면 ErrAlreadyClaimed 로 바꾼다.
func alreadyClaimedIfGranted(err error) error {
	if errors.Is(err, wallet.ErrAlreadyGranted) {
		return ErrAlreadyClaimed
	}
	return err
}

// insertClaim 은 출석의 줄을 적는다. 그날의 줄이 이미 있으면 ErrAlreadyClaimed 다.
func insertClaim(ctx context.Context, queries *attendancedb.Queries, userID uuid.UUID, claim Claim, now time.Time) error {
	params := attendancedb.InsertClaimParams{
		UserID: userID, Day: claim.Day, CycleDay: int16(claim.CycleDay), Silver: claim.Silver, Now: now,
	}
	if claim.Chest != nil {
		params.ChestTable = &claim.Chest.Table
		params.ChestOutcome = &claim.Chest.Outcome.ID
		params.ChestSilver = &claim.Chest.Outcome.Silver
	}
	inserted, err := queries.InsertClaim(ctx, params)
	if err != nil {
		return err
	}
	if inserted == 0 {
		return ErrAlreadyClaimed
	}
	return nil
}

// findClaim 은 그날의 출석을 읽는다. 없으면 nil 이다.
func findClaim(ctx context.Context, queries *attendancedb.Queries, userID uuid.UUID, day time.Time) (*attendancedb.AttendanceClaim, error) {
	row, err := queries.GetClaim(ctx, attendancedb.GetClaimParams{UserID: userID, Day: day})
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &row, nil
}

// lastClaim 은 가장 최근의 출석을 읽는다. 없으면 nil 이다.
func lastClaim(ctx context.Context, queries *attendancedb.Queries, userID uuid.UUID) (*Last, error) {
	row, err := queries.LastClaim(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &Last{Day: row.Day, CycleDay: int(row.CycleDay)}, nil
}
