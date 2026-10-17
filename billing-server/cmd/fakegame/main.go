// billing-server/cmd/fakegame/main.go

// 게임 서버가 되어 결제 서버의 홀드 주소와 가격 목록을 부르는 명령. 개발할 때 손으로 확인하는 데 쓴다.
//
//	go run ./cmd/fakegame hold <사용자 번호> <이름표> [가격표 이름]
//	go run ./cmd/fakegame capture <이름표>
//	go run ./cmd/fakegame release <이름표>
//	go run ./cmd/fakegame extend <이름표>
//	go run ./cmd/fakegame prices [ETag]
//
// prices 에 지난 응답의 ETag 를 주면 If-None-Match 로 실어 보낸다. 바뀐 것이 없으면 304 다.
//
// 이 주소들은 사용자의 토큰이 아니라 게임 서버의 서명을 본다. 게임 서버를 띄우지 않고 해 볼 때,
// 그 호출을 이 명령이 대신한다. 서버와 같은 설정(.env)에서 비밀과 주소를 읽어 서명해 보낸다.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/google/uuid"
	"github.com/joho/godotenv"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = `쓰는 법:
  go run ./cmd/fakegame hold <사용자 번호> <이름표> [가격표 이름]
  go run ./cmd/fakegame capture <이름표>
  go run ./cmd/fakegame release <이름표>
  go run ./cmd/fakegame extend <이름표>
  go run ./cmd/fakegame prices [ETag]`

// sendTimeout 은 서버의 답을 기다리는 가장 긴 시간이다.
const sendTimeout = 15 * time.Second

// maxAnswerBytes 는 화면에 찍을 서버의 답의 가장 큰 크기다. 가격 목록이 길어도 다 보이게 넉넉히 둔다.
const maxAnswerBytes = 64 << 10

// call 은 보낼 요청 하나다. 주소는 호스트를 뺀 경로다. 본문이 nil 이면 본문 없는 GET 이다.
type call struct {
	path string
	body map[string]string
	// ifNoneMatch 는 가격 목록에 실어 보낼 지난 응답의 ETag 다.
	ifNoneMatch string
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("요청을 보내지 못했습니다: %v", err)
	}
}

// run 은 명령을 확인하고, 설정을 읽고, 요청을 보낸다.
func run(args []string, out io.Writer) error {
	request, err := parse(args)
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.Load(os.LookupEnv)
	if err != nil {
		return err
	}
	return send(settings, request, time.Now(), out)
}

// parse 는 명령의 글자들을 보낼 요청으로 바꾼다. 서버가 볼 것(이름표의 모양, 가격표의 이름)은 여기서 보지 않는다.
func parse(args []string) (call, error) {
	const holds = httpapi.APIPrefix + "/service/holds"
	switch {
	case len(args) >= 3 && len(args) <= 4 && args[0] == "hold":
		if _, err := uuid.Parse(args[1]); err != nil {
			return call{}, errors.New("사용자 번호가 UUID 가 아닙니다.\n" + usage)
		}
		priceCode := pricing.NarrationStandard
		if len(args) == 4 {
			priceCode = args[3]
		}
		return call{path: holds, body: map[string]string{"user_id": args[1], "reference": args[2], "price_code": priceCode}}, nil
	case len(args) == 2 && args[0] == "capture":
		return call{path: holds + "/capture", body: map[string]string{"reference": args[1]}}, nil
	case len(args) == 2 && args[0] == "release":
		return call{path: holds + "/release", body: map[string]string{"reference": args[1]}}, nil
	case len(args) == 2 && args[0] == "extend":
		return call{path: holds + "/extend", body: map[string]string{"reference": args[1]}}, nil
	case len(args) >= 1 && len(args) <= 2 && args[0] == "prices":
		c := call{path: httpapi.APIPrefix + "/service/prices"}
		if len(args) == 2 {
			c.ifNoneMatch = args[1]
		}
		return c, nil
	default:
		return call{}, errors.New(usage)
	}
}

// send 는 요청의 본문을 만들어 서명하고 서버에 보낸 뒤, 서버의 답을 적는다.
func send(settings config.Settings, c call, sentAt time.Time, out io.Writer) error {
	request, err := newRequest(settings, c, sentAt)
	if err != nil {
		return err
	}

	client := &http.Client{Timeout: sendTimeout}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("서버(%s)에 닿지 못했습니다. 서버가 떠 있는지 확인해 주세요", settings.Addr())
	}
	defer response.Body.Close()
	answer, _ := io.ReadAll(io.LimitReader(response.Body, maxAnswerBytes))
	if tag := response.Header.Get("ETag"); tag != "" {
		fmt.Fprintf(out, "ETag %s\n", tag)
	}
	fmt.Fprintf(out, "%d %s\n", response.StatusCode, bytes.TrimSpace(answer))
	return nil
}

// newRequest 는 보낼 요청을 만들고 게임 서버처럼 서명한다. 본문이 있으면 POST, 없으면 GET 이다.
func newRequest(settings config.Settings, c call, sentAt time.Time) (*http.Request, error) {
	method, body := http.MethodGet, []byte{}
	if c.body != nil {
		encoded, err := json.Marshal(c.body)
		if err != nil {
			return nil, err
		}
		method, body = http.MethodPost, encoded
	}
	request, err := http.NewRequest(method, "http://"+settings.Addr()+c.path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	if c.body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if c.ifNoneMatch != "" {
		request.Header.Set("If-None-Match", c.ifNoneMatch)
	}
	// 서명하는 주소는 호스트를 뺀 경로다. 서버가 받은 주소에서 같은 글자를 꺼낸다
	request.Header.Set(serviceauth.SignatureHeader, serviceauth.Sign(settings.GameServerSecret, sentAt, method, c.path, body))
	return request, nil
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		log.Printf(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
