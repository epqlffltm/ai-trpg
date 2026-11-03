// billing-server/internal/coupon/store.go

package coupon

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon/coupondb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// uniqueViolation 은 유일 제약에 걸렸다는 PostgreSQL 의 SQLSTATE 다.
const uniqueViolation = "23505"

// Granter 는 한 번만 주는 실버를 부르는 쪽의 트랜잭션 안에서 주는 것의 모양이다. *wallet.Service 가 이 모양이다.
type Granter interface {
	GrantFreeOnceForInTx(
		ctx context.Context, tx pgx.Tx, userID uuid.UUID, amount credit.Amount, key string, ttl time.Duration,
	) (wallet.Grant, error)
}

// Verifier 는 사용자가 본인인증을 했는지 보는 것의 모양이다. *eligibility.Service 가 이 모양이다.
type Verifier interface {
	Verified(ctx context.Context, userID uuid.UUID) (bool, error)
}

// Service 는 쿠폰을 만들고, 멈추고, 받게 한다.
type Service struct {
	pool     *pgxpool.Pool
	clock    func() time.Time
	wallet   Granter
	verifier Verifier
}

// NewService 는 Service 를 만든다.
func NewService(pool *pgxpool.Pool, now func() time.Time, granter Granter, verifier Verifier) *Service {
	return &Service{pool: pool, clock: now, wallet: granter, verifier: verifier}
}

// --- 사용자 ---

// Redeem 은 사용자가 넣은 코드의 실버를 준다.
//   - 본인인증 전 -> ErrVerificationRequired
//   - 이 창에서 너무 많이 틀렸다 -> *TooManyAttemptsError
//   - 그런 코드가 없다(모양이 틀린 것도) -> ErrNotFound. 틀린 시도로 센다
//   - 멈춤, 아직, 지남, 다 참 -> ErrStopped, ErrNotStarted, ErrEnded, ErrExhausted. 세지 않는다(있는 코드다)
//   - 이미 받았다 -> ErrAlreadyRedeemed
//
// 받은 기록, 받은 사람의 수, 실버를 한 트랜잭션에서 적는다. 함께 되거나 함께 안 된다.
func (s *Service) Redeem(ctx context.Context, userID uuid.UUID, input string) (Redemption, error) {
	if err := s.requireVerified(ctx, userID); err != nil {
		return Redemption{}, err
	}
	now := s.clock()
	if err := s.requireNotBlocked(ctx, userID, now); err != nil {
		return Redemption{}, err
	}
	code, ok := NormalizeCode(input)
	if !ok {
		return Redemption{}, s.failed(ctx, userID, now)
	}
	var redemption Redemption
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		var err error
		redemption, err = s.redeemIn(ctx, tx, userID, code, now)
		return err
	})
	if errors.Is(err, ErrNotFound) {
		return Redemption{}, s.failed(ctx, userID, now)
	}
	if err != nil {
		return Redemption{}, err
	}
	return redemption, nil
}

// requireVerified 는 본인인증을 마친 사람인지 본다.
func (s *Service) requireVerified(ctx context.Context, userID uuid.UUID) error {
	verified, err := s.verifier.Verified(ctx, userID)
	if err != nil {
		return err
	}
	if !verified {
		return ErrVerificationRequired
	}
	return nil
}

// requireNotBlocked 는 이 창에서 너무 많이 틀리지 않았는지 본다.
func (s *Service) requireNotBlocked(ctx context.Context, userID uuid.UUID, now time.Time) error {
	row, err := coupondb.New(s.pool).GetAttempts(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return err
	}
	blocked, retryAfter := Blocked(&Attempts{WindowStartedAt: row.WindowStartedAt, Failures: int(row.Failures)}, now)
	if blocked {
		return &TooManyAttemptsError{RetryAfter: retryAfter}
	}
	return nil
}

// failed 는 틀린 시도를 하나 세고 ErrNotFound 를 돌려준다. 세지 못했으면 그 오류다.
// 받는 트랜잭션과 따로 적는다. 그 트랜잭션은 되돌려지므로 그 안에서 세면 남지 않는다.
func (s *Service) failed(ctx context.Context, userID uuid.UUID, now time.Time) error {
	err := coupondb.New(s.pool).RecordFailure(ctx, coupondb.RecordFailureParams{
		UserID: userID, Now: now, StaleBefore: now.Add(-FailureWindow),
	})
	if err != nil {
		return err
	}
	return ErrNotFound
}

