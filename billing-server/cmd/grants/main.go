// billing-server/cmd/grants/main.go

// 명단의 사용자들에게 이벤트 실버(무료 크레딧)를 한 번씩 주는 명령. 운영자가 쓴다. 서버와 같은 설정(.env)을 읽는다.
//
//	go run ./cmd/grants give <명단 파일> -event <이름> -silver <양> -reason "<이유>"          미리 본다(아무것도 주지 않는다)
//	go run ./cmd/grants give <명단 파일> -event <이름> -silver <양> -reason "<이유>" -apply   준다
//
// 명단은 한 줄에 사용자 번호(인증 서버의 사용자 UUID) 하나다. 빈 줄과 '#' 로 시작하는 줄은 건너뛴다.
// 지급의 이름은 "event-<이름>" 이다. 한 사람은 같은 이름을 한 번만 받는다. 같은 명령을 다시 돌려도 받은 사람은 건너뛴다.
// 그래서 중간에 멈췄으면(오류, Ctrl+C) 같은 명령을 다시 돌리면 된다.
// 준 실버는 다른 무료 크레딧과 같이 FREE_CREDIT_TTL 뒤에 사라진다.
//
// 지급은 로그(operation grant.event)에 이름, 양, 몇 명, 준 사람(-by), 이유와 함께 남는다. -by 를 적지 않으면 "cli:<이 PC 의 계정 이름>"이다.
// 나중에 관리 서버가 생기면 같은 일(eventgrant 의 Look, Give)을 관리자용 주소로 연다.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"log/slog"
	"os"
	"os/signal"
	"os/user"
	"strconv"
	"time"

	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/eventgrant"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/grants give <명단 파일> -event <이름> -silver <양> -reason "<이유>" [-apply] [-by <이름>]`

// progressEvery 는 줄 때 진행을 몇 명마다 찍는지다.
const progressEvery = 1000

// request 는 명령 줄에서 읽은 일 하나다.
type request struct {
	// file 은 명단 파일이다.
	file string
	// plan 은 줄 것이다. 명단(Users)은 run 이 파일을 읽어 채운다.
	plan eventgrant.Plan
	// duplicates 는 명단에서 겹친 줄의 수다(run 이 채운다).
	duplicates int
	// apply 가 false 면 미리 보기만 한다.
	apply bool
}

