// billing-server/internal/coupon/coupon_test.go

// 쿠폰의 규칙을 DB 없이 본다(#979). 코드의 모양, 받을 수 있는 때, 틀린 시도의 창, 만들 값.
package coupon_test

import (
	"errors"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
)

var now = time.Date(2026, 11, 10, 3, 0, 0, 0, time.UTC)

func TestCodesAreTrimmedAndUppercased(t *testing.T) {
	cases := []struct {
		input string
		code  string
		ok    bool
	}{
		{" launch-2026 ", "LAUNCH-2026", true},
		{"ABCD", "ABCD", true},
		{"ABC", "ABC", false},
		{"쿠폰코드", "쿠폰코드", false},
		{"AB CD", "AB CD", false},
		{"A123456789012345678901234567890123", "A123456789012345678901234567890123", false},
	}
	for _, tc := range cases {
		code, ok := coupon.NormalizeCode(tc.input)
		if code != tc.code || ok != tc.ok {
			t.Fatalf("NormalizeCode(%q) = %q, %v. %q, %v 여야 한다", tc.input, code, ok, tc.code, tc.ok)
		}
	}
}

func TestAvailability(t *testing.T) {
	open := coupon.Coupon{StartsAt: now.Add(-time.Hour), EndsAt: now.Add(time.Hour), MaxRedemptions: 2, Redemptions: 1}
	stopped := now
	cases := []struct {
		name   string
		change func(*coupon.Coupon)
		want   error
	}{
		{"열림", func(*coupon.Coupon) {}, nil},
		{"시작하는 때 바로", func(c *coupon.Coupon) { c.StartsAt = now }, nil},
		{"아직", func(c *coupon.Coupon) { c.StartsAt = now.Add(time.Second) }, coupon.ErrNotStarted},
		{"끝나는 때 바로", func(c *coupon.Coupon) { c.EndsAt = now }, coupon.ErrEnded},
		{"다 참", func(c *coupon.Coupon) { c.Redemptions = 2 }, coupon.ErrExhausted},
		{"한도 없음", func(c *coupon.Coupon) { c.MaxRedemptions, c.Redemptions = 0, 1_000_000 }, nil},
		{"멈춤이 먼저", func(c *coupon.Coupon) { c.StoppedAt, c.EndsAt = &stopped, now }, coupon.ErrStopped},
	}
	for _, tc := range cases {
		c := open
		tc.change(&c)
		if err := coupon.Availability(c, now); !errors.Is(err, tc.want) {
			t.Fatalf("%s: %v, %v 여야 한다", tc.name, err, tc.want)
		}
	}
}

func TestBlockedOnlyWithinTheWindowAfterTooManyFailures(t *testing.T) {
	start := now.Add(-10 * time.Minute)
	cases := []struct {
		name     string
		attempts *coupon.Attempts
		blocked  bool
		wait     time.Duration
	}{
		{"틀린 적 없음", nil, false, 0},
		{"한도 바로 아래", &coupon.Attempts{WindowStartedAt: start, Failures: coupon.MaxFailures - 1}, false, 0},
		{"한도", &coupon.Attempts{WindowStartedAt: start, Failures: coupon.MaxFailures}, true, 50 * time.Minute},
		{"창이 끝남", &coupon.Attempts{WindowStartedAt: now.Add(-coupon.FailureWindow), Failures: 99}, false, 0},
	}
	for _, tc := range cases {
		blocked, wait := coupon.Blocked(tc.attempts, now)
		if blocked != tc.blocked || wait != tc.wait {
			t.Fatalf("%s: %v, %s. %v, %s 여야 한다", tc.name, blocked, wait, tc.blocked, tc.wait)
		}
	}
}

func TestSpecValidation(t *testing.T) {
	good := coupon.Spec{Code: "LAUNCH-2026", Silver: 500, StartsAt: now, EndsAt: now.Add(time.Hour), CreatedBy: "운영자", Reason: "출시"}
	if err := good.Validate(); err != nil {
		t.Fatalf("맞는 값 = %v", err)
	}
	bad := []func(*coupon.Spec){
		func(s *coupon.Spec) { s.Code = "x" },
		func(s *coupon.Spec) { s.Silver = 0 },
		func(s *coupon.Spec) { s.Silver = coupon.MaxSilver + 1 },
		func(s *coupon.Spec) { s.SilverDays = coupon.MaxSilverDays + 1 },
		func(s *coupon.Spec) { s.EndsAt = s.StartsAt },
		func(s *coupon.Spec) { s.MaxRedemptions = -1 },
		func(s *coupon.Spec) { s.CreatedBy = " " },
		func(s *coupon.Spec) { s.Reason = "" },
	}
	for i, change := range bad {
		spec := good
		change(&spec)
		if err := spec.Validate(); !errors.Is(err, coupon.ErrInvalidSpec) {
			t.Fatalf("%d 번째 = %v, ErrInvalidSpec 여야 한다", i, err)
		}
	}
}

func TestGrantKeyAndTTL(t *testing.T) {
	if key := coupon.GrantKey(42); key != "coupon-42" {
		t.Fatalf("GrantKey = %q", key)
	}
	if ttl := (coupon.Coupon{SilverDays: 3}).TTL(); ttl != 72*time.Hour {
		t.Fatalf("TTL = %s", ttl)
	}
	if ttl := (coupon.Coupon{}).TTL(); ttl != 0 {
		t.Fatalf("기본 TTL = %s, 0(지갑의 기본값) 이어야 한다", ttl)
	}
}
