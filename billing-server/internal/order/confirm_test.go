// billing-server/internal/order/confirm_test.go

package order_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

func TestAnApprovedPaymentPaysTheOrderAndAddsCredits(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()

	confirmed := f.confirm(created.ID, paymentKey)

	if confirmed.Status != order.StatusPaid || confirmed.PaymentKey != paymentKey || confirmed.FailureCode != "" {
		t.Errorf("주문 = %+v", confirmed)
	}
	if confirmed.PaidAt == nil || !confirmed.PaidAt.Equal(startedAt) {
		t.Errorf("치른 시각 = %v, 기대 = %v", confirmed.PaidAt, startedAt)
	}
	f.wantStatus(created.ID, order.StatusPaid)
	f.wantPaidCredits(credits, 1)

	// 원장의 줄이 이 주문을 가리킨다
	var orderID uuid.UUID
	var amount int64
	const query = "SELECT order_id, amount FROM ledger_entries WHERE user_id = $1"
	if err := f.pool.QueryRow(ctx(t), query, f.user).Scan(&orderID, &amount); err != nil {
		t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	if orderID != created.ID || amount != int64(credits) {
		t.Errorf("원장의 줄 = 주문 %v, 양 %d", orderID, amount)
	}
}

func TestTheProviderIsAskedForTheOrdersOwnPrice(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()

	f.confirm(created.ID, paymentKey)

	// 받을 돈은 주문에 적힌 값이다. 클라이언트는 금액을 보내지 않는다
	want := payment.Request{PaymentKey: paymentKey, OrderID: created.ID, Amount: price}
	if len(f.provider.confirms) != 1 || f.provider.confirms[0] != want {
		t.Errorf("결제 대행사가 받은 요청 = %+v, 기대 = %+v", f.provider.confirms, want)
	}
	// 결제 대행사의 답을 끝없이 기다리지 않는다
	if f.provider.deadline <= 0 || f.provider.deadline > order.ProviderTimeout {
		t.Errorf("결제 대행사에 준 시간 = %v. 0 보다 크고 %v 이하여야 한다", f.provider.deadline, order.ProviderTimeout)
	}
}

func TestADeclinedPaymentFailsTheOrderWithoutCredits(t *testing.T) {
	f := setUp(t, declining())
	created := f.create()

	confirmed := f.confirm(created.ID, newPaymentKey())

	if confirmed.Status != order.StatusFailed || confirmed.FailureCode != "card_declined" || confirmed.PaidAt != nil {
		t.Errorf("주문 = %+v", confirmed)
	}
	f.wantStatus(created.ID, order.StatusFailed)
	f.wantPaidCredits(0, 0)
}

func TestADeclineWithoutAReasonStillFailsTheOrder(t *testing.T) {
	f := setUp(t, &scripted{confirm: payment.Result{Status: payment.StatusDeclined}})
	created := f.create()

	confirmed := f.confirm(created.ID, newPaymentKey())

	if confirmed.Status != order.StatusFailed || confirmed.FailureCode != order.FailureCodeUnspecified {
		t.Errorf("주문 = %+v", confirmed)
	}
}

func TestConfirmingAgainDoesNotChargeOrCreditTwice(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()
	f.confirm(created.ID, paymentKey)

	again := f.confirm(created.ID, paymentKey)

	if again.Status != order.StatusPaid {
		t.Errorf("주문 = %+v", again)
	}
	// 끝난 주문은 결제 대행사에 다시 묻지도 않는다
	if confirms, lookups := f.provider.calls(); confirms != 1 || lookups != 0 {
		t.Errorf("승인 요청 %d 번, 조회 %d 번. 기대 = 1 번, 0 번", confirms, lookups)
	}
	f.wantPaidCredits(credits, 1)
}

func TestConfirmingAFailedOrderAgainKeepsItFailed(t *testing.T) {
	f := setUp(t, declining())
	created := f.create()
	paymentKey := newPaymentKey()
	f.confirm(created.ID, paymentKey)
	// 결제 대행사가 이제는 승인한다고 해도 끝난 주문은 되살아나지 않는다
	f.provider.confirm = payment.Result{Status: payment.StatusApproved}
	f.provider.lookup = payment.Result{Status: payment.StatusApproved}

	again := f.confirm(created.ID, paymentKey)

	if again.Status != order.StatusFailed {
		t.Errorf("주문 = %+v", again)
	}
	if confirms, lookups := f.provider.calls(); confirms != 1 || lookups != 0 {
		t.Errorf("승인 요청 %d 번, 조회 %d 번. 기대 = 1 번, 0 번", confirms, lookups)
	}
	f.wantPaidCredits(0, 0)
}

func TestAnOrderCannotSwitchToAnotherPayment(t *testing.T) {
	providers := map[string]*scripted{
		"치른 주문":      approving(),
		"거절된 주문":     declining(),
		"결과를 모르는 주문": silent(payment.Result{Status: payment.StatusPending}),
	}
	for name, provider := range providers {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, provider)
			created := f.create()
			before := f.confirm(created.ID, newPaymentKey())
			provider.confirm, provider.confirmErr = payment.Result{Status: payment.StatusApproved}, nil
			provider.lookup = payment.Result{Status: payment.StatusApproved}

			_, err := f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey())

			if !errors.Is(err, order.ErrPaymentKeyMismatch) {
				t.Errorf("오류 = %v. ErrPaymentKeyMismatch 이어야 한다", err)
			}
			// 주문은 그대로다. 다른 결제 번호로는 결제 대행사에 묻지도 않는다
			after := f.wantStatus(created.ID, before.Status)
			if after.PaymentKey != before.PaymentKey {
				t.Error("주문의 결제 번호가 바뀌었다")
			}
			if confirms, lookups := provider.calls(); confirms != 1 || lookups != 0 {
				t.Errorf("승인 요청 %d 번, 조회 %d 번. 기대 = 1 번, 0 번", confirms, lookups)
			}
		})
	}
}

