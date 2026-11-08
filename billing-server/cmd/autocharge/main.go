// billing-server/cmd/autocharge/main.go

// 자동 충전의 결제 작업(#980). 골드가 기준 아래로 떨어져 적어 둔 일을 등록한 카드(빌링키)로 결제한다. 서버와 따로 띄우는 프로세스다.
//
//	go run ./cmd/autocharge              10초마다 한 바퀴 돈다. Ctrl+C(또는 SIGTERM)로 끈다
//	go run ./cmd/autocharge -once        한 바퀴만 돌고, 한 일을 화면에 찍고 끝난다
//	go run ./cmd/autocharge -interval 30s -limit 50
//
// 일을 적는 것은 서버다(홀드가 골드를 뺄 때). 이 작업은 결제 대행사를 부른다. 그래서 대사처럼 결제 대행사의 설정을 읽는다(config.LoadAutoCharge).
// compose 는 billing-autocharge 로 띄운다. 바퀴가 성공할 때마다 심장박동(HEARTBEAT_FILE)의 시각을 바꾸고, healthcheck 가 그것을 본다.
// 서버와 정리 작업은 결제 대행사의 키 없이도 돈다. 키를 가진 프로세스를 늘리지 않으려고 결제를 이 작업에 모았다.
//
// 바퀴 하나가 작업 하나다(job_id). 바퀴가 실패해도 끄지 않는다. 둘을 띄워도 같은 일을 두 번 결제하지 않는다
// (일을 잠그고 임대를 걸며, 결제 대행사에 같은 멱등키를 보낸다). 그래도 하나면 충분하다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

const (
	// operation 은 바퀴 하나의 이름이다. 로그의 operation 칸에 적힌다.
	operation = "autocharge.run"
	// defaultInterval 은 바퀴 사이의 시간이다. 떨어진 뒤 늦어도 이만큼 뒤에 결제한다.
	defaultInterval = 10 * time.Second
	// minInterval 은 받는 가장 짧은 간격이다.
	minInterval = time.Second
	// defaultLimit 은 한 바퀴에 결제하는 가장 많은 수다. 하나에 결제 대행사를 한 번 부르므로 작게 둔다.
	defaultLimit = 50
	// metricsProcess 는 메트릭의 label instance 앞에 붙는 이 프로세스의 이름이다.
	metricsProcess = "autocharge"
)

// options 는 명령 줄에서 받는 것이다.
type options struct {
	interval time.Duration
	once     bool
	limit    int
}

// rounder 는 한 바퀴를 도는 것이다. *autocharge.Service 가 이 모양이다.
type rounder interface {
	ChargeRound(ctx context.Context, limit int) (autocharge.ChargeResult, error)
}

func main() {
	slog.SetDefault(obs.NewLogger(os.Stderr, obs.ServiceInfo{Service: obs.ServiceName}, slog.LevelInfo))
	if err := run(os.Args[1:], os.Stdout); err != nil {
		slog.Error("자동 충전의 결제 작업을 끝내지 못했습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorCode, jobs.ErrorCodeFailed),
			slog.String(obs.FieldErrorMessage, err.Error()),
		)
		os.Exit(1)
	}
}

// run 은 명령 줄과 설정을 읽고, 한 바퀴 또는 끌 때까지 돈다.
func run(args []string, out io.Writer) error {
	opts, err := parseOptions(args)
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.LoadAutoCharge(os.LookupEnv)
	if err != nil {
		return err
	}
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	meters, err := app.StartMetrics(ctx, os.LookupEnv, settings.Logging, metricsProcess)
	if err != nil {
		return err
	}
	defer app.CloseMetrics(meters)
	tracer, err := app.StartTracing(ctx, os.LookupEnv, settings.Logging, metricsProcess)
	if err != nil {
		return err
	}
	defer app.CloseTracing(tracer)
	if err := jobs.Measure(meters.Meter()); err != nil {
		return err
	}
	pool, err := database.NewMeteredPool(ctx, settings.Database.URL, settings.Database.Schema, database.JobLimits, meters.Meter())
	if err != nil {
		return err
	}
	defer pool.Close()
	services, err := app.NewServices(pool, settings.Rules, app.NewProviders(settings.Payment), time.Now)
	if err != nil {
		return err
	}
	// 자동 충전으로 paid 가 된 주문과 넣은 골드를 센다
	if err := app.MeasureServices(services, meters.Meter()); err != nil {
		return err
	}
	cards := app.NewCards(settings.Payment)
	charger := autocharge.NewService(pool, time.Now, cards, services.Eligibility).WithCharging(cards, services.Orders)
	// 충전할 일을 끝낸 결과(결제됨, 거절, 그만둠과 그 까닭, 다시 보낼 것)를 센다
	if err := charger.Measure(meters.Meter()); err != nil {
		return err
	}

	if opts.once {
		result, err := round(ctx, charger, opts.limit)
		printResult(out, result)
		return err
	}
	slog.InfoContext(ctx, "자동 충전의 결제 작업을 시작합니다",
		slog.String(obs.FieldOperation, operation),
		slog.Int64("interval_ms", opts.interval.Milliseconds()),
	)
	loop(ctx, charger, opts.interval, opts.limit, settings.HeartbeatFile)
	return nil
}

