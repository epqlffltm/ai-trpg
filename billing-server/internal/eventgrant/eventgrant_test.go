// billing-server/internal/eventgrant/eventgrant_test.go

// 이름, 명단, 미리 보기, 주기를 DB 없이 시험한다. 지갑의 자리에는 정해 둔 대로 답하는 가짜를 넣는다.
package eventgrant_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eventgrant"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

var (
	alice = uuid.MustParse("aaaaaaaa-0000-4000-8000-000000000001")
	bob   = uuid.MustParse("aaaaaaaa-0000-4000-8000-000000000002")
	carol = uuid.MustParse("aaaaaaaa-0000-4000-8000-000000000003")
)

// fakeWallet 은 정해 둔 대로 답하는 가짜 지갑이다. 받은 것을 적어 둔다.
type fakeWallet struct {
	// already 는 이미 받은 사람, broken 은 주다가 오류가 나는 사람이다.
	already map[uuid.UUID]bool
	broken  map[uuid.UUID]bool
	// given 은 이번에 준 사람과 그때의 양, 이름이다.
	given  []uuid.UUID
	amount credit.Amount
	key    string
	// granted, wallets 는 세는 쪽의 답이다.
	granted, wallets int
	counted          []uuid.UUID
}

func (f *fakeWallet) GrantFreeOnce(_ context.Context, user uuid.UUID, amount credit.Amount, key string) (wallet.Grant, error) {
	if f.broken[user] {
		return wallet.Grant{}, errors.New("DB 가 답하지 않는다")
	}
	if f.already[user] {
		return wallet.Grant{}, wallet.ErrAlreadyGranted
	}
	f.given, f.amount, f.key = append(f.given, user), amount, key
	return wallet.Grant{Amount: amount}, nil
}

func (f *fakeWallet) CountGranted(_ context.Context, key string, users []uuid.UUID) (int, error) {
	f.key, f.counted = key, users
	return f.granted, nil
}

func (f *fakeWallet) CountWallets(_ context.Context, _ []uuid.UUID) (int, error) {
	return f.wallets, nil
}

// aPlan 은 셋에게 100 실버를 주는 지급이다.
func aPlan(t *testing.T) eventgrant.Plan {
	t.Helper()
	key, err := eventgrant.Key("launch-2026")
	if err != nil {
		t.Fatalf("이름을 만들지 못했다: %v", err)
	}
	return eventgrant.Plan{Key: key, Silver: 100, Users: []uuid.UUID{alice, bob, carol}, Reason: "출시 기념", By: "cli:me"}
}

// captureLogs 는 테스트 동안 기본 로거를 버퍼에 적는 것으로 바꾸고, 남긴 줄들을 읽는 함수를 돌려준다.
func captureLogs(t *testing.T) func() []map[string]any {
	t.Helper()
	var out bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&out, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })
	return func() []map[string]any {
		var lines []map[string]any
		for _, text := range strings.Split(strings.TrimSpace(out.String()), "\n") {
			var line map[string]any
			if err := json.Unmarshal([]byte(text), &line); err != nil {
				t.Fatalf("JSON 이 아닌 줄: %q", text)
			}
			lines = append(lines, line)
		}
		return lines
	}
}

func TestTheKeyIsAlwaysAnEventKey(t *testing.T) {
	key, err := eventgrant.Key("launch-2026")
	if err != nil || key != "event-launch-2026" {
		t.Errorf("이름 = %q, %v", key, err)
	}
	// 서버가 쓰는 이름과 겹칠 수 없다. "welcome" 을 적어도 "event-welcome" 이다
	if key, _ := eventgrant.Key("welcome"); key != "event-welcome" {
		t.Errorf("이름 = %q", key)
	}
	for _, name := range []string{"", "Launch", "출시", "a b", "a:b", strings.Repeat("a", 59)} {
		if _, err := eventgrant.Key(name); !errors.Is(err, eventgrant.ErrInvalidName) {
			t.Errorf("%q: %v. ErrInvalidName 이어야 한다", name, err)
		}
	}
	// 58자면 앞머리를 붙여 지급 이름의 64자다
	if key, err := eventgrant.Key(strings.Repeat("a", 58)); err != nil || len(key) != 64 {
		t.Errorf("이름 = %q, %v", key, err)
	}
}

