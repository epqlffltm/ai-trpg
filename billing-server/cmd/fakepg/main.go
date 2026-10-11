// billing-server/cmd/fakepg/main.go

// 가짜 결제 대행사가 되어 결제 서버에 알림(웹훅)을 보내는 명령. 개발할 때 손으로 확인하는 데 쓴다.
//
//	go run ./cmd/fakepg notify <주문 번호> <결제 번호>
//
// 실제 결제 대행사는 결제의 결과가 정해지면 서버의 주소를 불러 알려 준다. 가짜 결제 대행사는 따로 떠 있는
// 서버가 아니라서, 그 호출을 이 명령이 대신한다. 서버와 같은 설정(.env)에서 비밀과 주소를 읽어 서명해 보낸다.
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
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

// usage 는 명령을 잘못 적었을 때 보여 주는 말이다.
const usage = "쓰는 법: go run ./cmd/fakepg notify <주문 번호> <결제 번호>"

// sendTimeout 은 서버의 답을 기다리는 가장 긴 시간이다.
const sendTimeout = 15 * time.Second

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("알림을 보내지 못했습니다: %v", err)
	}
}

// run 은 명령을 확인하고, 설정을 읽고, 알림을 보낸다.
func run(args []string, out io.Writer) error {
	if len(args) != 3 || args[0] != "notify" {
		return errors.New(usage)
	}
	orderID, err := uuid.Parse(args[1])
	if err != nil {
		return errors.New("주문 번호가 UUID 가 아닙니다. " + usage)
	}
	loadDotEnv()
	settings, err := config.Load(os.LookupEnv)
	if err != nil {
		return err
	}
	return notify(settings, orderID, args[2], out)
}

// notify 는 알림의 본문을 만들어 서명하고 서버에 보낸 뒤, 서버의 답을 적는다.
func notify(settings config.Settings, orderID uuid.UUID, paymentKey string, out io.Writer) error {
	body, err := json.Marshal(map[string]string{"order_id": orderID.String(), "payment_key": paymentKey})
	if err != nil {
		return err
	}
	url := "http://" + settings.Addr() + httpapi.APIPrefix + "/webhooks/payment"
	request, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(payment.SignatureHeader, payment.Sign(settings.WebhookSecret, time.Now(), body))

	client := &http.Client{Timeout: sendTimeout}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("서버(%s)에 닿지 못했습니다. 서버가 떠 있는지 확인해 주세요", settings.Addr())
	}
	defer response.Body.Close()
	answer, _ := io.ReadAll(io.LimitReader(response.Body, 4<<10))
	fmt.Fprintf(out, "%d %s\n", response.StatusCode, bytes.TrimSpace(answer))
	return nil
}

// loadDotEnv 는 현재 폴더의 .env 를 환경 변수로 올린다. 파일이 없으면 아무것도 하지 않는다.
func loadDotEnv() {
	if err := godotenv.Load(); err != nil && !errors.Is(err, os.ErrNotExist) {
		// 내용은 찍지 않는다. .env 에는 비밀번호가 들어 있다
		log.Printf(".env 를 읽지 못했습니다. 환경 변수만으로 진행합니다")
	}
}