// redeemIn 은 트랜잭션 안에서 쿠폰을 잠그고, 받을 수 있는지 보고, 실버를 주고, 받은 것을 적는다.
// 쿠폰의 줄을 잠그므로 같은 쿠폰의 요청은 차례로 지나간다. 뒤의 것은 앞의 것이 늘린 수와 적은 기록을 본다.
func (s *Service) redeemIn(ctx context.Context, tx pgx.Tx, userID uuid.UUID, code string, now time.Time) (Redemption, error) {
	queries := coupondb.New(tx)
	row, err := queries.LockCouponByCode(ctx, code)
	if errors.Is(err, pgx.ErrNoRows) {
		return Redemption{}, ErrNotFound
	}
	if err != nil {
		return Redemption{}, err
	}
	coupon := toCoupon(row)
	if err := Availability(coupon, now); err != nil {
		return Redemption{}, err
	}
	grant, err := s.wallet.GrantFreeOnceForInTx(ctx, tx, userID, coupon.Silver, GrantKey(coupon.ID), coupon.TTL())
	if errors.Is(err, wallet.ErrAlreadyGranted) {
		return Redemption{}, ErrAlreadyRedeemed
	}
	if err != nil {
		return Redemption{}, err
	}
	if err := record(ctx, queries, coupon, userID, grant, now); err != nil {
		return Redemption{}, err
	}
	return Redemption{Code: coupon.Code, Silver: grant.Amount, ExpiresAt: grant.ExpiresAt}, nil
}

// record 는 받은 것을 적고 받은 사람의 수를 늘린다. 이미 받은 사람이면 ErrAlreadyRedeemed 다.
func record(ctx context.Context, queries *coupondb.Queries, coupon Coupon, userID uuid.UUID, grant wallet.Grant, now time.Time) error {
	inserted, err := queries.InsertRedemption(ctx, coupondb.InsertRedemptionParams{
		CouponID: coupon.ID, UserID: userID, Silver: grant.Amount, ExpiresAt: grant.ExpiresAt, Now: now,
	})
	if err != nil {
		return err
	}
	if inserted == 0 {
		return ErrAlreadyRedeemed
	}
	return queries.CountRedemption(ctx, coupon.ID)
}

// --- 운영자(cmd/coupons) ---

// Create 는 쿠폰을 만든다. 값이 틀렸으면 ErrInvalidSpec, 같은 코드가 있으면 ErrCodeTaken 이다.
// 코드는 NormalizeCode 로 바꿔 적는다(사용자가 넣을 때와 같게).
func (s *Service) Create(ctx context.Context, spec Spec) (Coupon, error) {
	spec.Code, _ = NormalizeCode(spec.Code)
	if err := spec.Validate(); err != nil {
		return Coupon{}, err
	}
	row, err := coupondb.New(s.pool).CreateCoupon(ctx, coupondb.CreateCouponParams{
		Code: spec.Code, Silver: spec.Silver, SilverDays: optional(spec.SilverDays),
		StartsAt: spec.StartsAt, EndsAt: spec.EndsAt, MaxRedemptions: optional(spec.MaxRedemptions),
		CreatedBy: spec.CreatedBy, Reason: spec.Reason, Now: s.clock(),
	})
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation {
		return Coupon{}, ErrCodeTaken
	}
	if err != nil {
		return Coupon{}, err
	}
	return toCoupon(row), nil
}

// List 는 최근에 만든 쿠폰부터 limit 개다.
func (s *Service) List(ctx context.Context, limit int) ([]Coupon, error) {
	rows, err := coupondb.New(s.pool).ListCoupons(ctx, int32(limit))
	if err != nil {
		return nil, err
	}
	coupons := make([]Coupon, 0, len(rows))
	for _, row := range rows {
		coupons = append(coupons, toCoupon(row))
	}
	return coupons, nil
}

// Stop 은 쿠폰을 멈춘다. 그런 코드가 없으면 ErrNotFound 다. 이미 멈췄으면 그대로 둔다(오류가 아니다).
// 이미 받은 실버는 그대로다.
func (s *Service) Stop(ctx context.Context, input string) error {
	code, _ := NormalizeCode(input)
	queries := coupondb.New(s.pool)
	stopped, err := queries.StopCoupon(ctx, coupondb.StopCouponParams{Code: code, Now: s.clock()})
	if err != nil || stopped > 0 {
		return err
	}
	exists, err := queries.CouponExists(ctx, code)
	if err != nil {
		return err
	}
	if !exists {
		return ErrNotFound
	}
	return nil
}

// --- 모양 바꾸기 ---

// toCoupon 은 DB 의 줄을 이 패키지의 모양으로 바꾼다.
func toCoupon(row coupondb.Coupon) Coupon {
	return Coupon{
		ID: row.ID, Code: row.Code, Silver: row.Silver, SilverDays: fromOptional(row.SilverDays),
		StartsAt: row.StartsAt, EndsAt: row.EndsAt, MaxRedemptions: fromOptional(row.MaxRedemptions),
		Redemptions: int(row.Redemptions), StoppedAt: row.StoppedAt,
		CreatedBy: row.CreatedBy, Reason: row.Reason, CreatedAt: row.CreatedAt,
	}
}

// optional 은 0 을 "적지 않음"(NULL)으로 바꾼다.
func optional(value int) *int32 {
	if value == 0 {
		return nil
	}
	v := int32(value)
	return &v
}

// fromOptional 은 NULL 을 0 으로 바꾼다.
func fromOptional(value *int32) int {
	if value == nil {
		return 0
	}
	return int(*value)
}
