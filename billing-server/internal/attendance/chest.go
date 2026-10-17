// billing-server/internal/attendance/chest.go

package attendance

import (
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
)

// 보물 상자의 확률표. 주기의 마지막 날(7일째)에 연다.
//
// 확률은 공개한다(사용자 결정, 2026-10-18). 무료로만 얻는 상자라 법의 공개 의무(게임산업법, 2024-03-22)는 없지만,
// 믿고 쓰게 하려고 스스로 공개한다. 공개하는 주소는 GET /attendance/rewards 다.
//
// 표는 설정(환경 변수)이 아니라 코드에 둔다. 확률을 바꾸는 일은 공지를 먼저 하고 PR 로 고친다.
// 바꿀 때는 표를 고치지 않고 버전을 올린 새 표를 만들어 CurrentChest 를 바꾼다. 연 상자마다 표의 버전을 적어 두므로,
// 옛 표로 연 상자의 결과도 그 표로 설명할 수 있다.
// 결과의 이름은 D&D SRD 5.1 에 있는 것에서 땄다(미믹, 고블린). 고유한 괴물(비홀더 등)과 상표는 쓰지 않는다.

// ChanceScale 은 확률의 단위다. 만분율이다. 1000 은 10%, 1 은 0.01% 다.
// 소수(float)를 쓰지 않는다. 더하면 정확히 ChanceScale 이 되는지를 틀림없이 볼 수 있다.
const ChanceScale = 10_000

// Outcome 은 보물 상자에서 나올 수 있는 결과 하나다.
type Outcome struct {
	// ID 는 결과의 이름이다. 기록(attendance_claims.chest_outcome)과 응답에 그대로 나간다. 한번 정하면 바꾸지 않는다.
	ID string
	// Name 은 화면에 보이는 이름이다.
	Name string
	// Silver 는 받는 실버다. 0 이면 꽝이다.
	Silver credit.Amount
	// Chance 는 나올 확률이다(만분율, ChanceScale).
	Chance int
}

// ChestTable 은 버전이 붙은 확률표다.
type ChestTable struct {
	// Version 은 표의 버전이다. 기록(attendance_claims.chest_table)에 그대로 적힌다.
	Version string
	// Outcomes 는 결과들이다. 이 순서로 화면에 보인다. 확률을 모두 더하면 ChanceScale 이다.
	Outcomes []Outcome
}

// ChestV1 은 첫 확률표다(2026-10-18). 평균 617 실버다.
var ChestV1 = ChestTable{
	Version: "v1",
	Outcomes: []Outcome{
		{ID: "mimic_bite", Name: "미믹 — 물렸다", Silver: 0, Chance: 1_000},
		{ID: "mimic_teeth", Name: "미믹 — 이빨 사이의 동전", Silver: 100, Chance: 2_000},
		{ID: "goblin_pouch", Name: "고블린의 주머니", Silver: 300, Chance: 3_000},
		{ID: "adventurer_pack", Name: "모험가의 배낭", Silver: 600, Chance: 2_200},
		{ID: "treasure_hoard", Name: "보물 더미", Silver: 1_500, Chance: 1_500},
		{ID: "dragon_hoard", Name: "용의 보물", Silver: 5_000, Chance: 300},
	},
}

// CurrentChest 는 지금 여는 상자의 표다.
var CurrentChest = ChestV1

// ErrInvalidChest 는 확률표가 틀렸다는 오류다. 서버가 뜰 때 걸러진다.
var ErrInvalidChest = errors.New("보물 상자의 확률표가 틀렸습니다")

// Validate 는 표가 맞는지 본다. 버전과 결과가 있어야 하고, 이름이 겹치지 않아야 하고,
// 확률은 1 이상이고 모두 더하면 ChanceScale 이어야 하고, 실버는 0 이상이어야 한다.
func (t ChestTable) Validate() error {
	if t.Version == "" || len(t.Outcomes) == 0 {
		return fmt.Errorf("%w: 버전과 결과가 있어야 합니다", ErrInvalidChest)
	}
	seen := make(map[string]bool, len(t.Outcomes))
	total := 0
	for _, outcome := range t.Outcomes {
		if outcome.ID == "" || seen[outcome.ID] {
			return fmt.Errorf("%w: 결과의 이름이 비었거나 겹칩니다(%q)", ErrInvalidChest, outcome.ID)
		}
		if outcome.Chance < 1 || outcome.Silver < 0 {
			return fmt.Errorf("%w: %s 의 확률은 1 이상, 실버는 0 이상이어야 합니다", ErrInvalidChest, outcome.ID)
		}
		seen[outcome.ID] = true
		total += outcome.Chance
	}
	if total != ChanceScale {
		return fmt.Errorf("%w: 확률을 더하면 %d 이어야 하는데 %d 입니다", ErrInvalidChest, ChanceScale, total)
	}
	return nil
}

// Pick 은 0 이상 ChanceScale 미만의 수 n 에 해당하는 결과를 고른다. 앞의 결과부터 확률만큼 구간을 차지한다.
// 표가 맞다면(Validate) 늘 하나를 고른다.
func (t ChestTable) Pick(n int) Outcome {
	for _, outcome := range t.Outcomes {
		if n < outcome.Chance {
			return outcome
		}
		n -= outcome.Chance
	}
	// 표가 틀렸거나 n 이 범위 밖이다. 마지막 것을 주지 않고 가장 앞의 것(꽝 쪽)을 준다
	return t.Outcomes[0]
}

// ExpectedSilver 는 상자 하나에서 받는 실버의 평균이다(내림). 화면에 함께 보인다.
func (t ChestTable) ExpectedSilver() credit.Amount {
	var sum credit.Amount
	for _, outcome := range t.Outcomes {
		sum += outcome.Silver * credit.Amount(outcome.Chance)
	}
	return sum / ChanceScale
}

// Roll 은 0 이상 ChanceScale 미만의 수 하나를 고른다. 운영체제의 난수(crypto/rand)를 쓴다.
// 다음 결과를 앞의 결과로 미루어 맞힐 수 없다.
type Roll func() (int, error)

// CryptoRoll 은 crypto/rand 로 고르는 Roll 이다.
func CryptoRoll() (int, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(ChanceScale))
	if err != nil {
		return 0, err
	}
	return int(n.Int64()), nil
}
