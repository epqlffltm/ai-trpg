// billing-server/cmd/reconcile/main.go

// 대사(對査). 하루 한 번 돌리는 명령이다. 한 번 돌고 끝난다. 예약은 밖(cron, 스케줄러)에서 건다.
//
//	go run ./cmd/reconcile
//	go run ./cmd/reconcile -stale-after 30m -stuck-after 24h -limit 500
//
// 하는 일(internal/reconcile):
//  1. 오래 confirming·refunding 에 머문 주문을 결제 대행사에 물어 끝낸다. 이것만 상태를 바꾼다.
//  2. 지갑, 지급 묶음, 주문, 홀드가 원장과 맞는지 본다. 읽기만 한다. 고치지 않는다.
//  3. 정리 작업(cmd/sweeper)이 밀려 있지 않은지 센다.
//  4. 1 을 하고도 하루 넘게 결과를 모르는 주문을 찾는다. 사람이 확인하고 cmd/orders 로 결과를 정한다.
//
// 끝 코드로 결과를 알린다. 예약한 쪽이 이것으로 경보를 건다.
//
//	0  장부가 맞다
//	1  맞지 않는 줄이 있다. 줄마다 error(ledger.mismatch) 로 남긴다. 사람이 봐야 한다
//	2  끝내지 못했다(설정, DB, 결제 대행사). 다음에 다시 돌린다
//	3  장부는 맞는데, 결과를 끝내 모르는 주문이 있다. 주문마다 warning(order.stuck) 로 남긴다. 사람이 결과를 정한다
//
// 여럿이면 앞의 것을 알린다(1, 2, 3 의 차례). 장부가 틀린 것이 가장 급하다.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/reconcile"
)

const (
	// operation 은 대사 한 번의 이름이다. 로그의 operation 칸에 적힌다.
	operation = "reconcile.run"
	// 대사가 남기는 오류 코드. docs/observability.md 의 표에 있다.
	errorCodeMismatch = "ledger.mismatch"
	errorCodeBehind   = "sweep.behind"
	errorCodeStuck    = "order.stuck"
	// defaultStaleAfter 는 confirming·refunding 에 이만큼 머문 주문을 결제 대행사에 묻는다.
	// 승인·취소 요청 하나는 길어야 몇십 초다(order.ProviderTimeout). 그보다 넉넉히 둬서 진행 중인 요청과 엇갈리지 않게 한다.
	defaultStaleAfter = 10 * time.Minute
	minStaleAfter     = time.Minute
)

// 끝 코드.
const (
	exitClean    = 0
	exitMismatch = 1
	exitFailed   = 2
	// exitNeedsPerson 은 장부는 맞는데 사람이 결과를 정할 주문이 있다는 것이다.
	exitNeedsPerson = 3
)

// options 는 명령 줄에서 받는 것이다.
type options struct {
	staleAfter time.Duration
	stuckAfter time.Duration
	limit      int
}

// runner 는 대사를 한 번 하는 것이다. *reconcile.Reconciler 가 이 모양이다.
type runner interface {
	Run(ctx context.Context, options reconcile.Options) (reconcile.Report, error)
}

func main() {
	slog.SetDefault(obs.NewLogger(os.Stderr, obs.ServiceInfo{Service: obs.ServiceName}, slog.LevelInfo))
	os.Exit(run(os.Args[1:], os.Stdout))
}

// run 은 명령 줄과 설정을 읽고 대사를 한 번 한 뒤 끝 코드를 돌려준다.
func run(args []string, out io.Writer) int {
	opts, err := parseOptions(args)
	if err != nil {
		fmt.Fprintln(out, err)
		return exitFailed
	}
	loadDotEnv()
	settings, err := config.LoadJobs(os.LookupEnv)
	if err != nil {
		logStartFailed(err)
		return exitFailed
	}
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	pool, err := database.NewPool(ctx, settings.Database.URL, settings.Database.Schema)
	if err != nil {
		logStartFailed(err)
		return exitFailed
	}
	defer pool.Close()
	services, err := app.NewServices(pool, settings.Rules, app.NewProvider(settings.Payment), time.Now)
	if err != nil {
		logStartFailed(err)
		return exitFailed
	}

	report, err := once(ctx, reconcile.New(pool, services.Orders, time.Now), opts)
	printReport(out, report, err)
	return exitCode(report, err)
}

// parseOptions 는 명령 줄을 읽는다.
func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("reconcile", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var opts options
	flags.DurationVar(&opts.staleAfter, "stale-after", defaultStaleAfter, "confirming·refunding 에 이만큼 머문 주문을 결제 대행사에 묻는다")
	flags.DurationVar(&opts.stuckAfter, "stuck-after", order.StuckAfter, "결과를 모르는 채로 이만큼 지난 주문을 사람이 볼 주문으로 센다")
	flags.IntVar(&opts.limit, "limit", reconcile.DefaultLimit, "검사마다 돌려주는 가장 많은 수")
	if err := flags.Parse(args); err != nil {
		return options{}, fmt.Errorf("%w\n쓰는 법: go run ./cmd/reconcile [-stale-after 10m] [-stuck-after 24h] [-limit 1000]", err)
	}
	if flags.NArg() > 0 {
		return options{}, errors.New("모르는 글자가 있습니다: " + flags.Arg(0))
	}
	if opts.staleAfter < minStaleAfter {
		return options{}, fmt.Errorf("-stale-after 는 %s 이상이어야 합니다", minStaleAfter)
	}
	if opts.stuckAfter <= opts.staleAfter {
		// 결제 대행사에 한 번도 묻지 않은 주문을 사람에게 넘기지 않는다
		return options{}, errors.New("-stuck-after 는 -stale-after 보다 길어야 합니다")
	}
	if opts.limit <= 0 {
		return options{}, errors.New("-limit 은 1 이상이어야 합니다")
	}
	return opts, nil
}

