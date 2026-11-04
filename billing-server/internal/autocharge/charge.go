// billing-server/internal/autocharge/charge.go

package autocharge

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eligibility"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// 결제하기(#980 의 둘째 단계). 따로 도는 작업(cmd/autocharge)이 한 바퀴마다 적어 둔 일을 결제한다(ChargeRound).
//
//  1. 차지하기: 때가 된 일 하나를 잠그고 임대를 건다. 결제 대행사를 부르는 동안에는 잠금을 쥐지 않는다
//  2. 보내기 전(pending): 아직 켜져 있는지, 카드가 있는지, 지금 결제할 수 있는지, 한 달 상한을 넘지 않는지 본다.
//     하나라도 아니면 그만둔다(skipped). 실패로 세지 않는다. 모두 맞으면 카드를 일에 옮겨 적고 charging 으로 바꾼다.
//     적힌 지 PendingFor(하루)가 지난 일은 보내지 않고 그만둔다(stale). 결제 작업이 멈춰 있었던 것이다.
//     며칠 전의 잔액으로 사지 않고, armed 를 다시 켜 다음에 골드가 떨어질 때 그때의 설정으로 산다(2026-11-04 결정)
//  3. 보내기(charging): 일의 번호를 주문 번호이자 멱등키로 빌링키 결제를 보낸다
//     - 승인: 한 트랜잭션에서 일을 끝내고, paid 인 주문을 적고, 골드를 넣고, 이어서 실패한 수를 0 으로 한다
//     - 거절: 일을 끝내고 이어서 실패한 수를 늘린다. MaxFailures 가 되면 끈다. 다시 보내지 않는다
//     - 모름: 그대로 두고 간격을 늘려 같은 것을 다시 보낸다. 결제 대행사가 처음의 답을 준다
//  4. 다시 보내는 것은 일이 적힌 뒤 ResendFor(3일)까지다. 결제 대행사의 멱등키는 15일만 쓸 수 있어서 그 전에 멈춘다.
//     그 뒤로는 보내지 않고 주문 번호로 조회한다(payment.CardCharger.LookupCharge). 조회는 결제를 만들지 않는다
//     - 완료: 승인과 같다. 결제가 없거나 끝내 되지 않았다: 거절과 같다(돈이 나가지 않았다)
//     - 그 밖: 그대로 두고 간격을 두어 다시 조회한다. 하루가 지나면 대사가 사람에게 넘긴다(autocharge.stuck). 사람은 Resolve 로 정한다
//
// charging 이 된 일은 그만두지 않는다. 돈이 나갔을 수 있다. 그새 끄거나 카드를 지워도 옮겨 적은 카드로 답을 받을 때까지 보낸다.

const (
	// MaxFailures 는 이어서 실패하면 자동 충전을 끄는 수다(2026-11-04 결정).
	MaxFailures = 3
	// PendingFor 는 보내지 않은 일(pending)을 보내는 기한이다. 일이 적힌 때부터 센다(2026-11-04 결정).
	// 결제 작업은 10초마다 돌아서, 이만큼 남았으면 작업이 멈춰 있었던 것이다. 대사가 사람에게 넘기는 기준(하루)과 같다.
	// ResendFor 와 다르다. 그것은 이미 보낸 일(charging)을 다시 보내는 기한이고, 보낸 일은 돈이 나갔을 수 있어 그만두지 않는다.
	PendingFor = 24 * time.Hour
	// ResendFor 는 답을 받지 못한 결제를 다시 보내는 기한이다. 일이 적힌 때부터 센다(2026-11-04 결정).
	// 그 뒤로는 주문 번호로 조회만 한다. 결제 대행사의 멱등키(15일)보다 넉넉히 짧고,
	// 골드가 떨어진 지 며칠 뒤에 결제되어 사용자가 놀라는 일을 줄인다.
	ResendFor = 72 * time.Hour
	// ChargeTimeout 은 빌링키 결제의 답을 기다리는 가장 긴 시간이다.
	ChargeTimeout = 15 * time.Second
	// ChargeLease 는 보내는 동안 다른 작업이 가져가지 않는 시간이다. ChargeTimeout 보다 넉넉하다.
	ChargeLease = 60 * time.Second
	// firstRetryDelay 와 maxRetryDelay 는 답을 받지 못했을 때 다시 보내기까지의 간격이다. 실패할 때마다 두 배가 된다.
	firstRetryDelay = 10 * time.Second
	maxRetryDelay   = time.Hour
	// maxErrorLength 는 마지막 오류를 적는 가장 긴 길이다.
	maxErrorLength = 200
)

