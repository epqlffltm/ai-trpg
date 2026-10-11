// billing-server/internal/credit/amount.go

// Package credit 는 크레딧의 양을 나타내는 타입과, 그것을 글자로 바꾸고 읽는 규칙을 둔다.
//
// 양은 "가장 작은 단위가 몇 개인가"를 정수로 들고 있다. 소수를 쓰지 않는다. 소수(float)는
// 0.1 + 0.2 가 0.3 이 되지 않아서 돈과 닮은 값에 쓰지 않는다.
//
// 지금은 가장 작은 단위가 1 크레딧이다(Scale = 0). 나중에 소수 크레딧이 필요해지면 바꿀 곳은 둘이다.
//  1. Scale 을 올린다. 4 로 올리면 1 크레딧이 가장 작은 단위 10000 개가 되고, "12.3456" 을 적을 수 있다.
//  2. 마이그레이션 하나로 이미 저장된 양에 10^Scale 을 곱한다.
//
// DB 의 칸(BIGINT)과 API 의 모양(글자)은 그대로다. 그래서 API 는 처음부터 양을 숫자가 아니라 글자로 준다.
// 숫자로 주면 소수가 생기는 날 클라이언트가 float 로 읽어 값이 틀어진다.
package credit

import (
	"errors"
	"strconv"
	"strings"
)

// Scale 은 소수점 아래로 몇 자리까지 쓰는지다. 0 이면 정수 크레딧이다.
const Scale = 0

// ErrInvalidAmount 는 글자를 양으로 읽지 못했다는 오류다.
var ErrInvalidAmount = errors.New("크레딧의 양이 아닙니다")

// Amount 는 크레딧의 양이다. 가장 작은 단위의 개수를 들고 있다. 줄어든 양은 음수다.
// int64 와 섞어 쓰지 못하게 타입을 따로 둔다. 양이 아닌 숫자(번호, 개수)와 바뀌면 컴파일이 막는다.
type Amount int64

// String 은 양을 사람이 읽는 글자로 바꾼다. Scale 이 0 이면 "120", 4 면 "0.0120" 이다.
func (a Amount) String() string {
	return format(int64(a), Scale)
}

// MarshalJSON 은 양을 JSON 의 글자로 내보낸다. 숫자로 내보내지 않는다(패키지 설명 참고).
func (a Amount) MarshalJSON() ([]byte, error) {
	return []byte(strconv.Quote(a.String())), nil
}

// Parse 는 글자를 양으로 읽는다. String 이 만든 글자는 그대로 다시 읽힌다.
func Parse(text string) (Amount, error) {
	units, err := parse(text, Scale)
	return Amount(units), err
}

// format 은 가장 작은 단위의 개수를 소수점 아래 scale 자리의 글자로 바꾼다.
// 자릿수는 항상 scale 개를 채운다("12.3400"). 같은 양이 한 가지 글자로만 적힌다.
func format(units int64, scale int) string {
	digits := strconv.FormatInt(units, 10)
	if scale == 0 {
		return digits
	}
	sign := ""
	if strings.HasPrefix(digits, "-") {
		sign, digits = "-", digits[1:]
	}
	// 정수 부분에 적어도 한 자리가 남도록 앞을 0 으로 채운다(5 -> "00005" -> "0.0005")
	if len(digits) <= scale {
		digits = strings.Repeat("0", scale-len(digits)+1) + digits
	}
	split := len(digits) - scale
	return sign + digits[:split] + "." + digits[split:]
}

// parse 는 소수점 아래 scale 자리까지의 글자를 가장 작은 단위의 개수로 읽는다.
// 숫자와 맨 앞의 빼기표, 소수점 하나만 받는다. 더하기표, 빈칸, 지수(1e3)는 받지 않는다.
func parse(text string, scale int) (int64, error) {
	sign, rest := "", text
	if strings.HasPrefix(rest, "-") {
		sign, rest = "-", rest[1:]
	}
	whole, fraction, hasPoint := strings.Cut(rest, ".")
	if !isDigits(whole) || (hasPoint && !isDigits(fraction)) || len(fraction) > scale {
		return 0, ErrInvalidAmount
	}
	// 소수점을 지우고 모자란 자리를 0 으로 채우면 가장 작은 단위의 개수가 된다("12.3" -> "123000")
	digits := whole + fraction + strings.Repeat("0", scale-len(fraction))
	// int64 에 담기지 않는 큰 값은 여기서 오류가 된다
	units, err := strconv.ParseInt(sign+digits, 10, 64)
	if err != nil {
		return 0, ErrInvalidAmount
	}
	return units, nil
}

// isDigits 는 글자가 0 부터 9 까지로만 되어 있고 비어 있지 않은지 본다.
func isDigits(text string) bool {
	if text == "" {
		return false
	}
	for _, r := range text {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}