func TestThePlanIsChecked(t *testing.T) {
	cases := map[string]struct {
		change func(p *eventgrant.Plan)
		want   error
	}{
		"앞머리가 없는 이름": {func(p *eventgrant.Plan) { p.Key = "welcome" }, eventgrant.ErrInvalidName},
		"앞머리만 있는 이름": {func(p *eventgrant.Plan) { p.Key = "event-" }, eventgrant.ErrInvalidName},
		"0 실버":       {func(p *eventgrant.Plan) { p.Silver = 0 }, eventgrant.ErrInvalidSilver},
		"상한을 넘는 실버":  {func(p *eventgrant.Plan) { p.Silver = eventgrant.MaxSilver + 1 }, eventgrant.ErrInvalidSilver},
		"빈 명단":       {func(p *eventgrant.Plan) { p.Users = nil }, eventgrant.ErrEmptyRoster},
		"이유가 없다":     {func(p *eventgrant.Plan) { p.Reason = "" }, eventgrant.ErrNoReason},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			plan := aPlan(t)
			tc.change(&plan)
			fake := &fakeWallet{}

			_, err := eventgrant.Give(context.Background(), fake, plan, func(eventgrant.Result) {})

			// 틀린 지급은 아무에게도 주지 않는다
			if !errors.Is(err, tc.want) || len(fake.given) != 0 {
				t.Errorf("오류 = %v, 준 사람 = %v", err, fake.given)
			}
		})
	}
	if err := aPlan(t).Check(); err != nil {
		t.Errorf("맞는 지급이 거절되었다: %v", err)
	}
}

func TestReadRosterSkipsCommentsAndCountsDuplicates(t *testing.T) {
	text := "# 출시 기념 대상\n\n" + alice.String() + "\n  " + bob.String() + "  \n" + alice.String() + "\n" +
		strings.ToUpper(carol.String()) + "\n"

	roster, err := eventgrant.ReadRoster(strings.NewReader(text))

	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	// 적힌 차례대로, 겹친 번호는 처음 것만 남는다. 대문자로 적어도 같은 번호다
	want := []uuid.UUID{alice, bob, carol}
	if len(roster.Users) != len(want) || roster.Duplicates != 1 {
		t.Fatalf("명단 = %+v", roster)
	}
	for i := range want {
		if roster.Users[i] != want[i] {
			t.Errorf("%d째 = %s, 기대 = %s", i, roster.Users[i], want[i])
		}
	}
}

func TestReadRosterRefusesALineThatIsNotAUserID(t *testing.T) {
	for _, bad := range []string{"alice", "{" + bob.String() + "}", "urn:uuid:" + bob.String(), strings.ReplaceAll(bob.String(), "-", "")} {
		text := alice.String() + "\n# 설명\n" + bad + "\n" + carol.String() + "\n"

		_, err := eventgrant.ReadRoster(strings.NewReader(text))

		// 몇째 줄인지 알려 준다. 일부만 읽고 돌려주지 않는다
		if err == nil || !strings.HasPrefix(err.Error(), "3째 줄") {
			t.Errorf("%q: 오류 = %v", bad, err)
		}
	}
}

func TestReadRosterRefusesAnEmptyRoster(t *testing.T) {
	_, err := eventgrant.ReadRoster(strings.NewReader("# 아무도 없다\n\n"))

	if !errors.Is(err, eventgrant.ErrEmptyRoster) {
		t.Errorf("오류 = %v", err)
	}
}

