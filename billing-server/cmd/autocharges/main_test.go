// billing-server/cmd/autocharges/main_test.go

// 명령 줄을 읽는 것과 결과를 찍는 것을 DB 없이 확인한다. 자동 충전 서비스의 자리에는 받은 것을 적어 두는 가짜를 넣는다.
package main

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

const testID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

// fakeCharges 는 정해 둔 대로 답하는 가짜 자동 충전 서비스다. 받은 것을 적어 둔다.
type fakeCharges struct {
	open       []autocharge.OpenRequest
	err        error
	olderThan  time.Duration
	resolution autocharge.Resolution
}

func (f *fakeCharges) ListOpen(_ context.Context, olderThan time.Duration, _ int) ([]autocharge.OpenRequest, error) {
	f.olderThan = olderThan
	return f.open, f.err
}

func (f *fakeCharges) Resolve(_ context.Context, resolution autocharge.Resolution) error {
	f.resolution = resolution
	return f.err
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
	want := autocharge.Resolution{
		ID: uuid.MustParse(testID), Outcome: autocharge.OutcomePaid, PaymentKey: "tviva123", Reason: "상점관리자에서 완료", DecidedBy: "cli:me",
	}
	for _, args := range [][]string{
		{"decide", testID, "paid", "-payment-key", "tviva123", "-reason", "상점관리자에서 완료"},
		{"-reason", "상점관리자에서 완료", "-payment-key", "tviva123", "decide", testID, "paid"},
	} {
		req, err := parse(args, "cli:me")
		if err != nil || req.action != actionDecide || req.resolution != want {
			t.Errorf("%v: 일 = %+v, %v", args, req, err)
		}
	}
	req, err := parse([]string{"decide", testID, "declined", "-reason", "결제 없음", "-by", "운영자 김"}, "cli:me")
	if err != nil || req.resolution.DecidedBy != "운영자 김" || req.resolution.Outcome != autocharge.OutcomeDeclined || req.resolution.PaymentKey != "" {
		t.Errorf("일 = %+v, %v", req, err)
	}
}

func TestParseRefusesWhatItCannotUse(t *testing.T) {
	cases := map[string][]string{
		"없다":               {},
		"모르는 일":            {"fix"},
		"근거가 없다":           {"decide", testID, "declined"},
		"paid 에 결제 번호가 없다": {"decide", testID, "paid", "-reason", "x"},
		"declined 에 결제 번호": {"decide", testID, "declined", "-payment-key", "tviva", "-reason", "x"},
		"모르는 결과":           {"decide", testID, "refunded", "-reason", "x"},
		"일 번호가 이상하다":       {"decide", "charge-1", "declined", "-reason", "x"},
		"결과가 없다":           {"decide", testID, "-reason", "x"},
		"기간이 0":            {"stuck", "-older-than", "0s"},
		"모르는 옵션":           {"stuck", "-all"},
		"stuck 에 낱말이 더":    {"stuck", testID},
	}
	for name, args := range cases {
		if _, err := parse(args, "cli:me"); err == nil {
			t.Errorf("%s: 오류가 나야 한다", name)
		}
	}
}

func TestDoListsOpenChargesWithWhatToDo(t *testing.T) {
	since := time.Date(2026, 11, 1, 9, 0, 0, 0, time.UTC)
	service := &fakeCharges{open: []autocharge.OpenRequest{
		{ID: uuid.MustParse(testID), Status: "charging", ProductID: "credits-5000", Price: 5000, Attempts: 40,
			LastError: "토스페이먼츠가 답하지 않았습니다", CreatedAt: since, Decidable: true},
		{ID: uuid.New(), Status: "charging", ProductID: "credits-1000", Price: 1000, Attempts: 3, CreatedAt: since},
		{ID: uuid.New(), Status: "pending", ProductID: "credits-1000", Price: 1000, CreatedAt: since},
	}}
	var out bytes.Buffer

	err := do(context.Background(), service, request{action: actionStuck, olderThan: time.Hour}, &out)

	text := out.String()
	if err != nil || service.olderThan != time.Hour {
		t.Fatalf("오류 = %v, 넘긴 기간 = %v", err, service.olderThan)
	}
	for _, want := range []string{testID, "paid 또는 declined", "아직 다시 보낸다", "billing-autocharge", "5000원", "40번 시도", "마지막: 토스페이먼츠가"} {
		if !strings.Contains(text, want) {
			t.Errorf("화면에 %q 가 없다: %s", want, text)
		}
	}
	if strings.Count(text, "\n") != 3 {
		t.Errorf("줄이 셋이어야 한다: %s", text)
	}
}

func TestDoSaysWhenNothingIsOpen(t *testing.T) {
	var out bytes.Buffer

	if err := do(context.Background(), &fakeCharges{}, request{action: actionStuck, olderThan: time.Hour}, &out); err != nil {
		t.Fatalf("오류 = %v", err)
	}

	if !strings.Contains(out.String(), "끝나지 않은 자동 충전이 없습니다") {
		t.Errorf("화면 = %s", out.String())
	}
}

func TestDoPassesTheResolutionAndPrintsIt(t *testing.T) {
	resolution := autocharge.Resolution{ID: uuid.MustParse(testID), Outcome: autocharge.OutcomeDeclined, Reason: "결제 없음", DecidedBy: "cli:me"}
	service := &fakeCharges{}
	var out bytes.Buffer

	err := do(context.Background(), service, request{action: actionDecide, resolution: resolution}, &out)

	if err != nil || service.resolution != resolution || !strings.Contains(out.String(), "정했습니다: "+testID+"  declined") {
		t.Errorf("오류 = %v, 넘긴 결정 = %+v, 화면 = %s", err, service.resolution, out.String())
	}
}

func TestDoReturnsTheServicesError(t *testing.T) {
	service := &fakeCharges{err: autocharge.ErrStillResending}
	var out bytes.Buffer

	err := do(context.Background(), service, request{action: actionDecide}, &out)

	if !errors.Is(err, autocharge.ErrStillResending) || strings.Contains(out.String(), "정했습니다") {
		t.Errorf("오류 = %v, 화면 = %s", err, out.String())
	}
}
