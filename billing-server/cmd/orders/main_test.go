// billing-server/cmd/orders/main_test.go

// 명령 줄을 읽는 것과 결과를 찍는 것을 DB 없이 확인한다. 주문 서비스의 자리에는 받은 것을 적어 두는 가짜를 넣는다.
package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

const testOrderID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

// fakeOrders 는 정해 둔 대로 답하는 가짜 주문 서비스다. 받은 것을 적어 둔다.
type fakeOrders struct {
	stuck     []order.Order
	decided   order.Order
	err       error
	olderThan time.Duration
	decision  order.Decision
}

func (f *fakeOrders) ListStuck(_ context.Context, olderThan time.Duration, _ int) ([]order.Order, error) {
	f.olderThan = olderThan
	return f.stuck, f.err
}

func (f *fakeOrders) Decide(_ context.Context, decision order.Decision) (order.Order, error) {
	f.decision = decision
	return f.decided, f.err
}

func TestParseStuck(t *testing.T) {
	req, err := parse([]string{"stuck"}, "cli:me")
	if err != nil || req.action != actionStuck || req.olderThan != order.StuckAfter {
		t.Errorf("일 = %+v, %v", req, err)
	}
	req, err = parse([]string{"stuck", "-older-than", "2h"}, "cli:me")
	if err != nil || req.olderThan != 2*time.Hour {
		t.Errorf("일 = %+v, %v", req, err)
	}
}

func TestParseDecideReadsOptionsAnywhere(t *testing.T) {
	for _, args := range [][]string{
		{"decide", testOrderID, "paid", "-reason", "상점관리자에서 완료"},
		{"-reason", "상점관리자에서 완료", "decide", testOrderID, "paid"},
	} {
		req, err := parse(args, "cli:me")
		want := order.Decision{OrderID: uuid.MustParse(testOrderID), Outcome: order.OutcomePaid, Reason: "상점관리자에서 완료", DecidedBy: "cli:me"}
		if err != nil || req.action != actionDecide || req.decision != want {
			t.Errorf("%v: 일 = %+v, %v", args, req, err)
		}
	}
	req, err := parse([]string{"decide", testOrderID, "refunded", "-reason", "환불 완료", "-by", "운영자 김"}, "cli:me")
	if err != nil || req.decision.DecidedBy != "운영자 김" || req.decision.Outcome != order.OutcomeRefunded {
		t.Errorf("일 = %+v, %v", req, err)
	}
}

func TestParseRefusesWhatItCannotUse(t *testing.T) {
	cases := map[string][]string{
		"없다":            {},
		"모르는 일":         {"fix"},
		"근거가 없다":        {"decide", testOrderID, "paid"},
		"모르는 결과":        {"decide", testOrderID, "expired", "-reason", "x"},
		"주문 번호가 이상하다":   {"decide", "order-1", "paid", "-reason", "x"},
		"결과가 없다":        {"decide", testOrderID, "-reason", "x"},
		"기간이 0":         {"stuck", "-older-than", "0s"},
		"모르는 옵션":        {"stuck", "-all"},
		"stuck 에 낱말이 더": {"stuck", testOrderID},
	}
	for name, args := range cases {
		if _, err := parse(args, "cli:me"); err == nil {
			t.Errorf("%s: 오류가 나야 한다", name)
		}
	}
}

func TestDoListsStuckOrdersWithoutPaymentKeys(t *testing.T) {
	since := time.Date(2026, 3, 1, 9, 0, 0, 0, time.UTC)
	service := &fakeOrders{stuck: []order.Order{
		{ID: uuid.MustParse(testOrderID), Status: order.StatusConfirming, UpdatedAt: since, Price: 1000, PaymentKey: "tgen_secret"},
		{ID: uuid.New(), Status: order.StatusRefunding, UpdatedAt: since, Price: 5000},
	}}
	var out bytes.Buffer

	err := do(context.Background(), service, request{action: actionStuck, olderThan: time.Hour}, &out)

	text := out.String()
	if err != nil || service.olderThan != time.Hour {
		t.Fatalf("오류 = %v, 넘긴 기간 = %v", err, service.olderThan)
	}
	if strings.Count(text, "\n") != 2 || !strings.Contains(text, testOrderID) || !strings.Contains(text, "승인 확인") ||
		!strings.Contains(text, "환불 확인") || !strings.Contains(text, "1000원") {
		t.Errorf("화면 = %s", text)
	}
	if strings.Contains(text, "tgen_secret") {
		t.Errorf("화면에 결제 번호가 찍혔다: %s", text)
	}
}

func TestDoSaysWhenNothingIsStuck(t *testing.T) {
	var out bytes.Buffer

	if err := do(context.Background(), &fakeOrders{}, request{action: actionStuck, olderThan: time.Hour}, &out); err != nil {
		t.Fatalf("오류 = %v", err)
	}

	if !strings.Contains(out.String(), "결과를 모르는 주문이 없습니다") {
		t.Errorf("화면 = %s", out.String())
	}
}

func TestDoPassesTheDecisionAndPrintsTheResult(t *testing.T) {
	decision := order.Decision{OrderID: uuid.MustParse(testOrderID), Outcome: order.OutcomeFailed, Reason: "결제 없음", DecidedBy: "cli:me"}
	service := &fakeOrders{decided: order.Order{ID: decision.OrderID, Status: order.StatusFailed}}
	var out bytes.Buffer

	err := do(context.Background(), service, request{action: actionDecide, decision: decision}, &out)

	if err != nil || service.decision != decision || !strings.Contains(out.String(), "정했습니다: "+testOrderID+"  failed  ") {
		t.Errorf("오류 = %v, 넘긴 결정 = %+v, 화면 = %s", err, service.decision, out.String())
	}
}

func TestDoReturnsTheServicesError(t *testing.T) {
	service := &fakeOrders{err: order.ErrDecidedElsewhere}

	err := do(context.Background(), service, request{action: actionDecide}, &bytes.Buffer{})

	if !errors.Is(err, order.ErrDecidedElsewhere) {
		t.Errorf("오류 = %v", err)
	}
}