func TestLookCountsWithoutGiving(t *testing.T) {
	plan := aPlan(t)
	fake := &fakeWallet{granted: 1, wallets: 2}

	preview, err := eventgrant.Look(context.Background(), fake, plan)

	if err != nil || preview != (eventgrant.Preview{Listed: 3, Granted: 1, NoWallet: 1}) {
		t.Fatalf("미리 보기 = %+v, %v", preview, err)
	}
	if preview.ToGive() != 2 || preview.Total(plan.Silver) != 200 || fake.key != plan.Key || len(fake.given) != 0 {
		t.Errorf("줄 사람 = %d, 합 = %s, 센 이름 = %q, 준 사람 = %v", preview.ToGive(), preview.Total(plan.Silver), fake.key, fake.given)
	}
}

func TestGiveSkipsThoseWhoAlreadyHaveIt(t *testing.T) {
	logs := captureLogs(t)
	plan := aPlan(t)
	fake := &fakeWallet{already: map[uuid.UUID]bool{bob: true}}
	var seen []eventgrant.Result

	result, err := eventgrant.Give(context.Background(), fake, plan, func(r eventgrant.Result) { seen = append(seen, r) })

	if err != nil || result != (eventgrant.Result{Given: 2, Already: 1}) {
		t.Fatalf("결과 = %+v, %v", result, err)
	}
	if len(fake.given) != 2 || fake.given[0] != alice || fake.given[1] != carol || fake.amount != 100 || fake.key != "event-launch-2026" {
		t.Errorf("준 것 = %v, %s, %q", fake.given, fake.amount, fake.key)
	}
	// 사람 하나마다 진행을 알린다
	if len(seen) != 3 || seen[2].Done() != 3 {
		t.Errorf("진행 = %+v", seen)
	}
	// 누가 왜 몇 명에게 얼마를 줬는지 남긴다. 사용자 번호는 싣지 않는다
	lines := logs()
	if len(lines) != 1 || lines[0]["operation"] != "grant.event" || lines[0]["grant_key"] != "event-launch-2026" ||
		lines[0]["silver"] != "100" || lines[0]["given"] != 2.0 || lines[0]["already"] != 1.0 || lines[0]["listed"] != 3.0 ||
		lines[0]["granted_by"] != "cli:me" || lines[0]["reason"] != "출시 기념" || lines[0]["level"] != "INFO" {
		t.Errorf("로그 = %v", lines)
	}
	if text, _ := json.Marshal(lines); strings.Contains(string(text), alice.String()) {
		t.Errorf("로그에 사용자 번호가 있다: %s", text)
	}
}

func TestGiveStopsAtTheFirstFailure(t *testing.T) {
	logs := captureLogs(t)
	fake := &fakeWallet{broken: map[uuid.UUID]bool{bob: true}}

	result, err := eventgrant.Give(context.Background(), fake, aPlan(t), func(eventgrant.Result) {})

	// 앞사람에게 준 것은 그대로다. 뒷사람에게는 가지 않는다. 다시 돌리면 앞사람은 건너뛴다
	if err == nil || !strings.Contains(err.Error(), bob.String()) || result != (eventgrant.Result{Given: 1}) {
		t.Errorf("결과 = %+v, %v", result, err)
	}
	if len(fake.given) != 1 || fake.given[0] != alice {
		t.Errorf("준 사람 = %v", fake.given)
	}
	lines := logs()
	if len(lines) != 1 || lines[0]["level"] != "WARN" || lines[0]["given"] != 1.0 || lines[0]["error"] == nil {
		t.Errorf("로그 = %v", lines)
	}
}

func TestGiveStopsWhenAskedTo(t *testing.T) {
	captureLogs(t)
	fake := &fakeWallet{}
	ctx, cancel := context.WithCancel(context.Background())

	// 첫 사람을 준 뒤에 끄라는 신호(Ctrl+C)가 왔다
	result, err := eventgrant.Give(ctx, fake, aPlan(t), func(eventgrant.Result) { cancel() })

	if !errors.Is(err, context.Canceled) || result != (eventgrant.Result{Given: 1}) || len(fake.given) != 1 {
		t.Errorf("결과 = %+v, %v, 준 사람 = %v", result, err, fake.given)
	}
}