func TestOnePaymentCannotPayTwoOrders(t *testing.T) {
	f := setUp(t, approving())
	first, second := f.create(), f.create()
	paymentKey := newPaymentKey()
	f.confirm(first.ID, paymentKey)

	_, err := f.service.Confirm(ctx(t), f.user, second.ID, paymentKey)

	if !errors.Is(err, order.ErrPaymentKeyUsed) {
		t.Errorf("오류 = %v. ErrPaymentKeyUsed 이어야 한다", err)
	}
	// 둘째 주문은 손대지 않은 그대로다. 크레딧은 한 번만 들어갔다
	f.wantStatus(second.ID, order.StatusPending)
	f.wantPaidCredits(credits, 1)
	if confirms, _ := f.provider.calls(); confirms != 1 {
		t.Errorf("승인 요청이 %d 번 갔다", confirms)
	}
}

func TestOnlyTheOwnerCanConfirm(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	stranger := uuid.New()

	_, errStranger := f.service.Confirm(ctx(t), stranger, created.ID, newPaymentKey())
	_, errMissing := f.service.Confirm(ctx(t), f.user, uuid.New(), newPaymentKey())

	if !errors.Is(errStranger, order.ErrNotFound) || !errors.Is(errMissing, order.ErrNotFound) {
		t.Errorf("남의 주문 = %v, 없는 주문 = %v. 둘 다 ErrNotFound 이어야 한다", errStranger, errMissing)
	}
	f.wantStatus(created.ID, order.StatusPending)
	if confirms, lookups := f.provider.calls(); confirms+lookups != 0 {
		t.Error("남의 주문인데 결제 대행사를 불렀다")
	}
}

