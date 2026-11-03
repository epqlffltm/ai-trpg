// billing-server/cmd/coupons/main.go

// 쿠폰을 만들고, 보고, 멈추는 명령(#979). 운영자가 쓴다. 서버와 같은 설정(.env)을 읽는다.
//
//	go run ./cmd/coupons create -code <코드> -silver <양> -from <날짜> -until <날짜> -reason "<까닭>" [-max <사람 수>] [-days <날 수>] [-by <이름>]
//	go run ./cmd/coupons list [-limit <개수>]
//	go run ./cmd/coupons stop <코드>
//
// 날짜는 한국 날짜다(YYYY-MM-DD). -from 날의 0시부터 -until 날의 24시 전까지 넣을 수 있다.
// -max 는 모두 합쳐 받을 수 있는 사람의 수다. 적지 않으면 한도가 없다. 1 이면 한 사람용처럼 쓴다.
// -days 는 받은 실버가 사라질 때까지의 날 수다. 적지 않으면 다른 무료 크레딧과 같다(FREE_CREDIT_TTL).
// 멈춘 쿠폰은 다시 열지 않는다. 같은 일을 하려면 새 코드로 만든다. 이미 받은 실버는 그대로다.
//
// 만들기와 멈추기는 로그(operation coupon.create, coupon.stop)에 코드, 양, 만든 사람(-by), 까닭과 함께 남는다.
// -by 를 적지 않으면 "cli:<이 PC 의 계정 이름>"이다. 나중에 관리 서버가 생기면 같은 일(coupon.Service)을 관리자용 주소로 연다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/coupon"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/coupons create -code <코드> -silver <양> -from <YYYY-MM-DD> -until <YYYY-MM-DD> -reason "<까닭>" [-max <사람 수>] [-days <날 수>] [-by <이름>]
  go run ./cmd/coupons list [-limit <개수>]
  go run ./cmd/coupons stop <코드>`

// defaultLimit 는 list 가 보이는 쿠폰의 수다.
const defaultLimit = 20

// maxLimit 는 list 가 한 번에 보이는 가장 많은 쿠폰의 수다.
const maxLimit = 200

// korea 는 날짜를 읽는 시간대다. 한국은 일광 절약 시간이 없어 고정이다.
var korea = time.FixedZone("KST", 9*60*60)

// dateLayout 은 날짜의 모양이다.
const dateLayout = "2006-01-02"

// command 는 명령 줄에서 읽은 일 하나다.
type command struct {
	// action 은 create, list, stop 중 하나다.
	action string
	spec   coupon.Spec
	limit  int
	code   string
}

// coupons 는 이 명령이 쓰는 쿠폰의 모양이다. *coupon.Service 가 이 모양이다.
type coupons interface {
	Create(ctx context.Context, spec coupon.Spec) (coupon.Coupon, error)
	List(ctx context.Context, limit int) ([]coupon.Coupon, error)
	Stop(ctx context.Context, code string) error
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("쿠폰의 일을 끝내지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 설정을 읽고, 일을 한다.
func run(args []string, out io.Writer) error {
	cmd, err := parse(args, defaultOperator())
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.LoadJobs(os.LookupEnv)
	if err != nil {
		return err
	}
	// 만들기와 멈추기의 기록은 로그로 남는다. 서버와 같은 모양(JSON)으로 표준 오류에 찍는다
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	pool, err := database.NewPool(ctx, settings.Database.URL, settings.Database.Schema, database.JobLimits)
	if err != nil {
		return err
	}
	defer pool.Close()
	fmt.Fprintf(out, "스키마: %s\n", settings.Database.Schema)
	// 받게 하는 일(Redeem)은 쓰지 않는다. 지갑과 본인인증을 넣지 않는다
	return do(ctx, coupon.NewService(pool, time.Now, nil, nil), cmd, out)
}

// parse 는 명령 줄을 읽는다. 옵션은 낱말의 앞에 와도 뒤에 와도 된다.
func parse(args []string, operator string) (command, error) {
	flags := flag.NewFlagSet("coupons", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var cmd command
	var silver, from, until string
	flags.StringVar(&cmd.spec.Code, "code", "", "코드")
	flags.StringVar(&silver, "silver", "", "한 사람이 받는 실버")
	flags.StringVar(&from, "from", "", "넣을 수 있는 첫날(한국 날짜)")
	flags.StringVar(&until, "until", "", "넣을 수 있는 마지막 날(한국 날짜)")
	flags.IntVar(&cmd.spec.MaxRedemptions, "max", 0, "받을 수 있는 사람의 수. 0 이면 한도가 없다")
	flags.IntVar(&cmd.spec.SilverDays, "days", 0, "받은 실버가 사라질 때까지의 날 수. 0 이면 기본값")
	flags.StringVar(&cmd.spec.Reason, "reason", "", "만든 까닭")
	flags.StringVar(&cmd.spec.CreatedBy, "by", operator, "만든 사람")
	flags.IntVar(&cmd.limit, "limit", defaultLimit, "보일 쿠폰의 수")
	words, err := parseInterleaved(flags, args)
	if err != nil || len(words) == 0 {
		return command{}, errors.New(usage)
	}
	cmd.action = words[0]
	switch {
	case cmd.action == "create" && len(words) == 1:
		return withPeriod(withSilver(cmd, silver), from, until)
	case cmd.action == "list" && len(words) == 1:
		if cmd.limit < 1 || cmd.limit > maxLimit {
			return command{}, fmt.Errorf("-limit 은 1 에서 %d 사이여야 합니다.\n%s", maxLimit, usage)
		}
		return cmd, nil
	case cmd.action == "stop" && len(words) == 2:
		cmd.code = words[1]
		return cmd, nil
	}
	return command{}, errors.New(usage)
}

// withSilver 는 -silver 를 읽어 채운다. 범위는 쿠폰이 본다(Spec.Validate).
func withSilver(cmd command, text string) command {
	amount, err := strconv.ParseInt(text, 10, 64)
	if err != nil {
		amount = 0
	}
	cmd.spec.Silver = credit.Amount(amount)
	return cmd
}

// withPeriod 는 -from 과 -until 을 읽어 넣을 수 있는 때를 채운다. -until 날의 다음 날 0시 전까지다.
func withPeriod(cmd command, from, until string) (command, error) {
	start, err := time.ParseInLocation(dateLayout, from, korea)
	if err != nil {
		return command{}, fmt.Errorf("-from 은 YYYY-MM-DD 여야 합니다.\n%s", usage)
	}
	last, err := time.ParseInLocation(dateLayout, until, korea)
	if err != nil {
		return command{}, fmt.Errorf("-until 은 YYYY-MM-DD 여야 합니다.\n%s", usage)
	}
	cmd.spec.StartsAt, cmd.spec.EndsAt = start, last.AddDate(0, 0, 1)
	return cmd, nil
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

// do 는 읽은 일을 한다.
func do(ctx context.Context, service coupons, cmd command, out io.Writer) error {
	switch cmd.action {
	case "create":
		return create(ctx, service, cmd.spec, out)
	case "list":
		return list(ctx, service, cmd.limit, out)
	default:
		return stopCoupon(ctx, service, cmd.code, out)
	}
}

// create 는 쿠폰을 만들고 찍는다. 만든 것을 로그에 남긴다.
func create(ctx context.Context, service coupons, spec coupon.Spec, out io.Writer) error {
	made, err := service.Create(ctx, spec)
	if err != nil {
		return err
	}
	slog.InfoContext(ctx, "운영자가 쿠폰을 만들었다",
		slog.String("operation", "coupon.create"), slog.String("code", made.Code),
		slog.String("silver", made.Silver.String()), slog.Int("max_redemptions", made.MaxRedemptions),
		slog.String("created_by", made.CreatedBy), slog.String("reason", made.Reason))
	fmt.Fprintln(out, "만들었습니다")
	printCoupon(out, made)
	return nil
}

// list 는 최근에 만든 쿠폰을 찍는다.
func list(ctx context.Context, service coupons, limit int, out io.Writer) error {
	found, err := service.List(ctx, limit)
	if err != nil {
		return err
	}
	if len(found) == 0 {
		fmt.Fprintln(out, "쿠폰이 없습니다")
	}
	for _, one := range found {
		printCoupon(out, one)
	}
	return nil
}

// stopCoupon 은 쿠폰을 멈추고 로그에 남긴다.
func stopCoupon(ctx context.Context, service coupons, code string, out io.Writer) error {
	if err := service.Stop(ctx, code); err != nil {
		return err
	}
	normalized, _ := coupon.NormalizeCode(code)
	slog.InfoContext(ctx, "운영자가 쿠폰을 멈췄다", slog.String("operation", "coupon.stop"), slog.String("code", normalized))
	fmt.Fprintf(out, "멈췄습니다: %s. 이미 받은 실버는 그대로입니다\n", normalized)
	return nil
}

// printCoupon 은 쿠폰 하나를 한 줄로 찍는다.
func printCoupon(out io.Writer, c coupon.Coupon) {
	limit := "한도 없음"
	if c.MaxRedemptions > 0 {
		limit = fmt.Sprintf("%d명까지", c.MaxRedemptions)
	}
	days := "기본 기한"
	if c.SilverDays > 0 {
		days = fmt.Sprintf("%d일 뒤 사라짐", c.SilverDays)
	}
	state := "열림"
	if c.StoppedAt != nil {
		state = "멈춤"
	}
	fmt.Fprintf(out, "%s · 실버 %s(%s) · %s ~ %s · 받은 사람 %d명(%s) · %s · %s\n",
		c.Code, c.Silver, days, c.StartsAt.In(korea).Format(dateLayout), c.EndsAt.In(korea).AddDate(0, 0, -1).Format(dateLayout),
		c.Redemptions, limit, state, c.Reason)
}

// defaultOperator 는 -by 를 적지 않았을 때 만든 사람으로 적을 이름이다. 이 PC 의 계정 이름을 쓴다.
func defaultOperator() string {
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
