// billing-server/cmd/prices/main.go

// 가격표를 보고 바꾸는 명령. 운영자가 쓴다. 서버와 같은 설정(.env 의 DATABASE_URL, DB_SCHEMA)을 읽는다.
//
//	go run ./cmd/prices list                                    이름마다 지금의 값
//	go run ./cmd/prices history <이름>                          그 이름의 모든 줄(예약 포함)
//	go run ./cmd/prices set <이름> <크레딧> -reason "<이유>"    값을 정한다. 없던 이름이면 새로 판다
//	go run ./cmd/prices stop <이름> -reason "<이유>"            판매를 멈춘다
//
// set 과 stop 은 -at <시각>(RFC 3339, 예: 2026-11-01T00:00:00+09:00)으로 적용을 미래로 미룰 수 있고,
// -by <이름>으로 바꾼 사람을 적는다. 적지 않으면 "cli:<이 PC 의 계정 이름>"이다.
//
// 가격표는 덧붙이기만 한다. 값을 고치거나 줄을 지우는 명령은 없다. 잘못 넣었으면 새 값을 다시 넣는다.
// 나중에 관리 서버가 생기면 같은 일(pricing.Service 의 Set, Stop)을 관리자용 주소로 연다.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"os/user"
	"strconv"
	"time"

	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/prices list
  go run ./cmd/prices history <이름>
  go run ./cmd/prices set <이름> <크레딧> -reason "<이유>" [-at <시각>] [-by <이름>]
  go run ./cmd/prices stop <이름> -reason "<이유>" [-at <시각>] [-by <이름>]`

// timeLayout 은 화면에 시각을 찍는 모양이다. 이 PC 의 시간대로 찍는다.
const timeLayout = "2006-01-02 15:04:05 -07:00"

// request 는 명령 줄에서 읽은 일 하나다.
type request struct {
	action string
	code   string
	// credits 는 set 의 값이다.
	credits credit.Amount
	at      time.Time
	reason  string
	by      string
}

// prices 는 이 명령이 쓰는 가격표의 모양이다. *pricing.Service 가 이 모양이다.
type prices interface {
	Current(ctx context.Context) ([]pricing.Version, error)
	History(ctx context.Context, code string) ([]pricing.Version, error)
	Set(ctx context.Context, change pricing.Change) (pricing.Version, error)
	Stop(ctx context.Context, change pricing.Change) (pricing.Version, error)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("가격표를 다루지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 설정을 읽고, 가격표에 그 일을 한다.
func run(args []string, out io.Writer) error {
	req, err := parse(args, defaultChanger())
	if err != nil {
		return err
	}
	loadDotEnv()
	target, err := config.LoadDatabase(os.LookupEnv)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	pool, err := database.NewPool(ctx, target.URL, target.Schema)
	if err != nil {
		return err
	}
	defer pool.Close()

	fmt.Fprintf(out, "스키마: %s\n", target.Schema)
	return do(ctx, pricing.NewService(pool, time.Now), req, out)
}

// parse 는 명령 줄을 읽는다. 옵션(-reason 같은 것)은 이름과 값의 앞에 와도 뒤에 와도 된다.
func parse(args []string, changer string) (request, error) {
	flags := flag.NewFlagSet("prices", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	req := request{}
	var at string
	flags.StringVar(&req.reason, "reason", "", "바꾼 이유")
	flags.StringVar(&req.by, "by", changer, "바꾼 사람")
	flags.StringVar(&at, "at", "", "적용을 시작할 시각(RFC 3339)")
	words, err := parseInterleaved(flags, args)
	if err != nil {
		return request{}, errors.New(usage)
	}
	if req, err = readWords(req, words); err != nil {
		return request{}, err
	}
	if at != "" {
		if req.at, err = time.Parse(time.RFC3339, at); err != nil {
			return request{}, errors.New("-at 은 2026-11-01T00:00:00+09:00 모양이어야 합니다")
		}
	}
	return req, nil
}

// parseInterleaved 는 옵션과 낱말이 섞인 명령 줄에서 옵션을 읽고, 옵션이 아닌 낱말들을 차례로 돌려준다.
// 표준 flag 는 옵션이 아닌 낱말을 만나면 거기서 멈춘다. 멈춘 자리의 낱말을 꺼내 두고 남은 것을 다시 읽는다.
func parseInterleaved(flags *flag.FlagSet, args []string) ([]string, error) {
	var words []string
	for {
		if err := flags.Parse(args); err != nil {
			return nil, err
		}
		if flags.NArg() == 0 {
			return words, nil
		}
		words = append(words, flags.Arg(0))
		args = flags.Args()[1:]
	}
}

// readWords 는 옵션이 아닌 낱말들(일, 이름, 값)을 읽는다.
func readWords(req request, words []string) (request, error) {
	switch {
	case len(words) == 1 && words[0] == "list":
		req.action = "list"
	case len(words) == 2 && words[0] == "history":
		req.action, req.code = "history", words[1]
	case len(words) == 3 && words[0] == "set":
		amount, err := strconv.ParseInt(words[2], 10, 64)
		if err != nil {
			return request{}, errors.New("크레딧은 정수여야 합니다.\n" + usage)
		}
		req.action, req.code, req.credits = "set", words[1], credit.Amount(amount)
	case len(words) == 2 && words[0] == "stop":
		req.action, req.code = "stop", words[1]
	default:
		return request{}, errors.New(usage)
	}
	if (req.action == "set" || req.action == "stop") && req.reason == "" {
		return request{}, errors.New("-reason 으로 바꾸는 이유를 적어야 합니다.\n" + usage)
	}
	return req, nil
}

// do 는 읽은 일을 가격표에 하고 결과를 찍는다.
func do(ctx context.Context, list prices, req request, out io.Writer) error {
	change := pricing.Change{Code: req.code, Credits: req.credits, EffectiveAt: req.at, Reason: req.reason, ChangedBy: req.by}
	switch req.action {
	case "list":
		versions, err := list.Current(ctx)
		return printVersions(out, versions, err)
	case "history":
		versions, err := list.History(ctx, req.code)
		return printVersions(out, versions, err)
	case "set":
		version, err := list.Set(ctx, change)
		return printVersions(out, []pricing.Version{version}, err)
	default:
		version, err := list.Stop(ctx, change)
		return printVersions(out, []pricing.Version{version}, err)
	}
}

// printVersions 는 가격표의 줄들을 한 줄씩 찍는다. err 가 있으면 찍지 않고 돌려준다.
func printVersions(out io.Writer, versions []pricing.Version, err error) error {
	if err != nil {
		return err
	}
	if len(versions) == 0 {
		fmt.Fprintln(out, "줄이 없습니다")
	}
	for _, version := range versions {
		fmt.Fprintln(out, formatVersion(version))
	}
	return nil
}

// formatVersion 은 줄 하나를 사람이 읽는 글로 바꾼다.
func formatVersion(version pricing.Version) string {
	value := "판매 중지"
	if version.OnSale {
		value = version.Credits.String() + " 크레딧"
	}
	return fmt.Sprintf("%s  %s  %s 부터  (%s, %s)",
		version.Code, value, version.EffectiveAt.Local().Format(timeLayout), version.Reason, version.ChangedBy)
}

// defaultChanger 는 -by 를 적지 않았을 때 바꾼 사람으로 적을 이름이다. 이 PC 의 계정 이름을 쓴다.
func defaultChanger() string {
	current, err := user.Current()
	if err != nil || current.Username == "" {
		return "cli"
	}
	return "cli:" + current.Username
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		log.Printf(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
