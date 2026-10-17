// billing-server/cmd/sweeper/main.go

// 정리 작업. 끝이 열린 것을 닫는다. 서버와 따로 띄우는 프로세스다.
//
//	go run ./cmd/sweeper              30초마다 한 바퀴 돈다. Ctrl+C(또는 SIGTERM)로 끈다
//	go run ./cmd/sweeper -once        한 바퀴만 돌고, 정리한 수를 화면에 찍고 끝난다
//	go run ./cmd/sweeper -interval 1m -limit 200
//
// 한 바퀴에 하는 일: 만료된 홀드를 돌려주고, 사라진 무료 크레딧을 원장에 적고, 만료된 주문을 끝내고, 보호자에게 알릴 결제를 보낸다(internal/sweep).
// 서버와 같은 설정(.env)을 읽는다. 다만 포트, 공개키 주소, 서명의 비밀, 결제 대행사의 키는 없어도 돈다(config.LoadSweeper).
// 미성년자의 결제를 보호자에게 알리라고 인증 서버에 보낸다(AUTH_SERVER_SECRET 이 있을 때, #352).
// 결제 대행사를 부르지 않는다. 주문 서비스에는 부르면 오류를 내는 것을 끼운다(app.NoProviders).
//
// 바퀴 하나가 작업 하나다(job_id). 바퀴가 실패해도 끄지 않는다. 그 바퀴를 error 로 남기고 다음 바퀴에 다시 한다.
// 둘을 띄워도 같은 것을 두 번 정리하지 않는다. 그래도 하나면 충분하다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/guardiannotice"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/jobs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/sweep"
)

const (
	// operation 은 바퀴 하나의 이름이다. 로그의 operation 칸에 적힌다.
	operation = "sweep.run"
	// defaultInterval 은 바퀴 사이의 시간이다. 홀드와 주문의 기한(하루)에 견주면 짧아서 늦어도 30초다.
	defaultInterval = 30 * time.Second
	// minInterval 은 받는 가장 짧은 간격이다. 더 짧으면 할 일이 없을 때도 DB 를 쉬지 않고 두드린다.
	minInterval = time.Second
)

// options 는 명령 줄에서 받는 것이다.
type options struct {
	interval time.Duration
	once     bool
	limit    int
}

// rounder 는 한 바퀴를 도는 것이다. *sweep.Sweeper 가 이 모양이다.
type rounder interface {
	Round(ctx context.Context) (sweep.Result, error)
}

func main() {
	slog.SetDefault(obs.NewLogger(os.Stderr, obs.ServiceInfo{Service: obs.ServiceName}, slog.LevelInfo))
	if err := run(os.Args[1:], os.Stdout); err != nil {
		slog.Error("정리 작업을 끝내지 못했습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorCode, jobs.ErrorCodeFailed),
			slog.String(obs.FieldErrorMessage, err.Error()),
		)
		os.Exit(1)
	}
}

// run 은 명령 줄과 설정을 읽고, 정리 작업을 한 바퀴 또는 끌 때까지 돈다.
func run(args []string, out io.Writer) error {
	opts, err := parseOptions(args)
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.LoadSweeper(os.LookupEnv)
	if err != nil {
		return err
	}
	slog.SetDefault(app.NewLogger(os.Stderr, settings.Logging))

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	pool, err := database.NewPool(ctx, settings.Database.URL, settings.Database.Schema, database.JobLimits)
	if err != nil {
		return err
	}
	defer pool.Close()
	services, err := app.NewServices(pool, settings.Rules, app.NoProviders(), time.Now)
	if err != nil {
		return err
	}
	sweeper := sweep.New(services.Holds, services.Wallet, services.Orders, opts.limit).
		WithNotices(guardiannotice.NewService(pool, time.Now, noticeSender(settings.GuardianNotices)))

	if opts.once {
		result, err := round(ctx, sweeper)
		printResult(out, result)
		return err
	}
	slog.InfoContext(ctx, "정리 작업을 시작합니다",
		slog.String(obs.FieldOperation, operation),
		slog.Int64("interval_ms", opts.interval.Milliseconds()),
	)
	loop(ctx, sweeper, opts.interval, settings.HeartbeatFile)
	return nil
}