// wallets 는 이 명령이 쓰는 지갑의 모양이다. *wallet.Service 가 이 모양이다.
type wallets interface {
	eventgrant.Counter
	eventgrant.Granter
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("이벤트 실버를 주지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 명단을 읽고, 설정을 읽고, 미리 보거나 준다.
func run(args []string, out io.Writer) error {
	req, err := parse(args, defaultGranter())
	if err != nil {
		return err
	}
	// 명단을 DB 에 붙기 전에 읽는다. 틀린 줄이 있으면 DB 를 건드리지 않고 끝난다
	if req, err = readRoster(req); err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.LoadJobs(os.LookupEnv)
	if err != nil {
		return err
	}
	// 지급의 기록(grant.event)은 로그로 남는다. 서버와 같은 모양(JSON)으로 표준 오류에 찍는다
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	pool, err := database.NewPool(ctx, settings.Database.URL, settings.Database.Schema, database.JobLimits)
	if err != nil {
		return err
	}
	defer pool.Close()
	services, err := app.NewServices(pool, settings.Rules, app.NewProviders(settings.Payment), time.Now)
	if err != nil {
		return err
	}

	fmt.Fprintf(out, "스키마: %s\n", settings.Database.Schema)
	return do(ctx, services.Wallet, req, settings.Rules.FreeCreditTTL, out)
}

// parse 는 명령 줄을 읽는다. 옵션(-event 같은 것)은 낱말의 앞에 와도 뒤에 와도 된다.
func parse(args []string, granter string) (request, error) {
	flags := flag.NewFlagSet("grants", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	req := request{}
	var event, silver string
	flags.StringVar(&event, "event", "", "이벤트 이름. 지급의 이름은 event-<이름> 이다")
	flags.StringVar(&silver, "silver", "", "한 사람에게 주는 실버")
	flags.StringVar(&req.plan.Reason, "reason", "", "주는 이유")
	flags.StringVar(&req.plan.By, "by", granter, "준 사람")
	flags.BoolVar(&req.apply, "apply", false, "미리 보기만 하지 않고 준다")
	words, err := parseInterleaved(flags, args)
	if err != nil || len(words) != 2 || words[0] != "give" {
		return request{}, errors.New(usage)
	}
	req.file = words[1]
	if req.plan.Key, err = eventgrant.Key(event); err != nil {
		return request{}, fmt.Errorf("-event: %w.\n%s", err, usage)
	}
	if req.plan.Silver, err = readSilver(silver); err != nil {
		return request{}, fmt.Errorf("-silver: %w.\n%s", err, usage)
	}
	if req.plan.Reason == "" {
		return request{}, errors.New("-reason 으로 주는 이유를 적어야 합니다.\n" + usage)
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

// readSilver 는 -silver 의 값을 읽는다. 정수여야 하고 받는 범위 안이어야 한다.
func readSilver(text string) (credit.Amount, error) {
	amount, err := strconv.ParseInt(text, 10, 64)
	if err != nil {
		return 0, errors.New("정수여야 합니다")
	}
	silver := credit.Amount(amount)
	return silver, eventgrant.CheckSilver(silver)
}

// readRoster 는 명단 파일을 읽어 줄 사람을 채운다.
func readRoster(req request) (request, error) {
	file, err := os.Open(req.file)
	if err != nil {
		return request{}, err
	}
	defer file.Close()
	roster, err := eventgrant.ReadRoster(file)
	if err != nil {
		return request{}, fmt.Errorf("%s: %w", req.file, err)
	}
	req.plan.Users, req.duplicates = roster.Users, roster.Duplicates
	return req, nil
}

// do 는 미리 보고 찍는다. -apply 면 이어서 주고 결과를 찍는다.
func do(ctx context.Context, service wallets, req request, ttl time.Duration, out io.Writer) error {
	preview, err := eventgrant.Look(ctx, service, req.plan)
	if err != nil {
		return err
	}
	printPreview(out, req, preview, ttl)
	if !req.apply {
		fmt.Fprintln(out, "미리 보기만 했습니다. 주려면 -apply 를 붙입니다")
		return nil
	}
	result, err := eventgrant.Give(ctx, service, req.plan, progress(out))
	fmt.Fprintf(out, "준 사람: %d명, 이미 받아 건너뛴 사람: %d명\n", result.Given, result.Already)
	if err != nil {
		return fmt.Errorf("%d명째에서 멈췄습니다. 같은 명령을 다시 돌리면 받은 사람은 건너뜁니다: %w", result.Done()+1, err)
	}
	return nil
}

// printPreview 는 주기 전에 본 명단을 찍는다.
func printPreview(out io.Writer, req request, preview eventgrant.Preview, ttl time.Duration) {
	fmt.Fprintf(out, "지급: %s, 한 사람에 실버 %s, 받은 때부터 %s 뒤에 사라진다\n", req.plan.Key, req.plan.Silver, ttl)
	fmt.Fprintf(out, "명단: %d명", preview.Listed)
	if req.duplicates > 0 {
		fmt.Fprintf(out, " (겹친 줄 %d개는 한 번만 센다)", req.duplicates)
	}
	fmt.Fprintln(out)
	fmt.Fprintf(out, "이미 받은 사람: %d명 (건너뛴다)\n", preview.Granted)
	if preview.NoWallet > 0 {
		fmt.Fprintf(out, "지갑이 없는 사람: %d명 (이 서버에서 크레딧이 바뀐 적이 없다. 번호가 맞는지 본다)\n", preview.NoWallet)
	}
	fmt.Fprintf(out, "새로 받을 사람: %d명, 실버 합계 %s\n", preview.ToGive(), preview.Total(req.plan.Silver))
}

// progress 는 줄 때 progressEvery 명마다 진행을 찍는 함수를 돌려준다.
func progress(out io.Writer) func(eventgrant.Result) {
	return func(result eventgrant.Result) {
		if result.Done()%progressEvery == 0 {
			fmt.Fprintf(out, "%d명 봤습니다 (준 사람 %d명)\n", result.Done(), result.Given)
		}
	}
}

// defaultGranter 는 -by 를 적지 않았을 때 준 사람으로 적을 이름이다. 이 PC 의 계정 이름을 쓴다.
func defaultGranter() string {
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
