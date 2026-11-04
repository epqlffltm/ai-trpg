// billing-server/cmd/autocharges/main.go

// 끝나지 않은 자동 충전(#980)을 보고, 운영자가 결과를 정하는 명령. 운영자가 쓴다. 서버와 같은 설정(.env)을 읽는다.
//
//	go run ./cmd/autocharges stuck [-older-than 24h]
//	go run ./cmd/autocharges decide <일 번호> paid -payment-key <결제 번호> -reason "<근거>" [-by <이름>]
//	go run ./cmd/autocharges decide <일 번호> declined -reason "<근거>" [-by <이름>]
//
// stuck 은 끝나지 않은 채(pending, charging) 하루 넘게 지난 일을 찍는다. 대사가 경보(autocharge.stuck)를 낸 일이다.
// 결제 작업은 답을 받지 못한 결제를 3일(autocharge.ResendFor) 동안 다시 보내고, 그 뒤로는 주문 번호로 조회한다.
// 조회로도 모르는 일은 결제 대행사의 상점관리자에서 일 번호(= 주문 번호)로 결제를 찾아 확인한 뒤 decide 로 정한다.
//
//	결제가 완료됐다        paid(상점관리자의 결제 번호를 -payment-key 로 적는다. 골드가 들어간다)
//	결제가 없거나 실패했다  declined(돈이 나가지 않았다. 사용자의 알림함에 알린다)
//
// 정할 수 있는 것은 3일이 지난 charging 일뿐이다. 그 전에는 결제 작업이 다시 보내므로 정하면 엇갈릴 수 있다.
// 결정은 로그(operation autocharge.resolve)에 근거와 정한 사람과 함께 남는다. -by 를 적지 않으면 "cli:<이 PC 의 계정 이름>"이다.
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
	"time"

	"github.com/google/uuid"
	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/autocharges stuck [-older-than 24h]
  go run ./cmd/autocharges decide <일 번호> paid -payment-key <결제 번호> -reason "<근거>" [-by <이름>]
  go run ./cmd/autocharges decide <일 번호> declined -reason "<근거>" [-by <이름>]`

// timeLayout 은 화면에 시각을 찍는 모양이다. 이 PC 의 시간대로 찍는다.
const timeLayout = "2006-01-02 15:04:05 -07:00"

// listLimit 은 stuck 이 찍는 가장 많은 수다.
const listLimit = 1000

// 일의 종류.
const (
	actionStuck  = "stuck"
	actionDecide = "decide"
)

// request 는 명령 줄에서 읽은 일 하나다.
type request struct {
	action     string
	olderThan  time.Duration
	resolution autocharge.Resolution
}

// charges 는 이 명령이 쓰는 자동 충전 서비스의 모양이다. *autocharge.Service 가 이 모양이다.
type charges interface {
	ListOpen(ctx context.Context, olderThan time.Duration, limit int) ([]autocharge.OpenRequest, error)
	Resolve(ctx context.Context, resolution autocharge.Resolution) error
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("자동 충전을 다루지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 설정을 읽고, 자동 충전 서비스에 그 일을 한다.
func run(args []string, out io.Writer) error {
	req, err := parse(args, defaultDecider())
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.LoadJobs(os.LookupEnv)
	if err != nil {
		return err
	}
	// 결정의 기록(autocharge.resolve)은 로그로 남는다. 서버와 같은 모양(JSON)으로 표준 오류에 찍는다
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
	// 결정은 결제 대행사를 부르지 않는다. 결제 작업과 같은 길(주문, 골드)로 적으려고 결제하는 일을 붙인다
	cards := app.NewCards(settings.Payment)
	service := autocharge.NewService(pool, time.Now, cards, services.Eligibility).WithCharging(cards, services.Orders)

	fmt.Fprintf(out, "스키마: %s\n", settings.Database.Schema)
	return do(ctx, service, req, out)
}

// parse 는 명령 줄을 읽는다. 옵션(-reason 같은 것)은 낱말의 앞에 와도 뒤에 와도 된다.
func parse(args []string, decider string) (request, error) {
	flags := flag.NewFlagSet("autocharges", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	req := request{}
	flags.DurationVar(&req.olderThan, "older-than", order.StuckAfter, "끝나지 않은 채 이만큼 지난 일을 찍는다")
	flags.StringVar(&req.resolution.PaymentKey, "payment-key", "", "상점관리자에서 본 결제 번호(paid 일 때)")
	flags.StringVar(&req.resolution.Reason, "reason", "", "그렇게 정한 근거")
	flags.StringVar(&req.resolution.DecidedBy, "by", decider, "정한 사람")
	words, err := parseInterleaved(flags, args)
	if err != nil {
		return request{}, errors.New(usage)
	}
	return readWords(req, words)
}

// parseInterleaved 는 옵션과 낱말이 섞인 명령 줄에서 옵션을 읽고, 옵션이 아닌 낱말들을 차례로 돌려준다.
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

// readWords 는 옵션이 아닌 낱말들(일, 일 번호, 결과)을 읽는다.
func readWords(req request, words []string) (request, error) {
	switch {
	case len(words) == 1 && words[0] == actionStuck:
		if req.olderThan <= 0 {
			return request{}, errors.New("-older-than 은 0 보다 커야 합니다")
		}
		req.action = actionStuck
		return req, nil
	case len(words) == 3 && words[0] == actionDecide:
		return readResolution(req, words[1], words[2])
	default:
		return request{}, errors.New(usage)
	}
}

// readResolution 은 decide 의 일 번호와 결과를 읽는다. 근거가 없거나, paid 인데 결제 번호가 없거나, declined 인데 있으면 거절한다.
func readResolution(req request, id string, outcome string) (request, error) {
	parsed, err := uuid.Parse(id)
	if err != nil {
		return request{}, errors.New("일 번호가 UUID 가 아닙니다.\n" + usage)
	}
	switch autocharge.Outcome(outcome) {
	case autocharge.OutcomePaid:
		if req.resolution.PaymentKey == "" {
			return request{}, errors.New("paid 는 -payment-key 로 상점관리자의 결제 번호를 적어야 합니다.\n" + usage)
		}
	case autocharge.OutcomeDeclined:
		if req.resolution.PaymentKey != "" {
			return request{}, errors.New("declined 에는 -payment-key 를 적지 않습니다.\n" + usage)
		}
	default:
		return request{}, errors.New("결과는 paid, declined 가운데 하나입니다.\n" + usage)
	}
	if req.resolution.Reason == "" {
		return request{}, errors.New("-reason 으로 그렇게 정한 근거를 적어야 합니다(상점관리자에서 본 것).\n" + usage)
	}
	req.action = actionDecide
	req.resolution.ID, req.resolution.Outcome = parsed, autocharge.Outcome(outcome)
	return req, nil
}

// do 는 읽은 일을 자동 충전 서비스에 하고 결과를 찍는다.
func do(ctx context.Context, service charges, req request, out io.Writer) error {
	if req.action == actionStuck {
		open, err := service.ListOpen(ctx, req.olderThan, listLimit)
		if err != nil {
			return err
		}
		printOpen(out, open)
		return nil
	}
	if err := service.Resolve(ctx, req.resolution); err != nil {
		return err
	}
	fmt.Fprintf(out, "정했습니다: %s  %s\n", req.resolution.ID, req.resolution.Outcome)
	return nil
}

// printOpen 은 끝나지 않은 일들을 한 줄씩 찍는다.
func printOpen(out io.Writer, open []autocharge.OpenRequest) {
	if len(open) == 0 {
		fmt.Fprintln(out, "끝나지 않은 자동 충전이 없습니다")
		return
	}
	for _, o := range open {
		fmt.Fprintln(out, formatOpen(o))
	}
}

// formatOpen 은 일 하나를 사람이 읽는 글로 바꾼다. 사용자와 카드는 찍지 않는다. 상점관리자에서는 일 번호(주문 번호)로 찾는다.
func formatOpen(o autocharge.OpenRequest) string {
	line := fmt.Sprintf("%s  %s%s  %s 부터  %s %d원  %d번 시도",
		o.ID, o.Status, statusHint(o), o.CreatedAt.Local().Format(timeLayout), o.ProductID, o.Price, o.Attempts)
	if o.LastError != "" {
		line += "  마지막: " + o.LastError
	}
	return line
}

// statusHint 는 일마다 운영자가 할 것이다.
func statusHint(o autocharge.OpenRequest) string {
	switch {
	case o.Decidable:
		return "(상점관리자에서 확인: paid 또는 declined)"
	case o.Status == "charging":
		return "(결제 작업이 아직 다시 보낸다. " + o.CreatedAt.Add(autocharge.ResendFor).Local().Format(timeLayout) + " 부터 정한다)"
	default:
		return "(보내지 않았다. 결제 작업(billing-autocharge)이 도는지 본다)"
	}
}

// defaultDecider 는 -by 를 적지 않았을 때 정한 사람으로 적을 이름이다. 이 PC 의 계정 이름을 쓴다.
func defaultDecider() string {
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