// noticeSender 는 보호자 알림을 인증 서버에 보내는 것을 만든다. 보낼 곳이나 비밀이 없으면 nil 이다(적기만 한다).
func noticeSender(settings config.GuardianNotices) guardiannotice.Sender {
	if !settings.Enabled() {
		slog.Warn("인증 서버의 알림 주소나 AUTH_SERVER_SECRET 이 없습니다. 보호자에게 알릴 결제를 적기만 하고 보내지 않습니다",
			slog.String(obs.FieldOperation, operation),
		)
		return nil
	}
	return guardiannotice.NewHTTPSender(settings.URL, settings.Secret, time.Now)
}

// parseOptions 는 명령 줄을 읽는다.
func parseOptions(args []string) (options, error) {
	flags := flag.NewFlagSet("sweeper", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var opts options
	flags.DurationVar(&opts.interval, "interval", defaultInterval, "바퀴 사이의 시간")
	flags.BoolVar(&opts.once, "once", false, "한 바퀴만 돈다")
	flags.IntVar(&opts.limit, "limit", sweep.DefaultLimit, "한 바퀴에 종류마다 다루는 가장 많은 수")
	if err := flags.Parse(args); err != nil {
		return options{}, fmt.Errorf("%w\n쓰는 법: go run ./cmd/sweeper [-once] [-interval 30s] [-limit 500]", err)
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
// 바퀴 도중에 끄라는 신호가 오면 그 바퀴의 남은 일을 하지 않는다. 바뀐 것은 줄 하나씩 끝난 것이라 반쯤 된 것은 없다.
// 바퀴가 성공하면 심장박동(heartbeat 파일)의 시각을 바꾼다. 실패한 바퀴(DB 에 닿지 못한 것)는 바꾸지 않는다.
func loop(ctx context.Context, sweeper rounder, interval time.Duration, heartbeat string) {
	for {
		// 실패는 바퀴가 이미 남겼다. 다음 바퀴에 다시 한다
		if _, err := round(ctx, sweeper); err == nil {
			beat(ctx, heartbeat)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(interval):
		}
	}
}

// round 는 한 바퀴를 작업 하나로 돈다. 정리한 것이 있으면 그 수를 info 로 남긴다.
func round(ctx context.Context, sweeper rounder) (sweep.Result, error) {
	var result sweep.Result
	err := jobs.Run(ctx, operation, func(ctx context.Context) error {
		var err error
		result, err = sweeper.Round(ctx)
		if result.Any() {
			slog.InfoContext(ctx, "만료된 것을 정리했습니다",
				slog.String(obs.FieldOperation, operation),
				slog.Int("expired_holds", result.Holds),
				slog.Int("expired_free_credit_users", result.FreeCreditUsers),
				slog.Int("expired_orders", result.Orders),
				slog.Int("guardian_notices_queued", result.Notices.Queued),
				slog.Int("guardian_notices_sent", result.Notices.Sent),
				slog.Int("guardian_notices_retried", result.Notices.Retried),
			)
		}
		return err
	})
	return result, err
}

// beat 는 심장박동을 남긴다. 남기지 못해도 정리 작업은 멈추지 않는다. healthcheck 가 unhealthy 로 알린다.
func beat(ctx context.Context, heartbeat string) {
	if err := jobs.Beat(heartbeat); err != nil {
		slog.WarnContext(ctx, "심장박동 파일을 바꾸지 못했습니다",
			slog.String(obs.FieldOperation, operation),
			slog.String(obs.FieldErrorType, fmt.Sprintf("%T", err)),
		)
	}
}

// printResult 는 -once 로 돌았을 때 정리한 수를 사람이 읽게 찍는다.
func printResult(out io.Writer, result sweep.Result) {
	fmt.Fprintf(out, "돌려준 홀드: %d\n무료 크레딧을 정리한 사용자: %d\n끝낸 주문: %d\n보호자 알림: 적음 %d, 보냄 %d, 다시 보낼 것 %d\n",
		result.Holds, result.FreeCreditUsers, result.Orders,
		result.Notices.Queued, result.Notices.Sent, result.Notices.Retried)
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		slog.Warn(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
