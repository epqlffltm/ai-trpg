// billing-server/internal/eventgrant/roster.go

package eventgrant

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/google/uuid"
)

// MaxRoster 는 한 명단에 적을 수 있는 가장 많은 사람이다. 잘못 고른 큰 파일을 끝까지 읽지 않는다.
const MaxRoster = 1_000_000

var (
	// ErrEmptyRoster 는 명단에 사람이 하나도 없다는 오류다.
	ErrEmptyRoster = errors.New("명단에 사용자 번호가 하나도 없습니다")
	// ErrRosterTooLong 은 명단이 MaxRoster 보다 길다는 오류다.
	ErrRosterTooLong = errors.New("명단은 1000000명까지입니다. 나눠서 줍니다")
)

// Roster 는 읽은 명단이다.
type Roster struct {
	// Users 는 적힌 차례대로의 사용자 번호다. 같은 번호는 처음 것만 남긴다.
	Users []uuid.UUID
	// Duplicates 는 앞서 적힌 번호가 다시 나온 줄의 수다. 받는 사람은 한 번만 센다.
	Duplicates int
}

// ReadRoster 는 명단을 읽는다. 한 줄에 사용자 번호 하나다. 빈 줄과 '#' 로 시작하는 줄은 건너뛴다. 앞뒤의 빈칸은 버린다.
// 번호가 아닌 줄이 하나라도 있으면 몇째 줄인지 적은 오류다. 명단의 일부만 주고 멈추는 일이 없게 다 읽은 뒤에야 돌려준다.
func ReadRoster(r io.Reader) (Roster, error) {
	roster := Roster{}
	seen := map[uuid.UUID]bool{}
	scanner := bufio.NewScanner(r)
	for line := 1; scanner.Scan(); line++ {
		text := strings.TrimSpace(scanner.Text())
		if text == "" || strings.HasPrefix(text, "#") {
			continue
		}
		user, err := readUser(text)
		if err != nil {
			return Roster{}, fmt.Errorf("%d째 줄: %w", line, err)
		}
		if seen[user] {
			roster.Duplicates++
			continue
		}
		if len(roster.Users) == MaxRoster {
			return Roster{}, ErrRosterTooLong
		}
		seen[user] = true
		roster.Users = append(roster.Users, user)
	}
	if err := scanner.Err(); err != nil {
		return Roster{}, err
	}
	if len(roster.Users) == 0 {
		return Roster{}, ErrEmptyRoster
	}
	return roster, nil
}

// readUser 는 한 줄의 사용자 번호를 읽는다. 하이픈이 있는 36자 모양만 받는다.
// uuid.Parse 는 중괄호나 "urn:uuid:" 가 붙은 모양, 하이픈이 없는 모양도 받는다. 읽은 번호를 다시 적은 것과 같아야 받는다.
func readUser(text string) (uuid.UUID, error) {
	user, err := uuid.Parse(text)
	if err != nil || user.String() != strings.ToLower(text) {
		return uuid.UUID{}, fmt.Errorf("사용자 번호(aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee 모양)가 아닙니다: %q", text)
	}
	return user, nil
}
