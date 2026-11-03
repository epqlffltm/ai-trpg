// billing-server/cmd/coupons/main_test.go

// 명령 줄을 읽는 것과 찍는 것을 DB 없이 확인한다(#979). 쿠폰의 자리에는 받은 것을 적어 두는 가짜를 넣는다.
package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
)

// fakeCoupons 는 정해 둔 대로 답하는 가짜 쿠폰이다. 만들려던 값과 멈추려던 코드를 적어 둔다.
type fakeCoupons struct {
	created coupon.Spec
	stopped string
	listed  []coupon.Coupon
	err     error
}

func (f *fakeCoupons) Create(_ context.Context, spec coupon.Spec) (coupon.Coupon, error) {
	f.created = spec
	code, _ := coupon.NormalizeCode(spec.Code)
	return coupon.Coupon{
		Code: code, Silver: spec.Silver, StartsAt: spec.StartsAt, EndsAt: spec.EndsAt,
		MaxRedemptions: spec.MaxRedemptions, SilverDays: spec.SilverDays, CreatedBy: spec.CreatedBy, Reason: spec.Reason,
	}, f.err
}

func (f *fakeCoupons) List(context.Context, int) ([]coupon.Coupon, error) { return f.listed, f.err }

func (f *fakeCoupons) Stop(_ context.Context, code string) error {
	f.stopped = code
	return f.err
}

// quietLogs 는 테스트 동안 운영자의 기록(로그)을 버린다.
func quietLogs(t *testing.T) {
	t.Helper()
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(io.Discard, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })
}

func TestCreateReadsTheKoreanDays(t *testing.T) {
	cmd, err := parse([]string{
		"create", "-code", "launch-2026", "-silver", "500", "-from", "2026-11-10", "-until", "2026-11-30",
		"-max", "100", "-days", "14", "-reason", "출시 기념",
	}, "cli:me")
	if err != nil {
		t.Fatal(err)
	}

	want := coupon.Spec{
		Code: "launch-2026", Silver: 500, SilverDays: 14, MaxRedemptions: 100, CreatedBy: "cli:me", Reason: "출시 기념",
		StartsAt: time.Date(2026, 11, 9, 15, 0, 0, 0, time.UTC), EndsAt: time.Date(2026, 11, 30, 15, 0, 0, 0, time.UTC),
	}
	if !cmd.spec.StartsAt.Equal(want.StartsAt) || !cmd.spec.EndsAt.Equal(want.EndsAt) {
		t.Fatalf("때 = %s ~ %s. 한국의 11-10 0시부터 12-01 0시 전까지여야 한다", cmd.spec.StartsAt.UTC(), cmd.spec.EndsAt.UTC())
	}
	cmd.spec.StartsAt, cmd.spec.EndsAt = want.StartsAt, want.EndsAt
	if cmd.action != "create" || cmd.spec != want {
		t.Fatalf("읽은 것 = %+v", cmd)
	}
}

func TestParseRejectsWrongCommands(t *testing.T) {
	bad := [][]string{
		{},
		{"give"},
		{"create", "-from", "11/10", "-until", "2026-11-30"},
		{"create", "-from", "2026-11-10", "-until", "nope"},
		{"list", "-limit", "0"},
		{"list", "extra"},
		{"stop"},
		{"stop", "A", "B"},
	}
	for _, args := range bad {
		if _, err := parse(args, "cli"); err == nil {
			t.Errorf("%v 를 받았다. 틀린 명령이다", args)
		}
	}
}

func TestCreatePrintsTheCouponAndStopNamesIt(t *testing.T) {
	quietLogs(t)
	service := &fakeCoupons{}
	cmd, err := parse([]string{"create", "-code", "launch", "-silver", "300", "-from", "2026-11-10", "-until", "2026-11-30", "-reason", "출시"}, "cli")
	if err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer

	if err := do(context.Background(), service, cmd, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), "LAUNCH · 실버 300(기본 기한) · 2026-11-10 ~ 2026-11-30 · 받은 사람 0명(한도 없음) · 열림") {
		t.Fatalf("찍은 것 = %s", out.String())
	}

	out.Reset()
	if err := do(context.Background(), service, command{action: "stop", code: "launch"}, &out); err != nil {
		t.Fatal(err)
	}
	if service.stopped != "launch" || !strings.Contains(out.String(), "멈췄습니다: LAUNCH") {
		t.Fatalf("멈춤 = %q, %s", service.stopped, out.String())
	}
}

func TestStoppingAnUnknownCodeFails(t *testing.T) {
	quietLogs(t)
	service := &fakeCoupons{err: coupon.ErrNotFound}

	err := do(context.Background(), service, command{action: "stop", code: "NOPE"}, io.Discard)

	if !errors.Is(err, coupon.ErrNotFound) {
		t.Fatalf("없는 코드 = %v", err)
	}
}
