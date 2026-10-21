// billing-server/cmd/grants/main_test.go

// 명령 줄을 읽는 것과 미리 보기·주기의 화면을 DB 없이 확인한다. 지갑의 자리에는 받은 것을 적어 두는 가짜를 넣는다.
package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eventgrant"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	firstUser  = "aaaaaaaa-0000-4000-8000-000000000001"
	secondUser = "aaaaaaaa-0000-4000-8000-000000000002"
)

// fakeWallets 는 정해 둔 대로 답하는 가짜 지갑이다. 준 사람을 적어 둔다.
type fakeWallets struct {
	granted, wallets int
	given            []uuid.UUID
	err              error
}

func (f *fakeWallets) CountGranted(context.Context, string, []uuid.UUID) (int, error) {
	return f.granted, nil
}

func (f *fakeWallets) CountWallets(context.Context, []uuid.UUID) (int, error) {
	return f.wallets, nil
}

func (f *fakeWallets) GrantFreeOnce(_ context.Context, user uuid.UUID, amount credit.Amount, _ string) (wallet.Grant, error) {
	if f.err != nil {
		return wallet.Grant{}, f.err
	}
	f.given = append(f.given, user)
	return wallet.Grant{Amount: amount}, nil
}

// quietLogs 는 테스트 동안 지급의 기록(로그)을 버린다.
func quietLogs(t *testing.T) {
	t.Helper()
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(io.Discard, nil)))
	t.Cleanup(func() { slog.SetDefault(previous) })
}

// rosterFile 은 두 사람과 겹친 줄 하나가 적힌 명단 파일을 만든다.
func rosterFile(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "roster.txt")
	text := "# 대상\n" + firstUser + "\n" + secondUser + "\n" + firstUser + "\n"
	if err := os.WriteFile(path, []byte(text), 0o600); err != nil {
		t.Fatalf("명단을 만들지 못했다: %v", err)
	}
	return path
}

func TestParseReadsOptionsAnywhere(t *testing.T) {
	for _, args := range [][]string{
		{"give", "roster.txt", "-event", "launch", "-silver", "500", "-reason", "출시 기념"},
		{"-event", "launch", "-silver", "500", "give", "-reason", "출시 기념", "roster.txt", "-apply"},
	} {
		req, err := parse(args, "cli:me")

		if err != nil || req.file != "roster.txt" || req.plan.Key != "event-launch" || req.plan.Silver != 500 ||
			req.plan.Reason != "출시 기념" || req.plan.By != "cli:me" {
			t.Errorf("%v: 일 = %+v, %v", args, req, err)
		}
	}
}

func TestParseRefusesWhatCannotBeGiven(t *testing.T) {
	cases := map[string][]string{
		"일이 없다":     {"roster.txt", "-event", "launch", "-silver", "500", "-reason", "이유"},
		"명단이 없다":    {"give", "-event", "launch", "-silver", "500", "-reason", "이유"},
		"이름이 없다":    {"give", "roster.txt", "-silver", "500", "-reason", "이유"},
		"이름이 틀렸다":   {"give", "roster.txt", "-event", "Launch!", "-silver", "500", "-reason", "이유"},
		"실버가 없다":    {"give", "roster.txt", "-event", "launch", "-reason", "이유"},
		"실버가 정수 아님": {"give", "roster.txt", "-event", "launch", "-silver", "5.5", "-reason", "이유"},
		"실버가 0":     {"give", "roster.txt", "-event", "launch", "-silver", "0", "-reason", "이유"},
		"실버가 상한 넘음": {"give", "roster.txt", "-event", "launch", "-silver", "1000001", "-reason", "이유"},
		"이유가 없다":    {"give", "roster.txt", "-event", "launch", "-silver", "500"},
		"모르는 옵션":    {"give", "roster.txt", "-event", "launch", "-silver", "500", "-reason", "이유", "-at", "now"},
	}
	for name, args := range cases {
		if _, err := parse(args, "cli:me"); err == nil {
			t.Errorf("%s: 받아들였다", name)
		}
	}
}

