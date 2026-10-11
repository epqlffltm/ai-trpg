// billing-server/internal/credit/amount_internal_test.go

// Scale 을 바꿨을 때의 규칙을 미리 확인한다. Scale 은 상수라 밖에서는 다른 값으로 시험할 수 없다.
// 그래서 자릿수를 인자로 받는 안쪽 함수(format, parse)를 직접 부른다.
package credit

import (
	"errors"
	"math"
	"testing"
)

func TestFormatAtEveryScale(t *testing.T) {
	cases := []struct {
		units int64
		scale int
		want  string
	}{
		{0, 0, "0"},
		{120, 0, "120"},
		{-45, 0, "-45"},
		{math.MaxInt64, 0, "9223372036854775807"},
		{math.MinInt64, 0, "-9223372036854775808"},
		{0, 4, "0.0000"},
		{5, 4, "0.0005"},
		{-5, 4, "-0.0005"},
		{10000, 4, "1.0000"},
		{123456, 4, "12.3456"},
		{123400, 4, "12.3400"},
		{-123456, 4, "-12.3456"},
		{math.MaxInt64, 4, "922337203685477.5807"},
		{math.MinInt64, 4, "-922337203685477.5808"},
		{7, 1, "0.7"},
	}
	for _, tc := range cases {
		if got := format(tc.units, tc.scale); got != tc.want {
			t.Errorf("format(%d, %d) = %q, 기대 = %q", tc.units, tc.scale, got, tc.want)
		}
	}
}

func TestParseAtEveryScale(t *testing.T) {
	cases := []struct {
		text  string
		scale int
		want  int64
	}{
		{"0", 0, 0},
		{"120", 0, 120},
		{"-45", 0, -45},
		{"007", 0, 7},
		{"9223372036854775807", 0, math.MaxInt64},
		{"-9223372036854775808", 0, math.MinInt64},
		{"12.3456", 4, 123456},
		{"12.34", 4, 123400},
		{"12", 4, 120000},
		{"0.0005", 4, 5},
		{"-0.0005", 4, -5},
		{"922337203685477.5807", 4, math.MaxInt64},
	}
	for _, tc := range cases {
		got, err := parse(tc.text, tc.scale)
		if err != nil || got != tc.want {
			t.Errorf("parse(%q, %d) = %d, %v, 기대 = %d", tc.text, tc.scale, got, err, tc.want)
		}
	}
}

func TestParseRejectsWhatIsNotAnAmount(t *testing.T) {
	cases := []struct {
		name  string
		text  string
		scale int
	}{
		{"빈 글자", "", 0},
		{"빼기표만", "-", 0},
		{"더하기표", "+5", 0},
		{"빈칸", " 5", 0},
		{"뒤의 빈칸", "5 ", 0},
		{"글자", "five", 0},
		{"지수", "1e3", 0},
		{"쉼표", "1,000", 0},
		{"정수 단위에 소수점", "1.5", 0},
		{"정수 단위에 점만", "1.", 0},
		{"자릿수가 넘친다", "1.23456", 4},
		{"정수 부분이 없다", ".5", 4},
		{"소수 부분이 없다", "5.", 4},
		{"점이 둘", "1.2.3", 4},
		{"소수 부분에 빼기표", "1.-5", 4},
		{"빼기표가 둘", "--5", 0},
		{"전각 숫자", "１２", 0},
		{"너무 크다", "9223372036854775808", 0},
		{"너무 작다", "-9223372036854775809", 0},
		{"자리를 채우면 넘친다", "922337203685477.5808", 4},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := parse(tc.text, tc.scale)
			if !errors.Is(err, ErrInvalidAmount) {
				t.Errorf("parse(%q, %d) = %d, %v. ErrInvalidAmount 이어야 한다", tc.text, tc.scale, got, err)
			}
		})
	}
}

func TestParseReadsBackWhatFormatWrote(t *testing.T) {
	for _, scale := range []int{0, 1, 4, 8} {
		for _, units := range []int64{0, 1, -1, 99, 10000, -123456, math.MaxInt64, math.MinInt64} {
			text := format(units, scale)
			got, err := parse(text, scale)
			if err != nil || got != units {
				t.Errorf("scale %d: %d -> %q -> %d, %v", scale, units, text, got, err)
			}
		}
	}
}
