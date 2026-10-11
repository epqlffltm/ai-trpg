// billing-server/internal/order/helpers_test.go

// 주문 테스트들이 함께 쓰는 도구. 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 돈다.
// 지갑은 진짜를 쓰고, 결제 대행사만 정해 둔 대로 답하는 것으로 바꾼다.
package order_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// 테스트가 쓰는 상품. 1,000원에 1,000크레딧이다.
const (
	productID               = "credits-1000"
	price     int64         = 1_000
	credits   credit.Amount = 1_000
)

// startedAt 은 테스트의 시계가 가리키는 시각이다. 실제 시각과 상관없이 테스트가 늘 같게 돈다.
var startedAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

// scripted 는 정해 둔 대로 답하는 결제 대행사다. 무엇을 몇 번 물어봤는지 적어 둔다.
type scripted struct {
	mu sync.Mutex
	// confirm 과 lookup 은 그 요청에 돌려줄 답이다.
	confirm, lookup       payment.Result
	confirmErr, lookupErr error

	confirms []payment.Request
	lookups  []string
	// deadline 은 마지막 요청이 받은 시간 제한이다.
	deadline time.Duration
}

func (s *scripted) Confirm(ctx context.Context, request payment.Request) (payment.Result, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.confirms = append(s.confirms, request)
	s.deadline = remaining(ctx)
	return s.confirm, s.confirmErr
}

func (s *scripted) Lookup(ctx context.Context, paymentKey string) (payment.Result, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lookups = append(s.lookups, paymentKey)
	s.deadline = remaining(ctx)
	return s.lookup, s.lookupErr
}

// calls 는 승인 요청과 조회를 각각 몇 번 받았는지 돌려준다.
func (s *scripted) calls() (confirms int, lookups int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.confirms), len(s.lookups)
}

// remaining 은 context 에 남은 시간이다. 제한이 없으면 0 이다.
func remaining(ctx context.Context) time.Duration {
	if limit, ok := ctx.Deadline(); ok {
		return time.Until(limit)
	}
	return 0
}

// approving, declining, silent 는 자주 쓰는 결제 대행사들이다.
func approving() *scripted {
	return &scripted{confirm: payment.Result{Status: payment.StatusApproved}, lookup: payment.Result{Status: payment.StatusApproved}}
}

func declining() *scripted {
	declined := payment.Result{Status: payment.StatusDeclined, Code: "card_declined"}
	return &scripted{confirm: declined, lookup: declined}
}

// silent 는 승인 요청에 답하지 않는다. 조회에는 lookup 으로 답한다.
func silent(lookup payment.Result) *scripted {
	return &scripted{confirmErr: payment.ErrUnknownOutcome, lookup: lookup}
}

// fixture 는 테스트 하나가 쓰는 것들이다.
type fixture struct {
	t        *testing.T
	pool     *pgxpool.Pool
	provider *scripted
	wallet   *wallet.Service
	service  *order.Service
	// user 는 이 테스트만 쓰는 새 사용자다.
	user uuid.UUID
}

// setUp 은 테스트용 스키마에 붙는 주문 서비스와 새 사용자를 만든다.
func setUp(t *testing.T, provider *scripted) fixture {
	t.Helper()
	pool := testenv.Pool(t)
	now := func() time.Time { return startedAt }
	wallets := wallet.NewService(pool, now, wallet.Policy{FreeFirst: true, FreeTTL: time.Hour})
	return fixture{
		t:        t,
		pool:     pool,
		provider: provider,
		wallet:   wallets,
		service:  order.NewService(pool, now, provider, wallets),
		user:     uuid.New(),
	}
}

// ctx 는 시간 제한이 걸린 context 를 만든다.
func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// newKey 는 테스트마다 다른 중복 방지 키를 만든다.
func newKey() string {
	return "key-" + uuid.NewString()
}

// newPaymentKey 는 테스트마다 다른 결제 번호를 만든다. 결제 번호는 스키마 전체에서 하나뿐이어야 한다.
func newPaymentKey() string {
	return "pay_" + uuid.NewString()
}

// create 는 이 사용자의 주문을 하나 만든다.
func (f fixture) create() order.Order {
	f.t.Helper()
	created, _, err := f.service.Create(ctx(f.t), f.user, productID, newKey())
	if err != nil {
		f.t.Fatalf("주문을 만들지 못했다: %v", err)
	}
	return created
}

// confirm 은 주문의 승인을 요청하고 끝난 뒤의 주문을 돌려준다.
func (f fixture) confirm(orderID uuid.UUID, paymentKey string) order.Order {
	f.t.Helper()
	confirmed, err := f.service.Confirm(ctx(f.t), f.user, orderID, paymentKey)
	if err != nil {
		f.t.Fatalf("승인을 요청하지 못했다: %v", err)
	}
	return confirmed
}

// stored 는 주문을 서비스를 거치지 않고 DB 에서 직접 읽는다.
func (f fixture) stored(orderID uuid.UUID) order.Order {
	f.t.Helper()
	var o order.Order
	var paymentKey, failureCode *string
	const query = `SELECT id, user_id, product_id, price, credits, status, payment_key, failure_code, created_at, paid_at
		FROM orders WHERE id = $1`
	err := f.pool.QueryRow(ctx(f.t), query, orderID).Scan(
		&o.ID, &o.UserID, &o.ProductID, &o.Price, &o.Credits, &o.Status, &paymentKey, &failureCode, &o.CreatedAt, &o.PaidAt)
	if err != nil {
		f.t.Fatalf("주문을 읽지 못했다: %v", err)
	}
	if paymentKey != nil {
		o.PaymentKey = *paymentKey
	}
	if failureCode != nil {
		o.FailureCode = *failureCode
	}
	return o
}

// wantStatus 는 DB 에 적힌 주문의 상태가 기대와 같은지 본다.
func (f fixture) wantStatus(orderID uuid.UUID, want order.Status) order.Order {
	f.t.Helper()
	got := f.stored(orderID)
	if got.Status != want {
		f.t.Errorf("주문의 상태 = %s, 기대 = %s", got.Status, want)
	}
	return got
}

// wantPaidCredits 는 이 사용자의 산 크레딧과, 주문으로 들어온 원장의 줄 수가 기대와 같은지 본다.
// 잔액만 보면 두 번 들어갔다가 한 번 빠진 것을 놓친다. 그래서 줄 수도 함께 본다.
func (f fixture) wantPaidCredits(balance credit.Amount, depositLines int) {
	f.t.Helper()
	got, err := f.wallet.Balance(ctx(f.t), f.user)
	if err != nil {
		f.t.Fatalf("잔액을 읽지 못했다: %v", err)
	}
	if got.Paid != balance || got.Free != 0 {
		f.t.Errorf("잔액 = %+v, 기대 = 산 크레딧 %d", got, balance)
	}
	var lines int
	const query = "SELECT COUNT(*) FROM ledger_entries WHERE user_id = $1 AND order_id IS NOT NULL"
	if err := f.pool.QueryRow(ctx(f.t), query, f.user).Scan(&lines); err != nil {
		f.t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	if lines != depositLines {
		f.t.Errorf("주문으로 들어온 원장의 줄이 %d 개다. 기대 = %d 개", lines, depositLines)
	}
}

// count 는 이 사용자의 주문이 몇 개인지 센다.
func (f fixture) count() int {
	f.t.Helper()
	var n int
	if err := f.pool.QueryRow(ctx(f.t), "SELECT COUNT(*) FROM orders WHERE user_id = $1", f.user).Scan(&n); err != nil {
		f.t.Fatalf("주문을 세지 못했다: %v", err)
	}
	return n
}
