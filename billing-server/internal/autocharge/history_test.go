// billing-server/internal/autocharge/history_test.go
// 최근 자동 결제 내역(History)을 테스트용 스키마에서 본다. 결제 작업이 끝낸 일과 직접 적은 여러 상태의 일을 읽는다.
// 테이블을 비우지 않으므로 테스트마다 새 사용자를 쓴다.
package autocharge_test

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// farFuture 는 직접 적는 일의 시각이다. 결제 작업은 사용자를 가리지 않으므로, 끝나지 않은 일이 보낼 때가 되거나
// 대사가 오래된 일로 세면 다른 테스트의 수가 흔들린다. 먼 앞의 시각이면 어느 쪽도 가져가지 않는다.
var farFuture = time.Date(2990, 1, 1, 0, 0, 0, 0, time.UTC)

// insertRequest 는 충전할 일 하나를 그 상태로 바로 적는다. 끝난 일은 created 의 1분 뒤에 끝났다.
// 보낸 일(charging)은 카드를 들고 있어야 한다(표의 조건). 그 사람의 끝나지 않은 일은 하나뿐이다.
func insertRequest(t *testing.T, pool *pgxpool.Pool, user uuid.UUID, status, reason string, turnedOff bool, created time.Time) uuid.UUID {
	t.Helper()
	id := uuid.New()
	var finished *time.Time
	var billingKey *string
	var customerKey *uuid.UUID
	switch status {
	case "paid", "declined", "skipped":
		at := created.Add(time.Minute)
		finished = &at
	case "charging":
		key, customer := "billing-"+id.String(), uuid.New()
		billingKey, customerKey = &key, &customer
	}
	if _, err := pool.Exec(context.Background(), `
		INSERT INTO auto_charge_requests (id, user_id, product_id, price, credits, status, skip_reason, turned_off,
			billing_key, customer_key, next_attempt_at, created_at, finished_at)
		VALUES ($1, $2, 'credits-1000', 1000, 1000, $3, $4, $5, $6, $7, $8, $8, $9)`,
		id, user, status, reason, turnedOff, billingKey, customerKey, created, finished); err != nil {
		t.Fatalf("충전할 일을 적지 못했다: %v", err)
	}
	return id
}

func newHistoryService(pool *pgxpool.Pool) *autocharge.Service {
	return autocharge.NewService(pool, time.Now, payment.Fake{}, nil)
}

func TestHistoryShowsWhatTheChargingJobFinished(t *testing.T) {
	f := setUpCharging(t)
	f.enable("")
	f.deposit(70)
	f.spend() // 20: 떨어졌다
	queued, err := f.service.History(context.Background(), f.user)
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	f.round()

	got, err := f.service.History(context.Background(), f.user)
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	if len(queued) != 1 || queued[0].Status != autocharge.HistoryProcessing || queued[0].FinishedAt != nil {
		t.Fatalf("보내기 전 = %+v. 끝나지 않은 일 하나여야 한다", queued)
	}
	if len(got) != 1 || got[0].ID != queued[0].ID || got[0].Status != autocharge.HistoryPaid || got[0].FinishedAt == nil {
		t.Fatalf("결제한 뒤 = %+v. 같은 일이 결제됨이어야 한다", got)
	}
	item := got[0]
	if item.ProductID != "credits-1000" || item.Price != 1_000 || item.Credits != 1_000 || item.Reason != "" || item.TurnedOff {
		t.Errorf("일 = %+v", item)
	}
	var orderStatus string
	if err := f.pool.QueryRow(context.Background(), "SELECT status FROM orders WHERE id = $1", item.ID).Scan(&orderStatus); err != nil || orderStatus != "paid" {
		t.Errorf("같은 번호의 주문 = %q (%v). 결제되었으면 있어야 한다", orderStatus, err)
	}
}

func TestHistoryIsNewestFirstAndOnlyTheirs(t *testing.T) {
	pool := testenv.Pool(t)
	user, other := uuid.New(), uuid.New()
	start := farFuture
	paid := insertRequest(t, pool, user, "paid", "", false, start)
	declined := insertRequest(t, pool, user, "declined", "", true, start.Add(time.Hour))
	stale := insertRequest(t, pool, user, "skipped", autocharge.SkipStale, false, start.Add(2*time.Hour))
	charging := insertRequest(t, pool, user, "charging", "", false, start.Add(3*time.Hour))
	insertRequest(t, pool, other, "paid", "", false, start.Add(4*time.Hour))

	got, err := newHistoryService(pool).History(context.Background(), user)
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}

	want := []struct {
		id        uuid.UUID
		status    string
		reason    string
		turnedOff bool
		finished  bool
	}{
		{charging, autocharge.HistoryProcessing, "", false, false},
		{stale, autocharge.HistorySkipped, autocharge.SkipStale, false, true},
		{declined, autocharge.HistoryDeclined, "", true, true},
		{paid, autocharge.HistoryPaid, "", false, true},
	}
	if len(got) != len(want) {
		t.Fatalf("일 = %+v. 그 사람의 넷이어야 한다", got)
	}
	for i, w := range want {
		item := got[i]
		if item.ID != w.id || item.Status != w.status || item.Reason != w.reason || item.TurnedOff != w.turnedOff || (item.FinishedAt != nil) != w.finished {
			t.Errorf("%d 번째 = %+v. %+v 여야 한다", i, item, w)
		}
	}
}

func TestAPendingRequestIsProcessingToo(t *testing.T) {
	pool := testenv.Pool(t)
	user := uuid.New()
	insertRequest(t, pool, user, "pending", "", false, farFuture)

	got, err := newHistoryService(pool).History(context.Background(), user)

	if err != nil || len(got) != 1 || got[0].Status != autocharge.HistoryProcessing || got[0].FinishedAt != nil {
		t.Fatalf("일 = %+v (%v). 끝나지 않은 일이어야 한다", got, err)
	}
}

func TestHistoryStopsAtTheMostRecentOnes(t *testing.T) {
	pool := testenv.Pool(t)
	user := uuid.New()
	start := farFuture
	var newest uuid.UUID
	for i := range autocharge.HistorySize + 1 {
		newest = insertRequest(t, pool, user, "declined", "", false, start.Add(time.Duration(i)*time.Hour))
	}

	got, err := newHistoryService(pool).History(context.Background(), user)

	if err != nil || len(got) != autocharge.HistorySize || got[0].ID != newest {
		t.Fatalf("일 %d 개 (%v). 가장 늦은 것부터 %d 개여야 한다", len(got), err, autocharge.HistorySize)
	}
	if got[len(got)-1].CreatedAt.Equal(start) {
		t.Errorf("가장 이른 것이 들어 있다. 잘려야 한다")
	}
}

func TestHistoryOfSomeoneWithoutAnyIsEmpty(t *testing.T) {
	got, err := newHistoryService(testenv.Pool(t)).History(context.Background(), uuid.New())

	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("일 = %#v (%v). 빈 목록이어야 한다", got, err)
	}
}