// 충전할 일의 상태. auto_charge_requests.status 에 그대로 적힌다.
const (
	statusPending  = "pending"
	statusCharging = "charging"
	statusPaid     = "paid"
	statusDeclined = "declined"
)

// 보내기 전에 그만둔 까닭. auto_charge_requests.skip_reason 에 그대로 적힌다.
const (
	SkipDisabled    = "disabled"
	SkipNoCard      = "no_card"
	SkipNotEligible = "not_eligible"
	SkipMonthlyCap  = "monthly_limit"
	// SkipStale 은 적힌 지 PendingFor 가 지나도록 보내지 못한 것이다. 실패로 세지 않고 알리지 않는다(사용자가 할 일이 없다)
	SkipStale = "stale"
)

// korea 는 한 달의 시작을 셀 때의 시간대다. 한국은 일광 절약 시간이 없어 고정이다.
var korea = time.FixedZone("KST", 9*60*60)

// Orders 는 승인된 결제를 주문으로 적고, 자동 충전으로 치른 돈을 세는 것의 모양이다. *order.Service 가 이 모양이다.
type Orders interface {
	RecordAutoPaidInTx(ctx context.Context, tx pgx.Tx, paid order.AutoPaid) (bool, error)
	CountAutoPaid(ctx context.Context)
	AutoPaidSince(ctx context.Context, userID uuid.UUID, since time.Time) (int64, error)
}

// ChargeResult 는 한 바퀴에서 한 일이다.
type ChargeResult struct {
	Paid     int
	Declined int
	Skipped  int
	// Retried 는 답을 받지 못해 다시 보내거나 다시 조회할 수다.
	Retried int
	// LookedUp 은 다시 보내는 기한이 지나 보내지 않고 조회한 수다. 조회의 결과도 Paid, Declined, Retried 에 함께 센다.
	LookedUp int
}

// Any 는 한 일이 있는지다.
func (r ChargeResult) Any() bool {
	return r.Paid > 0 || r.Declined > 0 || r.Skipped > 0 || r.Retried > 0 || r.LookedUp > 0
}

// WithCharging 은 결제하는 일을 붙인 Service 를 돌려준다. 결제하는 작업(cmd/autocharge)만 붙인다.
func (s *Service) WithCharging(charger payment.CardCharger, orders Orders) *Service {
	changed := *s
	changed.charger, changed.orders = charger, orders
	return &changed
}

// ChargeRound 는 때가 된 일을 limit 개까지 결제한다. 하나를 끝내지 못해도 나머지를 한다. DB 의 오류만 돌려준다.
func (s *Service) ChargeRound(ctx context.Context, limit int) (ChargeResult, error) {
	var result ChargeResult
	for range limit {
		outcome, lookedUp, err := s.chargeNext(ctx)
		if lookedUp {
			result.LookedUp++
		}
		if err != nil {
			return result, err
		}
		switch outcome {
		case outcomeNone:
			return result, nil
		case outcomePaid:
			result.Paid++
		case outcomeDeclined:
			result.Declined++
		case outcomeSkipped:
			result.Skipped++
		case outcomeRetried:
			result.Retried++
		}
	}
	return result, nil
}

type outcome int

const (
	outcomeNone outcome = iota
	outcomePaid
	outcomeDeclined
	outcomeSkipped
	outcomeRetried
)

// chargeNext 는 때가 된 일 하나를 차지하고 끝까지 한다. 다시 보내는 기한이 지났으면 보내지 않고 조회한다(두 번째 값이 true).
func (s *Service) chargeNext(ctx context.Context) (outcome, bool, error) {
	now := s.clock()
	request, found, err := s.claim(ctx, now)
	if err != nil || !found {
		return outcomeNone, false, err
	}
	if request.Status == statusPending {
		started, skipped, err := s.prepare(ctx, request, now)
		if err != nil || skipped {
			return outcomeSkipped, false, err
		}
		request = started
	}
	if PastResend(request.CreatedAt, now) {
		result, err := s.lookUp(ctx, request, now)
		return result, true, err
	}
	result, err := s.send(ctx, request, now)
	return result, false, err
}

