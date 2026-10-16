// billing-server/cmd/orders/main.go

// 결과를 끝내 모르는 주문을 보고, 운영자가 결과를 정하는 명령. 운영자가 쓴다. 서버와 같은 설정(.env)을 읽는다.
//
//	go run ./cmd/orders stuck [-older-than 24h]
//	go run ./cmd/orders decide <주문 번호> paid|failed|refunded -reason "<근거>" [-by <이름>]
//
// stuck 은 confirming·refunding 에 하루(order.StuckAfter) 넘게 머문 주문을 찍는다. 대사가 경보(order.stuck)를 낸 주문이다.
// 결제 대행사의 상점관리자에서 그 주문 번호로 결제를 찾아 확인한 뒤 decide 로 정한다.
//
//	confirming(승인 확인)  돈이 나갔으면 paid(크레딧이 들어간다), 나가지 않았으면 failed
//	refunding(환불 확인)   돈이 돌아갔으면 refunded, 취소되지 않았으면 paid(뺐던 크레딧을 돌려놓는다)
//
// 결정은 로그(operation order.decide)에 근거와 정한 사람과 함께 남는다. -by 를 적지 않으면 "cli:<이 PC 의 계정 이름>"이다.
// 나중에 관리 서버가 생기면 같은 일(order.Service 의 ListStuck, Decide)을 관리자용 주소로 연다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/orders stuck [-older-than 24h]
  go run ./cmd/orders decide <주문 번호> paid|failed|refunded -reason "<근거>" [-by <이름>]`

// timeLayout 은 화면에 시각을 찍는 모양이다. 이 PC 의 시간대로 찍는다.
const timeLayout = "2006-01-02 15:04:05 -07:00"

// listLimit 은 stuck 이 종류마다 찍는 가장 많은 수다.
const listLimit = 1000

// 일의 종류.
const (
	actionStuck  = "stuck"
	actionDecide = "decide"
)

// request 는 명령 줄에서 읽은 일 하나다.
type request struct {
	action    string
	olderThan time.Duration
	decision  order.Decision
}

// orders 는 이 명령이 쓰는 주문 서비스의 모양이다. *order.Service 가 이 모양이다.
type orders interface {
	ListStuck(ctx context.Context, olderThan time.Duration, limit int) ([]order.Order, error)
	Decide(ctx context.Context, decision order.Decision) (order.Order, error)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("주문을 다루지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 설정을 읽고, 주문 서비스에 그 일을 한다.
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
	// 결정의 기록(order.decide)은 로그로 남는다. 서버와 같은 모양(JSON)으로 표준 오류에 찍는다
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	pool, err := database.NewPool(ctx, settings.Database.URL, settings.Database.Schema)
	if err != nil {
		return err
	}
	defer pool.Close()
	services, err := app.NewServices(pool, settings.Rules, app.NewProviders(settings.Payment), time.Now)
	if err != nil {
		return err
	}

	fmt.Fprintf(out, "스키마: %s\n", settings.Database.Schema)
	return do(ctx, services.Orders, req, out)
}

// parse 는 명령 줄을 읽는다. 옵션(-reason 같은 것)은 낱말의 앞에 와도 뒤에 와도 된다.
func parse(args []string, decider string) (request, error) {
	flags := flag.NewFlagSet("orders", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	req := request{}
	flags.DurationVar(&req.olderThan, "older-than", order.StuckAfter, "결과를 모르는 채로 이만큼 지난 주문을 찍는다")
	flags.StringVar(&req.decision.Reason, "reason", "", "그렇게 정한 근거")
	flags.StringVar(&req.decision.DecidedBy, "by", decider, "정한 사람")
	words, err := parseInterleaved(flags, args)
	if err != nil {
		return request{}, errors.New(usage)
	}
	return readWords(req, words)
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

// readWords 는 옵션이 아닌 낱말들(일, 주문 번호, 결과)을 읽는다.
func readWords(req request, words []string) (request, error) {
	switch {
	case len(words) == 1 && words[0] == actionStuck:
		if req.olderThan <= 0 {
			return request{}, errors.New("-older-than 은 0 보다 커야 합니다")
		}
		req.action = actionStuck
		return req, nil
	case len(words) == 3 && words[0] == actionDecide:
		return readDecision(req, words[1], words[2])
	default:
		return request{}, errors.New(usage)
	}
}

// readDecision 은 decide 의 주문 번호와 결과를 읽는다. 근거가 없으면 거절한다.
func readDecision(req request, orderID string, outcome string) (request, error) {
	id, err := uuid.Parse(orderID)
	if err != nil {
		return request{}, errors.New("주문 번호가 UUID 가 아닙니다.\n" + usage)
	}
	switch order.Outcome(outcome) {
	case order.OutcomePaid, order.OutcomeFailed, order.OutcomeRefunded:
	default:
		return request{}, errors.New("결과는 paid, failed, refunded 가운데 하나입니다.\n" + usage)
	}
	if req.decision.Reason == "" {
		return request{}, errors.New("-reason 으로 그렇게 정한 근거를 적어야 합니다(상점관리자에서 본 것).\n" + usage)
	}
	req.action = actionDecide
	req.decision.OrderID, req.decision.Outcome = id, order.Outcome(outcome)
	return req, nil
}

// do 는 읽은 일을 주문 서비스에 하고 결과를 찍는다.
func do(ctx context.Context, service orders, req request, out io.Writer) error {
	if req.action == actionStuck {
		stuck, err := service.ListStuck(ctx, req.olderThan, listLimit)
		if err != nil {
			return err
		}
		printStuck(out, stuck)
		return nil
	}
	decided, err := service.Decide(ctx, req.decision)
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "정했습니다: %s\n", formatOrder(decided))
	return nil
}

// printStuck 은 결과를 모르는 주문들을 한 줄씩 찍는다.
func printStuck(out io.Writer, stuck []order.Order) {
	if len(stuck) == 0 {
		fmt.Fprintln(out, "결과를 모르는 주문이 없습니다")
		return
	}
	for _, o := range stuck {
		fmt.Fprintln(out, formatOrder(o))
	}
}

// formatOrder 는 주문 하나를 사람이 읽는 글로 바꾼다. 결제 번호는 찍지 않는다. 상점관리자에서는 주문 번호로 찾는다.
func formatOrder(o order.Order) string {
	return fmt.Sprintf("%s  %s%s  %s 부터  %d원  사용자 %s",
		o.ID, o.Status, statusHint(o.Status), o.UpdatedAt.Local().Format(timeLayout), o.Price, o.UserID)
}

// statusHint 는 결과를 모르는 상태마다 운영자가 확인할 것이다. 끝난 상태면 빈 글자다.
func statusHint(status order.Status) string {
	switch status {
	case order.StatusConfirming:
		return "(승인 확인: paid 또는 failed)"
	case order.StatusRefunding:
		return "(환불 확인: refunded 또는 paid)"
	default:
		return ""
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
