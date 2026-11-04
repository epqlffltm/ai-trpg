// billing-server/internal/autocharge/store.go

package autocharge

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// IssueTimeout 은 카드 등록에서 결제 대행사의 답을 기다리는 가장 긴 시간이다.
const IssueTimeout = 10 * time.Second

// Eligibility 는 그 사람이 지금 결제할 수 있는지 보는 것의 모양이다. *eligibility.Service 가 이 모양이다.
type Eligibility interface {
	Check(ctx context.Context, userID uuid.UUID) error
}

// Service 는 카드를 등록하고 지우며, 자동 충전의 설정을 적고 읽는다.
type Service struct {
	pool        *pgxpool.Pool
	clock       func() time.Time
	issuer      payment.CardIssuer
	eligibility Eligibility
	// charger 와 orders 는 결제하는 작업만 붙인다(WithCharging, charge.go). 처음에는 없다
	charger payment.CardCharger
	orders  Orders
}

// NewService 는 Service 를 만든다.
func NewService(pool *pgxpool.Pool, now func() time.Time, issuer payment.CardIssuer, eligibility Eligibility) *Service {
	return &Service{pool: pool, clock: now, issuer: issuer, eligibility: eligibility}
}

// --- 카드 ---

// CustomerKey 는 그 사람의 고객 키다. 없으면 무작위로 만든다. 카드 등록 창을 열 때 쓴다.
func (s *Service) CustomerKey(ctx context.Context, userID uuid.UUID) (uuid.UUID, error) {
	queries := autochargedb.New(s.pool)
	if err := queries.InsertCustomer(ctx, autochargedb.InsertCustomerParams{
		UserID: userID, CustomerKey: uuid.New(), Now: s.clock(),
	}); err != nil {
		return uuid.Nil, err
	}
	return queries.GetCustomerKey(ctx, userID)
}

// RegisterCard 는 결제 대행사가 준 인증 키로 빌링키를 받아 카드를 적는다. 이미 있으면 바꾼다.
//   - 인증 키의 모양이 틀렸다 -> ErrInvalidAuthKey
//   - 고객 키가 이 사람의 것이 아니다 -> ErrCustomerKeyMismatch
//   - 결제 대행사가 거절했다 -> *payment.RefusedError
//   - 결제 대행사의 답을 받지 못했다 -> ErrIssuerUnavailable
func (s *Service) RegisterCard(ctx context.Context, userID uuid.UUID, authKey string, customerKey uuid.UUID) (Card, error) {
	if err := CheckAuthKey(authKey); err != nil {
		return Card{}, err
	}
	if err := s.requireCustomerKey(ctx, userID, customerKey); err != nil {
		return Card{}, err
	}
	issued, err := s.issue(ctx, authKey, customerKey)
	if err != nil {
		return Card{}, err
	}
	now := s.clock()
	if err := autochargedb.New(s.pool).UpsertCard(ctx, autochargedb.UpsertCardParams{
		UserID: userID, BillingKey: issued.BillingKey, IssuerCode: issued.IssuerCode, CardNumber: issued.Number, Now: now,
	}); err != nil {
		return Card{}, err
	}
	return Card{IssuerCode: issued.IssuerCode, Number: issued.Number, RegisteredAt: now}, nil
}

// requireCustomerKey 는 고객 키가 이 사람의 것인지 본다. 고객 키를 만든 적이 없어도 틀린 것이다.
func (s *Service) requireCustomerKey(ctx context.Context, userID uuid.UUID, customerKey uuid.UUID) error {
	stored, err := autochargedb.New(s.pool).GetCustomerKey(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrCustomerKeyMismatch
	}
	if err != nil {
		return err
	}
	if stored != customerKey {
		return ErrCustomerKeyMismatch
	}
	return nil
}

// issue 는 결제 대행사에 빌링키를 받되 IssueTimeout 까지만 기다린다. 답을 받지 못했으면 ErrIssuerUnavailable 이다.
func (s *Service) issue(ctx context.Context, authKey string, customerKey uuid.UUID) (payment.Card, error) {
	ctx, cancel := context.WithTimeout(ctx, IssueTimeout)
	defer cancel()
	issued, err := s.issuer.IssueCard(ctx, payment.CardRequest{AuthKey: authKey, CustomerKey: customerKey.String()})
	if errors.Is(err, payment.ErrUnknownOutcome) {
		return payment.Card{}, ErrIssuerUnavailable
	}
	return issued, err
}