// PastResend 는 그때 적힌 일이 지금은 다시 보내는 기한(ResendFor)을 지났는지다. 지났으면 보내지 않는다.
func PastResend(createdAt time.Time, now time.Time) bool {
	return !now.Before(createdAt.Add(ResendFor))
}

// claim 은 때가 된 일 하나를 잠그고, 임대가 끝나는 때까지 다른 쪽이 가져가지 않게 적는다.
func (s *Service) claim(ctx context.Context, now time.Time) (autochargedb.AutoChargeRequest, bool, error) {
	var claimed autochargedb.AutoChargeRequest
	found := false
	err := pgx.BeginFunc(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		row, err := queries.LockDueRequest(ctx, now)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		claimed, found = row, true
		claimed.Attempts++
		return queries.LeaseRequest(ctx, autochargedb.LeaseRequestParams{Until: now.Add(ChargeLease), ID: row.ID})
	})
	return claimed, found, err
}

// prepare 는 보내기 전의 일을 살펴 그만두거나, 카드를 옮겨 적고 charging 으로 바꾼다. 그만뒀으면 두 번째 값이 true 다.
func (s *Service) prepare(ctx context.Context, request autochargedb.AutoChargeRequest, now time.Time) (autochargedb.AutoChargeRequest, bool, error) {
	if PastPending(request.CreatedAt, now) {
		return request, true, s.skipStale(ctx, request, now)
	}
	reason, err := s.refusal(ctx, request, now)
	if err != nil {
		return request, false, err
	}
	queries := autochargedb.New(s.pool)
	var card autochargedb.GetChargeCardRow
	if reason == "" {
		card, err = queries.GetChargeCard(ctx, request.UserID)
		if errors.Is(err, pgx.ErrNoRows) {
			reason = SkipNoCard
		} else if err != nil {
			return request, false, err
		}
	}
	if reason != "" {
		_, err := queries.SkipRequest(ctx, autochargedb.SkipRequestParams{ID: request.ID, Reason: reason, Now: now})
		return request, true, err
	}
	if _, err := queries.StartCharging(ctx, autochargedb.StartChargingParams{
		ID: request.ID, BillingKey: pgtextOf(card.BillingKey), CustomerKey: pguuidOf(card.CustomerKey),
	}); err != nil {
		return request, false, err
	}
	request.Status, request.BillingKey, request.CustomerKey = statusCharging, pgtextOf(card.BillingKey), pguuidOf(card.CustomerKey)
	return request, false, nil
}

// PastPending 은 그때 적힌 일이 지금은 보내는 기한(PendingFor)을 지났는지다. 지났으면 보내지 않는다.
func PastPending(createdAt time.Time, now time.Time) bool {
	return !now.Before(createdAt.Add(PendingFor))
}

// skipStale 은 늦은 일을 그만두고 armed 를 다시 켠다. 한 트랜잭션이다. 다른 쪽이 먼저 끝냈으면 켜지 않는다.
// 일을 적을 때 armed 를 껐다. 다시 켜지 않으면 잔액이 기준 아래에 있는 동안 다시 사지 않는다(기준 이상을 봐야 켜진다).
func (s *Service) skipStale(ctx context.Context, request autochargedb.AutoChargeRequest, now time.Time) error {
	return txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		skipped, err := queries.SkipRequest(ctx, autochargedb.SkipRequestParams{ID: request.ID, Reason: SkipStale, Now: now})
		if err != nil || skipped == 0 {
			return err
		}
		return queries.SetArmed(ctx, autochargedb.SetArmedParams{UserID: request.UserID, Armed: true})
	})
}

// refusal 은 보내지 않을 까닭이다. 보내도 되면 빈 글자다. 결제 자격의 오류가 아닌 오류(DB)는 오류로 돌려준다.
func (s *Service) refusal(ctx context.Context, request autochargedb.AutoChargeRequest, now time.Time) (string, error) {
	settings, err := autochargedb.New(s.pool).GetSettings(ctx, request.UserID)
	if errors.Is(err, pgx.ErrNoRows) || (err == nil && !settings.Enabled) {
		return SkipDisabled, nil
	}
	if err != nil {
		return "", err
	}
	if reason, err := s.eligibilityRefusal(ctx, request.UserID); reason != "" || err != nil {
		return reason, err
	}
	spent, err := s.orders.AutoPaidSince(ctx, request.UserID, MonthStart(now))
	if err != nil {
		return "", err
	}
	if spent+request.Price > settings.MonthlyLimit {
		return SkipMonthlyCap, nil
	}
	return "", nil
}

