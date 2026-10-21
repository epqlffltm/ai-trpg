// billing-server/internal/eventgrant/plan.go

// Package eventgrant 는 운영자가 명단의 사용자들에게 이벤트 실버(무료 크레딧)를 한 번씩 주는 일이다(cmd/grants).
//
// 기념일 이벤트, 장애 보상, 당첨자 지급처럼 정해진 사람들에게 같은 양을 준다. 지급마다 이름(이벤트 이름)이 있고,
// 한 사람은 같은 이름의 지급을 한 번만 받는다. 지갑의 한 번만 주는 지급(wallet.GrantFreeOnce)을 그대로 쓴다.
// 그래서 같은 명단으로 몇 번을 다시 돌려도, 중간에 끊긴 것을 다시 돌려도 두 번 받는 사람이 없다.
//
// 이름은 늘 "event-" 로 시작한다. 서버가 쓰는 이름(환영 크레딧 "welcome", 출석 "attendance-날짜")과 겹치면
// 이벤트로 준 것 때문에 그 사람이 환영 크레딧이나 출석을 받지 못한다. 운영자가 고르는 이름이 그 자리에 닿지 않게 한다.
//
// 이 패키지는 사용자가 있는지 모른다. 사용자는 인증 서버의 것이다. 명단의 번호를 그대로 믿는다.
// 그래서 주기 전에 지갑이 없는 사람이 몇인지 보여 준다(Preview). 처음 보는 번호가 많으면 명단이 틀렸을 수 있다.
package eventgrant

import (
	"errors"
	"regexp"
	"strings"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// KeyPrefix 는 이벤트 지급의 이름 앞에 늘 붙는 말이다.
const KeyPrefix = "event-"

// MaxSilver 는 한 사람에게 한 번에 주는 가장 큰 양이다. 환영 크레딧의 상한(config.MaxWelcomeCredits)과 같다.
// 0 을 몇 개 더 붙인 실수를 막는다.
const MaxSilver credit.Amount = 1_000_000

var (
	// ErrInvalidName 은 이벤트 이름이 받는 모양이 아니라는 오류다.
	ErrInvalidName = errors.New("이벤트 이름은 영문 소문자, 숫자, 밑줄, 붙임표로 된 1자에서 58자여야 합니다")
	// ErrInvalidSilver 는 주는 양이 받는 범위 밖이라는 오류다.
	ErrInvalidSilver = errors.New("실버는 1 부터 1000000 까지여야 합니다")
	// ErrNoReason 은 주는 이유를 적지 않았다는 오류다.
	ErrNoReason = errors.New("주는 이유를 적어야 합니다")
)

// namePattern 은 이벤트 이름으로 받는 모양이다. 앞에 KeyPrefix 를 붙여도 지급 이름의 64자(wallet)를 넘지 않는다.
var namePattern = regexp.MustCompile(`^[a-z0-9_-]{1,58}$`)

// Plan 은 한 번의 지급이다. 명단의 사람마다 Silver 를 Key 의 이름으로 준다.
type Plan struct {
	// Key 는 지급의 이름이다(KeyPrefix + 이벤트 이름). Key 로 만든다.
	Key string
	// Silver 는 한 사람에게 주는 양이다.
	Silver credit.Amount
	// Users 는 줄 사람들이다. 같은 번호가 두 번 없다(ReadRoster).
	Users []uuid.UUID
	// Reason 은 주는 이유, By 는 준 사람이다. 로그(grant.event)에 남는다.
	Reason string
	By     string
}

// Key 는 이벤트 이름으로 지급의 이름을 만든다. 이름이 받는 모양이 아니면 ErrInvalidName 이다.
func Key(name string) (string, error) {
	if !namePattern.MatchString(name) {
		return "", ErrInvalidName
	}
	return KeyPrefix + name, nil
}

// CheckSilver 는 한 사람에게 주는 양이 받는 범위 안인지 본다.
func CheckSilver(silver credit.Amount) error {
	if silver <= 0 || silver > MaxSilver {
		return ErrInvalidSilver
	}
	return nil
}

// Check 는 지급을 시작해도 되는지 본다. 이름, 양, 명단, 이유를 본다.
func (p Plan) Check() error {
	if name, ok := strings.CutPrefix(p.Key, KeyPrefix); !ok || !namePattern.MatchString(name) {
		return ErrInvalidName
	}
	if err := CheckSilver(p.Silver); err != nil {
		return err
	}
	if len(p.Users) == 0 {
		return ErrEmptyRoster
	}
	if p.Reason == "" {
		return ErrNoReason
	}
	return nil
}