// RemoveCard 는 카드를 지우고 자동 충전을 끈다. 둘은 한 트랜잭션이다. 카드가 없어도 오류가 아니다.
// 결제 대행사의 빌링키는 지우지 않는다. 이 서버가 키를 잊으면 그 키로 결제할 길이 없다.
func (s *Service) RemoveCard(ctx context.Context, userID uuid.UUID) error {
	return txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		if _, err := queries.DeleteCard(ctx, userID); err != nil {
			return err
		}
		return queries.DisableSettings(ctx, autochargedb.DisableSettingsParams{UserID: userID, Now: s.clock()})
	})
}

// --- 설정 ---

// Get 은 그 사람의 자동 충전이다.
func (s *Service) Get(ctx context.Context, userID uuid.UUID) (View, error) {
	return view(ctx, autochargedb.New(s.pool), userID)
}

// Update 는 설정을 적는다. 값이 틀렸으면 ErrInvalidSettings 다.
// 켜려면 카드가 있어야 하고(ErrNoCard) 지금 결제할 수 있어야 한다(eligibility 의 오류). 끄는 것은 언제나 된다.
// 켜는 동안 카드의 줄을 잠근다. 카드를 지우는 요청과 엇갈려도 "카드 없이 켜짐"으로 남지 않는다.
func (s *Service) Update(ctx context.Context, userID uuid.UUID, settings Settings) (View, error) {
	if err := settings.Validate(); err != nil {
		return View{}, err
	}
	if settings.Enabled {
		if err := s.eligibility.Check(ctx, userID); err != nil {
			return View{}, err
		}
	}
	var updated View
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		if settings.Enabled {
			if err := requireCard(ctx, queries, userID); err != nil {
				return err
			}
		}
		if _, err := queries.UpsertSettings(ctx, autochargedb.UpsertSettingsParams{
			UserID: userID, Enabled: settings.Enabled, Threshold: settings.Threshold,
			ProductID: settings.ProductID, MonthlyLimit: settings.MonthlyLimit, Now: s.clock(),
		}); err != nil {
			return err
		}
		var err error
		updated, err = view(ctx, queries, userID)
		return err
	})
	if err != nil {
		return View{}, err
	}
	return updated, nil
}

// requireCard 는 카드의 줄을 잠근다. 카드가 없으면 ErrNoCard 다.
func requireCard(ctx context.Context, queries *autochargedb.Queries, userID uuid.UUID) error {
	_, err := queries.LockCard(ctx, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNoCard
	}
	return err
}

// --- 탈퇴 ---

// Erase 는 그 사람의 설정, 카드, 고객 키를 지우고, 아직 보내지 않은 충전할 일을 그만둔다. 지운 것이 있으면 true 다.
// 몇 번을 불러도 같다. 이미 보낸 일(charging)은 옮겨 적은 카드로 답을 받을 때까지 둔다. 돈이 나갔을 수 있다.
func (s *Service) Erase(ctx context.Context, userID uuid.UUID) (bool, error) {
	var erased int64
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		skipped, err := queries.SkipOpenRequests(ctx, autochargedb.SkipOpenRequestsParams{UserID: userID, Now: s.clock()})
		if err != nil {
			return err
		}
		erased += skipped
		for _, remove := range []func(context.Context, uuid.UUID) (int64, error){
			queries.DeleteSettings, queries.DeleteCard, queries.DeleteCustomer,
		} {
			removed, err := remove(ctx, userID)
			if err != nil {
				return err
			}
			erased += removed
		}
		return nil
	})
	return erased > 0, err
}

// --- 읽기 ---

// view 는 설정과 카드를 함께 읽는다.
func view(ctx context.Context, queries *autochargedb.Queries, userID uuid.UUID) (View, error) {
	var result View
	settings, err := queries.GetSettings(ctx, userID)
	switch {
	case err == nil:
		result.Settings = &Settings{
			Enabled: settings.Enabled, Threshold: settings.Threshold, ProductID: settings.ProductID, MonthlyLimit: settings.MonthlyLimit,
		}
		result.ConsecutiveFailures = int(settings.ConsecutiveFailures)
	case !errors.Is(err, pgx.ErrNoRows):
		return View{}, err
	}
	card, err := queries.GetCard(ctx, userID)
	switch {
	case err == nil:
		result.Card = &Card{IssuerCode: card.IssuerCode, Number: card.CardNumber, RegisteredAt: card.RegisteredAt}
	case !errors.Is(err, pgx.ErrNoRows):
		return View{}, err
	}
	return result, nil
}

// pgtextOf 는 빈 칸이 아닌 글을 DB 의 글로 바꾼다.
func pgtextOf(text string) pgtype.Text {
	return pgtype.Text{String: text, Valid: true}
}

// pguuidOf 는 번호를 DB 의 빈 칸이 될 수 있는 번호로 바꾼다.
func pguuidOf(id uuid.UUID) pgtype.UUID {
	return pgtype.UUID{Bytes: id, Valid: true}
}