func TestConfirmRejectsBadPaymentKeys(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	keys := map[string]string{
		"비었다":   "",
		"빈칸":    "pay 123",
		"줄 바꿈":  "pay_123\n",
		"너무 길다": strings.Repeat("p", 201),
		"한글":    "결제_123",
	}
	for name, key := range keys {
		t.Run(name, func(t *testing.T) {
			if _, err := f.service.Confirm(ctx(t), f.user, created.ID, key); !errors.Is(err, order.ErrInvalidPaymentKey) {
				t.Errorf("오류 = %v. ErrInvalidPaymentKey 이어야 한다", err)
			}
		})
	}
	f.wantStatus(created.ID, order.StatusPending)
	if confirms, lookups := f.provider.calls(); confirms+lookups != 0 {
		t.Error("틀린 결제 번호인데 결제 대행사를 불렀다")
	}
}

func TestAnUnansweredPaymentLeavesTheOrderConfirming(t *testing.T) {
	errs := map[string]error{
		"답이 오지 않았다": payment.ErrUnknownOutcome,
		"연결이 끊겼다":   errors.New("connection reset by peer"),
		"시간이 다 되었다": context.DeadlineExceeded,
	}
	for name, providerErr := range errs {
		t.Run(name, func(t *testing.T) {
			f := setUp(t, &scripted{confirmErr: providerErr})
			created := f.create()
			paymentKey := newPaymentKey()

			confirmed, err := f.service.Confirm(ctx(t), f.user, created.ID, paymentKey)

			// 실패가 아니다. 돈이 나갔을 수도 있다. 오류로 답하지도 않고, 실패로 적지도 않는다
			if err != nil || confirmed.Status != order.StatusConfirming || confirmed.PaymentKey != paymentKey {
				t.Errorf("주문 = %+v, %v", confirmed, err)
			}
			f.wantStatus(created.ID, order.StatusConfirming)
			f.wantPaidCredits(0, 0)
		})
	}
}

func TestConfirmingAgainFinishesAnUnansweredPayment(t *testing.T) {
	cases := []struct {
		name        string
		truth       payment.Result
		wantStatus  order.Status
		wantCredits credit.Amount
		wantLines   int
	}{
		{"실제로는 승인되었다", payment.Result{Status: payment.StatusApproved}, order.StatusPaid, credits, 1},
		{"실제로는 거절되었다", payment.Result{Status: payment.StatusDeclined, Code: "card_declined"}, order.StatusFailed, 0, 0},
		{"결제 대행사도 아직 모른다", payment.Result{Status: payment.StatusPending}, order.StatusConfirming, 0, 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := setUp(t, silent(tc.truth))
			created := f.create()
			paymentKey := newPaymentKey()
			f.confirm(created.ID, paymentKey)

			again := f.confirm(created.ID, paymentKey)

			if again.Status != tc.wantStatus {
				t.Errorf("주문의 상태 = %s, 기대 = %s", again.Status, tc.wantStatus)
			}
			f.wantStatus(created.ID, tc.wantStatus)
			f.wantPaidCredits(tc.wantCredits, tc.wantLines)
			// 두 번째에는 승인을 다시 요청하지 않고 결과를 묻는다. 승인을 두 번 요청하면 돈이 두 번 나갈 수 있다
			if confirms, lookups := f.provider.calls(); confirms != 1 || lookups != 1 {
				t.Errorf("승인 요청 %d 번, 조회 %d 번. 기대 = 1 번, 1 번", confirms, lookups)
			}
			f.provider.lookedUp(t, created.ID, paymentKey)
		})
	}
}

func TestAFailedLookupLeavesTheOrderConfirming(t *testing.T) {
	f := setUp(t, &scripted{confirmErr: payment.ErrUnknownOutcome, lookupErr: errors.New("provider is down")})
	created := f.create()
	paymentKey := newPaymentKey()
	f.confirm(created.ID, paymentKey)

	again, err := f.service.Confirm(ctx(t), f.user, created.ID, paymentKey)

	if err != nil || again.Status != order.StatusConfirming {
		t.Errorf("주문 = %+v, %v", again, err)
	}
	f.wantPaidCredits(0, 0)
}