func TestReadRosterFillsTheUsers(t *testing.T) {
	req, err := readRoster(request{file: rosterFile(t)})

	if err != nil || len(req.plan.Users) != 2 || req.duplicates != 1 || req.plan.Users[0] != uuid.MustParse(firstUser) {
		t.Errorf("일 = %+v, %v", req, err)
	}
}

func TestReadRosterNamesTheFileOnABadLine(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bad.txt")
	if err := os.WriteFile(path, []byte(firstUser+"\nnot-a-user\n"), 0o600); err != nil {
		t.Fatalf("명단을 만들지 못했다: %v", err)
	}

	_, err := readRoster(request{file: path})

	if err == nil || !strings.Contains(err.Error(), "bad.txt: 2째 줄") {
		t.Errorf("오류 = %v", err)
	}
}

// aRequest 는 두 사람에게 500 실버를 주는 일이다.
func aRequest(t *testing.T, apply bool) request {
	t.Helper()
	req, err := parse([]string{"give", rosterFile(t), "-event", "launch", "-silver", "500", "-reason", "출시 기념"}, "cli:me")
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	if req, err = readRoster(req); err != nil {
		t.Fatalf("명단을 읽지 못했다: %v", err)
	}
	req.apply = apply
	return req
}

func TestWithoutApplyNothingIsGiven(t *testing.T) {
	fake := &fakeWallets{granted: 1, wallets: 1}
	var out bytes.Buffer

	err := do(context.Background(), fake, aRequest(t, false), 720*time.Hour, &out)

	if err != nil || len(fake.given) != 0 {
		t.Fatalf("오류 = %v, 준 사람 = %v", err, fake.given)
	}
	for _, want := range []string{
		"지급: event-launch, 한 사람에 실버 500, 받은 때부터 720h0m0s 뒤에 사라진다",
		"명단: 2명 (겹친 줄 1개는 한 번만 센다)",
		"이미 받은 사람: 1명",
		"지갑이 없는 사람: 1명",
		"새로 받을 사람: 1명, 실버 합계 500",
		"-apply 를 붙입니다",
	} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("%q 가 없다:\n%s", want, out.String())
		}
	}
}

func TestApplyGivesAndPrintsTheResult(t *testing.T) {
	quietLogs(t)
	fake := &fakeWallets{wallets: 2}
	var out bytes.Buffer

	err := do(context.Background(), fake, aRequest(t, true), 720*time.Hour, &out)

	if err != nil || len(fake.given) != 2 || !strings.Contains(out.String(), "준 사람: 2명, 이미 받아 건너뛴 사람: 0명") {
		t.Errorf("오류 = %v, 준 사람 = %v, 화면:\n%s", err, fake.given, out.String())
	}
	// 지갑이 모두 있으면 그 줄은 찍지 않는다
	if strings.Contains(out.String(), "지갑이 없는 사람") {
		t.Errorf("화면:\n%s", out.String())
	}
}

func TestAFailureSaysHowToGoOn(t *testing.T) {
	quietLogs(t)
	fake := &fakeWallets{wallets: 2, err: errors.New("DB 가 답하지 않는다")}
	var out bytes.Buffer

	err := do(context.Background(), fake, aRequest(t, true), 720*time.Hour, &out)

	if err == nil || !strings.Contains(err.Error(), "1명째에서 멈췄습니다. 같은 명령을 다시 돌리면") {
		t.Errorf("오류 = %v", err)
	}
}

func TestProgressIsPrintedEveryThousand(t *testing.T) {
	var out bytes.Buffer
	print := progress(&out)

	for done := 1; done <= 2*progressEvery+1; done++ {
		print(eventgrant.Result{Given: done})
	}

	if strings.Count(out.String(), "명 봤습니다") != 2 || !strings.Contains(out.String(), "2000명 봤습니다 (준 사람 2000명)") {
		t.Errorf("화면:\n%s", out.String())
	}
}