// parseOptions 는 명령 줄을 읽는다.
func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("autocharge", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var opts options
	flags.DurationVar(&opts.interval, "interval", defaultInterval, "바퀴 사이의 시간")
	flags.BoolVar(&opts.once, "once", false, "한 바퀴만 돈다")
	flags.IntVar(&opts.limit, "limit", defaultLimit, "한 바퀴에 결제하는 가장 많은 수")
	if err := flags.Parse(args); err != nil {
		return options{}, fmt.Errorf("%w\n쓰는 법: go run ./cmd/autocharge [-once] [-interval 10s] [-limit 50]", err)
	}
	if flags.NArg() > 0 {
		return options{}, errors.New("모르는 글자가 있습니다: " + flags.Arg(0))
	}
	if opts.interval < minInterval {
		return options{}, fmt.Errorf("-interval 은 %s 이상이어야 합니다", minInterval)
	}
	if opts.limit <= 0 {
		return options{}, errors.New("-limit 은 1 이상이어야 합니다")
	}
	return opts, nil
}

// loop 는 ctx 가 끝날 때까지 interval 마다 한 바퀴씩 돈다. 바퀴가 실패해도 멈추지 않는다.
// 바퀴가 성공하면 심장박동(heartbeat 파일)의 시각을 바꾼다. 실패한 바퀴(DB 에 닿지 못한 것)는 바꾸지 않는다.
// 결제 대행사가 답하지 않은 것은 바퀴의 실패가 아니다(일을 미뤄 두고 다음에 다시 보낸다).
func loop(ctx context.Context, charger rounder, interval time.Duration, limit int, heartbeat string) {
	for {
		// 실패는 바퀴가 이미 남겼다. 다음 바퀴에 다시 한다
		if _, err := round(ctx, charger, limit); err == nil {
			beat(ctx, heartbeat)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval):
		}
	}
}

// round 는 한 바퀴를 작업 하나로 돈다. 한 일이 있으면 그 수를 info 로 남긴다.
func round(ctx context.Context, charger rounder, limit int) (autocharge.ChargeResult, error) {
	var result autocharge.ChargeResult
	err := jobs.Run(ctx, operation, func(ctx context.Context) error {
		var err error
		result, err = charger.ChargeRound(ctx, limit)
		if result.Any() {
			slog.InfoContext(ctx, "자동 충전을 결제했습니다",
				slog.String(obs.FieldOperation, operation),
				slog.Int("paid", result.Paid),
				slog.Int("declined", result.Declined),
				slog.Int("skipped", result.Skipped),
				slog.Int("retried", result.Retried),
				slog.Int("looked_up", result.LookedUp),
				slog.Int("queued", result.Queued),
			)
		}
		return err
	})
	return result, err
}

// beat 는 심장박동을 남긴다. 남기지 못해도 결제 작업은 멈추지 않는다. healthcheck 가 unhealthy 로 알린다.
func beat(ctx context.Context, heartbeat string) {
	if err := jobs.Beat(heartbeat); err != nil {
		slog.WarnContext(ctx, "심장박동 파일을 바꾸지 못했습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorType, fmt.Sprintf("%T", err)),
		)
	}
}

// printResult 는 -once 로 돌았을 때 한 일을 사람이 읽게 찍는다.
func printResult(out io.Writer, result autocharge.ChargeResult) {
	fmt.Fprintf(out, "결제함: %d\n거절됨: %d\n그만둠: %d\n다시 보낼 것: %d\n주문 번호로 조회함: %d\n",
		result.Paid, result.Declined, result.Skipped, result.Retried, result.LookedUp)
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호와 결제 대행사의 키가 들어 있다
		slog.Warn(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
