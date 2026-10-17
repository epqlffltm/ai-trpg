// billing-server/cmd/pricereviews/main.go

// 공급사 가격 변경의 할 일을 적고 보는 명령. 운영자가 쓴다. 서버와 같은 설정(.env 의 DATABASE_URL, DB_SCHEMA)을 읽는다.
//
//	go run ./cmd/pricereviews list [-all]                                   남은 할 일(-all 이면 끝낸 것과 닫은 것도)
//	go run ./cmd/pricereviews add "<무엇>" -at <시각> [-note "<출처>"]      공급사가 그 시각에 값을 바꾼다고 적는다
//	go run ./cmd/pricereviews done <번호> <announce|notice|final> [-note "<글>"]   할 일 하나를 끝냈다고 적는다
//	go run ./cmd/pricereviews cancel <번호> -note "<이유>"                  닫는다(공급사가 거둬들였거나 잘못 적었다)
//
// 공급사가 값을 바꾸는 시각을 기준으로 할 일이 셋이다. 하루 한 번 도는 대사(cmd/reconcile)가 때가 된 것을 경고한다.
//
//	announce  D-30  첫 공지
//	notice    D-14  자세한 공지, 그리고 새 값을 가격표에 미래 시각으로 넣는다(cmd/prices set -at, import)
//	final     D-1   마지막 알림
//
// -at 은 RFC 3339(예: 2026-11-21T00:00:00+09:00)다. 시간대까지 적는다. 공급사의 공지가 UTC 면 Z 로 적는다.
// -by <이름>으로 적은 사람을 남긴다. 적지 않으면 "cli:<이 PC 의 계정 이름>"이다.
// 이 명령은 가격표를 바꾸지 않는다. 할 일을 적을 뿐이다. 고치거나 지우는 명령은 없다. 잘못 적었으면 cancel 로 닫고 다시 적는다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/pricereviews list [-all]
  go run ./cmd/pricereviews add "<무엇>" -at <시각> [-note "<출처>"] [-by <이름>]
  go run ./cmd/pricereviews done <번호> <announce|notice|final> [-note "<글>"] [-by <이름>]
  go run ./cmd/pricereviews cancel <번호> -note "<이유>" [-by <이름>]`

// timeLayout 은 화면에 시각을 찍는 모양이다. 이 PC 의 시간대로 찍는다.
const timeLayout = "2006-01-02 15:04:05 -07:00"

// request 는 명령 줄에서 읽은 일 하나다.
type request struct {
	action  string
	id      int64
	step    pricereview.Step
	subject string
	at      time.Time
	note    string
	by      string
	all     bool
}

// reviews 는 이 명령이 쓰는 할 일의 모양이다. *pricereview.Service 가 이 모양이다.
type reviews interface {
	Add(ctx context.Context, draft pricereview.Draft) (pricereview.Review, error)
	Done(ctx context.Context, id int64, step pricereview.Step, by string, note string) (pricereview.Review, error)
	Cancel(ctx context.Context, id int64, by string, reason string) (pricereview.Review, error)
	List(ctx context.Context, all bool) ([]pricereview.Review, error)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("가격 변경 할 일을 다루지 못했습니다: %v", err)
	}
}

// run 은 명령을 읽고, 설정을 읽고, 할 일에 그 일을 한다.
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
	pool, err := database.NewPool(ctx, target.URL, target.Schema, database.JobLimits)
	if err != nil {
		return err
	}
	defer pool.Close()

	fmt.Fprintf(out, "스키마: %s\n", target.Schema)
	return do(ctx, pricereview.NewService(pool, time.Now), req, out, time.Now())
}

// parse 는 명령 줄을 읽는다. 옵션(-note 같은 것)은 낱말의 앞에 와도 뒤에 와도 된다.
func parse(args []string, changer string) (request, error) {
	flags := flag.NewFlagSet("pricereviews", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	req := request{}
	var at string
	flags.StringVar(&req.note, "note", "", "덧붙이는 글(출처, 공지의 주소, 닫는 이유)")
	flags.StringVar(&req.by, "by", changer, "적은 사람")
	flags.StringVar(&at, "at", "", "공급사가 값을 바꾸는 시각(RFC 3339)")
	flags.BoolVar(&req.all, "all", false, "list 에서 끝낸 것과 닫은 것도 보인다")
	words, err := parseInterleaved(flags, args)
	if err != nil {
		return request{}, errors.New(usage)
	}
	if req, err = readWords(req, words); err != nil {
		return request{}, err
	}
	if err := checkOptions(req, at); err != nil {
		return request{}, err
	}
	if req.action == "add" {
		if req.at, err = time.Parse(time.RFC3339, at); err != nil {
			return request{}, errors.New("-at 은 2026-11-21T00:00:00+09:00 모양이어야 합니다")
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

// readWords 는 옵션이 아닌 낱말들(일, 번호, 할 일, 무엇)을 읽는다.
func readWords(req request, words []string) (request, error) {
	var err error
	switch {
	case len(words) == 1 && words[0] == "list":
		req.action = "list"
	case len(words) == 2 && words[0] == "add":
		req.action, req.subject = "add", words[1]
	case len(words) == 3 && words[0] == "done":
		req.action, req.step = "done", pricereview.Step(words[2])
		req.id, err = readID(words[1])
	case len(words) == 2 && words[0] == "cancel":
		req.action = "cancel"
		req.id, err = readID(words[1])
	default:
		return request{}, errors.New(usage)
	}
	return req, err
}

// readID 는 할 일의 번호를 읽는다.
func readID(word string) (int64, error) {
	id, err := strconv.ParseInt(word, 10, 64)
	if err != nil || id <= 0 {
		return 0, errors.New("번호는 1 이상의 정수여야 합니다(list 의 #3 이면 3).\n" + usage)
	}
	return id, nil
}

// checkOptions 는 그 일에 꼭 있어야 하는 옵션과 쓰지 않는 옵션을 본다.
// 붙여도 아무 일도 하지 않는 옵션을 조용히 넘기면, 쓴 사람은 적용된 줄 안다.
func checkOptions(req request, at string) error {
	switch {
	case req.action == "add" && at == "":
		return errors.New("-at 으로 공급사가 값을 바꾸는 시각을 적어야 합니다.\n" + usage)
	case req.action != "add" && at != "":
		return errors.New("-at 은 add 에만 씁니다.\n" + usage)
	case req.action == "cancel" && req.note == "":
		return errors.New("-note 로 닫는 이유를 적어야 합니다.\n" + usage)
	case req.action == "list" && req.note != "":
		return errors.New("-note 는 list 에 쓰지 않습니다.\n" + usage)
	case req.action != "list" && req.all:
		return errors.New("-all 은 list 에만 씁니다.\n" + usage)
	}
	return nil
}

// do 는 읽은 일을 하고 결과를 찍는다. now 는 남은 날을 셀 때 쓴다.
func do(ctx context.Context, list reviews, req request, out io.Writer, now time.Time) error {
	switch req.action {
	case "list":
		found, err := list.List(ctx, req.all)
		return printReviews(out, found, now, err)
	case "add":
		added, err := list.Add(ctx, pricereview.Draft{Subject: req.subject, ChangesAt: req.at, Note: req.note, CreatedBy: req.by})
		return printReviews(out, []pricereview.Review{added}, now, err)
	case "done":
		marked, err := list.Done(ctx, req.id, req.step, req.by, req.note)
		return printReviews(out, []pricereview.Review{marked}, now, err)
	default:
		closed, err := list.Cancel(ctx, req.id, req.by, req.note)
		return printReviews(out, []pricereview.Review{closed}, now, err)
	}
}

// printReviews 는 할 일들을 찍는다. err 가 있으면 찍지 않고 돌려준다.
func printReviews(out io.Writer, found []pricereview.Review, now time.Time, err error) error {
	if err != nil {
		return err
	}
	if len(found) == 0 {
		fmt.Fprintln(out, "남은 할 일이 없습니다")
	}
	for _, review := range found {
		printReview(out, review, now)
	}
	return nil
}

// stepNames 는 할 일을 사람이 읽는 이름이다. 차례대로다.
var stepNames = []struct {
	step pricereview.Step
	name string
}{
	{pricereview.StepAnnounce, "첫 공지(D-30)"},
	{pricereview.StepNotice, "자세한 공지와 새 값 예약(D-14)"},
	{pricereview.StepFinal, "마지막 알림(D-1)"},
}

// printReview 는 할 일 하나를 여러 줄로 찍는다. 첫 줄은 무엇이 언제 바뀌는지, 다음 줄들은 할 일마다다.
func printReview(out io.Writer, review pricereview.Review, now time.Time) {
	fmt.Fprintf(out, "#%d  %s  %s 에 바뀜 (%s)\n", review.ID, review.Subject, review.ChangesAt.Local().Format(timeLayout),
		dayLabel(pricereview.DaysUntil(review.ChangesAt, now)))
	if review.Note != "" {
		fmt.Fprintf(out, "    메모: %s\n", review.Note)
	}
	for _, s := range stepNames {
		fmt.Fprintf(out, "    %-8s %s  %s\n", s.step, s.name, stepState(review, s.step, now))
	}
	if review.Cancelled != nil {
		fmt.Fprintf(out, "    닫음: %s\n", formatMark(*review.Cancelled))
	}
}

// stepState 는 할 일 하나의 지금 상태다. 끝냈으면 언제 누가, 아니면 언제부터 할 일인지다.
func stepState(review pricereview.Review, step pricereview.Step, now time.Time) string {
	if mark, done := review.Done[step]; done {
		return "끝냄 " + formatMark(mark)
	}
	startsAt, _ := pricereview.StartOf(step, review.ChangesAt)
	if now.Before(startsAt) {
		return startsAt.Local().Format(timeLayout) + " 부터"
	}
	return "할 때가 됨 (" + startsAt.Local().Format(timeLayout) + " 부터)"
}

// formatMark 는 표시 하나를 사람이 읽는 글로 바꾼다.
func formatMark(mark pricereview.Mark) string {
	text := mark.MarkedAt.Local().Format(timeLayout) + " " + mark.MarkedBy
	if mark.Note != "" {
		text += " — " + mark.Note
	}
	return text
}

// dayLabel 은 남은 날을 D-14 처럼 쓴다. 공급사가 이미 값을 바꿨으면 "바뀐 뒤 N일"이다.
func dayLabel(daysLeft int) string {
	if daysLeft > 0 {
		return fmt.Sprintf("D-%d", daysLeft)
	}
	return fmt.Sprintf("바뀐 뒤 %d일", -daysLeft)
}

// defaultChanger 는 -by 를 적지 않았을 때 적은 사람으로 남길 이름이다. 이 PC 의 계정 이름을 쓴다.
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