// once 는 대사를 작업 하나로 한 번 하고, 결과를 로그에 남긴다.
func once(ctx context.Context, reconciler runner, opts options) (reconcile.Report, error) {
	var report reconcile.Report
	err := jobs.Run(ctx, operation, func(ctx context.Context) error {
		var err error
		report, err = reconciler.Run(ctx, reconcile.Options{StaleAfter: opts.staleAfter, StuckAfter: opts.stuckAfter, Limit: opts.limit})
		logReport(ctx, report)
		return err
	})
	return report, err
}

// logReport 는 대사의 결과를 남긴다. 맞지 않는 줄은 하나씩 error 로, 밀린 정리는 warning 으로 남긴다.
func logReport(ctx context.Context, report reconcile.Report) {
	if report.Stale.Found > 0 {
		slog.InfoContext(ctx, "오래된 주문을 결제 대행사에 물어 끝냈습니다",
			slog.String(obs.FieldOperation, operation),
			slog.Int("stale_found", report.Stale.Found),
			slog.Int("stale_paid", report.Stale.Paid),
			slog.Int("stale_failed", report.Stale.Failed),
			slog.Int("stale_refunded", report.Stale.Refunded),
			slog.Int("stale_refund_refused", report.Stale.RefundRefused),
			slog.Int("stale_unknown", report.Stale.Unknown),
			slog.Int("stale_errored", report.Stale.Errored),
		)
	}
	for _, mismatch := range report.Mismatches {
		slog.ErrorContext(ctx, "장부가 원장과 맞지 않습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorCode, errorCodeMismatch),
			slog.String("check", mismatch.Check),
			slog.String("record_id", mismatch.ID),
		)
	}
	for _, stuck := range report.Stuck {
		// 결제 번호는 적지 않는다. 상점관리자에서는 주문 번호로 찾는다
		slog.WarnContext(ctx, "결과를 모르는 채로 하루가 지난 주문입니다. 사람이 확인해야 합니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorCode, errorCodeStuck),
			slog.String("order_id", stuck.ID.String()),
			slog.String("status", string(stuck.Status)),
			slog.Time("since", stuck.UpdatedAt),
		)
	}
	if report.Overdue.Any() {
		slog.WarnContext(ctx, "정리 작업이 밀려 있습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorCode, errorCodeBehind),
			slog.Int64("overdue_holds", report.Overdue.Holds),
			slog.Int64("overdue_orders", report.Overdue.Orders),
			slog.Int64("overdue_free_grants", report.Overdue.FreeGrants),
		)
	}
}

// printReport 는 결과를 사람이 읽게 찍는다. 번호는 찍지 않는다. 번호는 로그에 있다.
func printReport(out io.Writer, report reconcile.Report, err error) {
	fmt.Fprintf(out, "오래된 주문: %d (치름 %d, 실패 %d, 환불 %d, 환불 거절 %d, 아직 모름 %d, 오류 %d)\n",
		report.Stale.Found, report.Stale.Paid, report.Stale.Failed, report.Stale.Refunded, report.Stale.RefundRefused,
		report.Stale.Unknown, report.Stale.Errored)
	fmt.Fprintf(out, "맞지 않는 줄: %d\n", len(report.Mismatches))
	fmt.Fprintf(out, "밀린 정리: 홀드 %d, 주문 %d, 무료 크레딧 묶음 %d\n",
		report.Overdue.Holds, report.Overdue.Orders, report.Overdue.FreeGrants)
	printStuck(out, report.Stuck)
	if err != nil {
		fmt.Fprintln(out, "끝내지 못했습니다. 로그를 봐 주세요")
	}
}

// printStuck 은 사람이 결과를 정할 주문의 수를 찍는다. 있으면 다음에 할 일도 알린다.
func printStuck(out io.Writer, stuck []order.Order) {
	confirming, refunding := 0, 0
	for _, o := range stuck {
		if o.Status == order.StatusRefunding {
			refunding++
		} else {
			confirming++
		}
	}
	fmt.Fprintf(out, "사람이 볼 주문: %d (승인 확인 %d, 환불 확인 %d)\n", len(stuck), confirming, refunding)
	if len(stuck) > 0 {
		fmt.Fprintln(out, "go run ./cmd/orders stuck 으로 보고, 상점관리자에서 확인한 뒤 go run ./cmd/orders decide 로 정합니다")
	}
}

// exitCode 는 결과를 끝 코드로 바꾼다. 맞지 않는 줄이 있으면, 끝내지 못한 것보다 먼저 알린다.
// 사람이 볼 주문은 그 둘이 없을 때 알린다. 장부가 틀렸거나 대사가 끝나지 않았으면 그것부터 봐야 한다.
func exitCode(report reconcile.Report, err error) int {
	switch {
	case !report.Clean():
		return exitMismatch
	case err != nil:
		return exitFailed
	case report.NeedsPerson():
		return exitNeedsPerson
	default:
		return exitClean
	}
}

// logStartFailed 는 대사를 시작하지도 못한 것을 남긴다.
func logStartFailed(err error) {
	slog.Error("대사를 시작하지 못했습니다",
		slog.String(obs.FieldOperation, operation),
		slog.String(obs.FieldErrorCode, jobs.ErrorCodeFailed),
		slog.String(obs.FieldErrorMessage, err.Error()),
	)
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		slog.Warn(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