func TestConfirmFinishesEvenIfTheCallerLeaves(t *testing.T) {
	// 요청을 보낸 쪽이 연결을 끊었다. 결제 대행사는 이미 돈을 받았을 수 있으니 끝까지 적는다
	f := setUp(t, approving())
	created := f.create()
	gone, cancel := context.WithCancel(ctx(t))
	cancel()

	confirmed, err := f.service.Confirm(gone, f.user, created.ID, newPaymentKey())

	if err != nil || confirmed.Status != order.StatusPaid {
		t.Errorf("주문 = %+v, %v", confirmed, err)
	}
	f.wantPaidCredits(credits, 1)
}

// brokenWallet 은 크레딧을 넣다가 실패하는 지갑이다. 청약철회의 일은 진짜 지갑의 것을 쓰지 않는다(부르지 않는다).
type brokenWallet struct {
	order.Refunder
	calls int
}

func (b *brokenWallet) DepositForOrder(context.Context, pgx.Tx, uuid.UUID, credit.Amount, uuid.UUID) error {
	b.calls++
	return errors.New("wallet is broken")
}

func TestAnOrderIsNotPaidUnlessTheCreditsGoIn(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()
	broken := &brokenWallet{}
	failing := newService(t, f.pool, func() time.Time { return startedAt }, f.provider, broken)

	_, err := failing.Confirm(ctx(t), f.user, created.ID, paymentKey)

	// 크레딧을 넣지 못했으면 주문도 치른 것으로 적지 않는다. 둘은 함께 되거나 함께 안 된다
	if err == nil || broken.calls != 1 {
		t.Fatalf("오류 = %v, 지갑을 부른 횟수 = %d", err, broken.calls)
	}
	f.wantStatus(created.ID, order.StatusConfirming)
	f.wantPaidCredits(0, 0)

	// 지갑이 돌아온 뒤 같은 요청을 다시 보내면 마저 끝난다
	again := f.confirm(created.ID, paymentKey)
	if again.Status != order.StatusPaid {
		t.Errorf("주문 = %+v", again)
	}
	f.wantPaidCredits(credits, 1)
}

func TestConcurrentConfirmsCreditOnce(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	paymentKey := newPaymentKey()
	const n = 20
	statuses := make([]order.Status, n)
	errs := make([]error, n)

	start := make(chan struct{})
	var done sync.WaitGroup
	for index := range n {
		done.Add(1)
		go func() {
			defer done.Done()
			<-start
			confirmed, err := f.service.Confirm(ctx(t), f.user, created.ID, paymentKey)
			statuses[index], errs[index] = confirmed.Status, err
		}()
	}
	close(start)
	done.Wait()

	for index := range n {
		if errs[index] != nil || statuses[index] != order.StatusPaid {
			t.Errorf("%d 번째: %s, %v. 모두 paid 여야 한다", index, statuses[index], errs[index])
		}
	}
	// 스무 요청이 함께 왔어도 승인은 한 번만 요청했고 크레딧은 한 번만 들어갔다
	if confirms, _ := f.provider.calls(); confirms != 1 {
		t.Errorf("승인 요청이 %d 번 갔다", confirms)
	}
	f.wantPaidCredits(credits, 1)
}

func TestConcurrentConfirmsWithDifferentPaymentsPayOnce(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()
	const n = 10
	errs := make([]error, n)

	start := make(chan struct{})
	var done sync.WaitGroup
	for index := range n {
		done.Add(1)
		go func() {
			defer done.Done()
			<-start
			_, errs[index] = f.service.Confirm(ctx(t), f.user, created.ID, newPaymentKey())
		}()
	}
	close(start)
	done.Wait()

	won := 0
	for _, err := range errs {
		switch {
		case err == nil:
			won++
		case !errors.Is(err, order.ErrPaymentKeyMismatch):
			t.Errorf("뜻밖의 오류: %v", err)
		}
	}
	// 결제 번호가 서로 다른 요청들이다. 하나만 이 주문을 차지하고, 나머지의 결제는 승인을 요청하지 않는다
	if confirms, _ := f.provider.calls(); won != 1 || confirms != 1 {
		t.Errorf("성공 %d 번, 승인 요청 %d 번. 둘 다 1 이어야 한다", won, confirms)
	}
	f.wantPaidCredits(credits, 1)
}