// eligibilityRefusal 은 지금 결제할 수 없으면 SkipNotEligible 이다. 미성년자가 보호자 동의를 잃은 것도 여기서 걸린다.
func (s *Service) eligibilityRefusal(ctx context.Context, userID uuid.UUID) (string, error) {
	err := s.eligibility.Check(ctx, userID)
	if errors.Is(err, eligibility.ErrVerificationRequired) || errors.Is(err, eligibility.ErrGuardianConsentRequired) {
		return SkipNotEligible, nil
	}
	return "", err
}

// send 는 빌링키 결제를 보내고 답을 적는다.
func (s *Service) send(ctx context.Context, request autochargedb.AutoChargeRequest, now time.Time) (outcome, error) {
	charged, err := s.charge(ctx, request)
	return s.settle(ctx, request, charged, err, now)
}

// lookUp 은 주문 번호로 결제를 조회하고 답을 적는다. 결제를 만들지 않는다.
func (s *Service) lookUp(ctx context.Context, request autochargedb.AutoChargeRequest, now time.Time) (outcome, error) {
	found, err := s.lookup(ctx, request)
	return s.settle(ctx, request, found, err, now)
}

// settle 은 결제 대행사의 답(보낸 것이나 조회한 것)을 적는다. 답이 없거나 아직 모르면 미룬다.
func (s *Service) settle(
	ctx context.Context, request autochargedb.AutoChargeRequest, charged payment.ChargeResult, err error, now time.Time,
) (outcome, error) {
	if err != nil || charged.Status == payment.StatusPending {
		cause := err
		if cause == nil {
			cause = errors.New("결제 대행사가 아직 결과를 모른다")
		}
		return outcomeRetried, s.delay(ctx, request, cause, now)
	}
	if charged.Status == payment.StatusApproved {
		_, err := s.settlePaid(ctx, request, charged.PaymentKey)
		return outcomePaid, err
	}
	_, err = s.settleDeclined(ctx, request, charged.Code)
	return outcomeDeclined, err
}

// charge 는 옮겨 적은 카드로 빌링키 결제를 보내되 ChargeTimeout 까지만 기다린다.
func (s *Service) charge(ctx context.Context, request autochargedb.AutoChargeRequest) (payment.ChargeResult, error) {
	ctx, cancel := context.WithTimeout(ctx, ChargeTimeout)
	defer cancel()
	product, _ := catalog.Find(request.ProductID)
	return s.charger.ChargeCard(ctx, payment.CardCharge{
		BillingKey: request.BillingKey.String, CustomerKey: uuid.UUID(request.CustomerKey.Bytes).String(),
		OrderID: request.ID, Amount: request.Price, OrderName: orderName(product, request.ProductID),
	})
}

// lookup 은 주문 번호로 결제를 조회하되 ChargeTimeout 까지만 기다린다.
func (s *Service) lookup(ctx context.Context, request autochargedb.AutoChargeRequest) (payment.ChargeResult, error) {
	ctx, cancel := context.WithTimeout(ctx, ChargeTimeout)
	defer cancel()
	return s.charger.LookupCharge(ctx, payment.CardCharge{
		BillingKey: request.BillingKey.String, CustomerKey: uuid.UUID(request.CustomerKey.Bytes).String(),
		OrderID: request.ID, Amount: request.Price,
	})
}

