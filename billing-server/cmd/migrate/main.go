// billing-server/cmd/migrate/main.go

// 결제 서버의 테이블을 만들고 바꾸는 명령. 서버와 같은 설정(.env 의 DATABASE_URL, DB_SCHEMA)을 읽는다.
//
//	go run ./cmd/migrate up       아직 적용하지 않은 마이그레이션을 모두 적용한다
//	go run ./cmd/migrate down     마지막으로 적용한 것 하나를 되돌린다(그 테이블의 데이터가 지워진다)
//	go run ./cmd/migrate status   파일마다 적용되어 있는지 보여 준다
//
// 접속 주소를 명령 줄에 적지 않는다. 명령 줄은 셸의 기록에 남는다.
package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"

	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/migrate"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = "쓰는 법: go run ./cmd/migrate up | down | status"

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("마이그레이션을 끝내지 못했습니다: %v", err)
	}
}

// command 는 명령 하나가 하는 일이다.
type command func(ctx context.Context, target config.Database, out io.Writer) error

// commands 는 받는 명령의 이름과 그 일이다.
var commands = map[string]command{"up": up, "down": down, "status": status}

// run 은 명령을 고르고, 설정을 읽고, 그 명령을 실행한다.
func run(args []string, out io.Writer) error {
	// 명령부터 본다. 잘못 적었으면 DB 설정을 읽기 전에 끝낸다
	if len(args) != 1 || commands[args[0]] == nil {
		return errors.New(usage)
	}
	loadDotEnv()
	target, err := config.LoadDatabase(os.LookupEnv)
	if err != nil {
		return err
	}

	// Ctrl+C 를 누르면 기다리던 일(잠금, 실행 중인 문장)을 그만둔다
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// 어느 스키마를 바꾸는지 먼저 보여 준다. 개발용과 테스트용을 헷갈리지 않게 한다
	fmt.Fprintf(out, "스키마: %s\n", target.Schema)
	return commands[args[0]](ctx, target, out)
}

// up 은 남은 마이그레이션을 적용하고 무엇을 적용했는지 적는다.
func up(ctx context.Context, target config.Database, out io.Writer) error {
	applied, err := migrate.Up(ctx, target.URL, target.Schema)
	for _, name := range applied {
		fmt.Fprintf(out, "적용: %s\n", name)
	}
	if err == nil && len(applied) == 0 {
		fmt.Fprintln(out, "적용할 것이 없습니다. 이미 최신입니다")
	}
	return err
}

// down 은 마지막 마이그레이션 하나를 되돌리고 무엇을 되돌렸는지 적는다.
func down(ctx context.Context, target config.Database, out io.Writer) error {
	name, err := migrate.Down(ctx, target.URL, target.Schema)
	if err != nil {
		return err
	}
	if name == "" {
		fmt.Fprintln(out, "되돌릴 것이 없습니다")
		return nil
	}
	fmt.Fprintf(out, "되돌림: %s\n", name)
	return nil
}

// status 는 파일마다 적용되어 있는지 적는다.
func status(ctx context.Context, target config.Database, out io.Writer) error {
	steps, err := migrate.Status(ctx, target.URL, target.Schema)
	if err != nil {
		return err
	}
	for _, step := range steps {
		fmt.Fprintf(out, "%s  %s\n", mark(step.Applied), step.Name)
	}
	return nil
}

// mark 는 적용 여부를 한 낱말로 바꾼다.
func mark(applied bool) string {
	if applied {
		return "적용됨"
	}
	return "대기  "
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		log.Printf(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