// settlePaid 는 한 트랜잭션에서 일을 끝내고, 주문을 적고, 골드를 넣고, 이어서 실패한 수를 0 으로 한다.
// 다른 쪽(다른 작업, 사람의 결정)이 먼저 끝냈으면 아무것도 하지 않는다. 끝냈으면 true 다.
func (s *Service) settlePaid(ctx context.Context, request autochargedb.AutoChargeRequest, paymentKey string) (bool, error) {
	recorded, settled := false, false
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		finished, err := queries.FinishRequest(ctx, autochargedb.FinishRequestParams{ID: request.ID, Status: statusPaid, Now: s.clock()})
		if err != nil || finished == 0 {
			return err
		}
		settled = true
		recorded, err = s.orders.RecordAutoPaidInTx(ctx, tx, order.AutoPaid{
			ID: request.ID, UserID: request.UserID, ProductID: request.ProductID,
			Price: request.Price, Credits: request.Credits, PaymentKey: paymentKey,
		})
		if err != nil {
			return err
		}
		return queries.CountSucceeded(ctx, request.UserID)
	})
	if err == nil && recorded {
		s.orders.CountAutoPaid(ctx)
	}
	return settled && err == nil, err
}

// settleDeclined 는 한 트랜잭션에서 일을 끝내고 이어서 실패한 수를 늘린다. MaxFailures 가 되면 끈다.
// 다른 쪽이 먼저 끝냈으면 아무것도 하지 않는다. 끝냈으면 true 다.
func (s *Service) settleDeclined(ctx context.Context, request autochargedb.AutoChargeRequest, code string) (bool, error) {
	if code == "" {
		code = order.FailureCodeUnspecified
	}
	settled := false
	err := txn.Run(ctx, s.pool, func(tx pgx.Tx) error {
		queries := autochargedb.New(tx)
		finished, err := queries.FinishRequest(ctx, autochargedb.FinishRequestParams{
			ID: request.ID, Status: statusDeclined, FailureCode: code, Now: s.clock(),
		})
		if err != nil || finished == 0 {
			return err
		}
		settled = true
		counted, err := queries.CountFailed(ctx, autochargedb.CountFailedParams{UserID: request.UserID, MaxFailures: MaxFailures, Now: s.clock()})
		if errors.Is(err, pgx.ErrNoRows) {
			// 설정을 지웠다(탈퇴). 셀 곳이 없다
			return nil
		}
		if err != nil || !turnedOff(counted.ConsecutiveFailures) {
			return err
		}
		return queries.MarkTurnedOff(ctx, request.ID)
	})
	return settled && err == nil, err
}

// turnedOff 는 이번 거절로 자동 충전을 껐는지다. 이어서 실패한 수가 처음 MaxFailures 에 닿은 때다.
// 그 뒤로는 꺼져 있어 이 일이 적히지 않는다(보내기 전에 그만둔다).
func turnedOff(failures int32) bool {
	return failures == MaxFailures
}

// delay 는 답을 받지 못했다고 적고 다음 시도 시각을 정한다.
func (s *Service) delay(ctx context.Context, request autochargedb.AutoChargeRequest, cause error, now time.Time) error {
	return autochargedb.New(s.pool).DelayRequest(ctx, autochargedb.DelayRequestParams{
		NextAttemptAt: now.Add(retryDelay(int(request.Attempts))),
		LastError:     cut(cause.Error(), maxErrorLength),
		ID:            request.ID,
	})
}

// MonthStart 는 at 이 든 달(한국 날짜)의 첫날 0시다.
func MonthStart(at time.Time) time.Time {
	local := at.In(korea)
	return time.Date(local.Year(), local.Month(), 1, 0, 0, 0, 0, korea)
}

// retryDelay 는 attempts 번 시도한 뒤에 기다릴 시간이다. 처음이 firstRetryDelay 이고 두 배씩 늘어 maxRetryDelay 에서 멈춘다.
func retryDelay(attempts int) time.Duration {
	delay := firstRetryDelay
	for i := 1; i < attempts && delay < maxRetryDelay; i++ {
		delay *= 2
	}
	return min(delay, maxRetryDelay)
}

// cut 은 글을 n 바이트 안으로 자른다. 글자 가운데서 자르지 않는다.
func cut(text string, n int) string {
	if len(text) <= n {
		return text
	}
	runes := []rune(text)
	for len(string(runes)) > n {
		runes = runes[:len(runes)-1]
	}
	return string(runes)
}

// orderName 은 결제 대행사의 결제 내역에 보이는 이름이다.
func orderName(product catalog.Product, productID string) string {
	if product.Name == "" {
		return fmt.Sprintf("자동 충전 %s", productID)
	}
	return "자동 충전 " + product.Name
}
