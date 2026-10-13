// billing-server/cmd/fakepg/main.go

// 결제 대행사가 되어 결제 서버에 알림(웹훅)을 보내는 명령. 개발할 때 손으로 확인하는 데 쓴다.
//
//	go run ./cmd/fakepg notify <주문 번호> <결제 번호>        가짜 결제 대행사의 알림(서명을 붙인다)
//	go run ./cmd/fakepg toss-notify <주문 번호> <결제 번호>   토스페이먼츠 모양의 알림(서명이 없다)
//
// 실제 결제 대행사는 결제의 결과가 정해지면 서버의 주소를 불러 알려 준다. 가짜 결제 대행사는 따로 떠 있는
// 서버가 아니라서, 그 호출을 이 명령이 대신한다. 토스페이먼츠는 개발자센터에 등록한 주소로만 알림을 보내므로,
// 그 주소를 인터넷에 열지 않은 PC 에서는 이 명령으로 같은 모양의 알림을 보내 본다.
// 서버와 같은 설정(.env)에서 주소와 비밀을 읽는다.
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
const usage = "쓰는 법: go run ./cmd/fakepg notify|toss-notify <주문 번호> <결제 번호>"

// sendTimeout 은 서버의 답을 기다리는 가장 긴 시간이다.
const sendTimeout = 15 * time.Second

// 명령의 종류.
const (
	commandNotify     = "notify"
	commandTossNotify = "toss-notify"
)

// command 는 명령 줄에서 읽은 것이다.
type command struct {
	kind       string
	orderID    uuid.UUID
	paymentKey string
}

// outgoing 은 서버에 보낼 알림 하나다.
type outgoing struct {
	path    string
	body    []byte
	headers map[string]string
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		log.Fatalf("알림을 보내지 못했습니다: %v", err)
	}
}

// run 은 명령을 확인하고, 설정을 읽고, 알림을 보낸다.
func run(args []string, out io.Writer) error {
	cmd, err := parseCommand(args)
	if err != nil {
		return err
	}
	loadDotEnv()
	settings, err := config.Load(os.LookupEnv)
	if err != nil {
		return err
	}
	message, err := build(cmd, settings.WebhookSecret, time.Now())
	if err != nil {
		return err
	}
	return send(&http.Client{Timeout: sendTimeout}, "http://"+settings.Addr(), message, out)
}

// parseCommand 는 명령 줄을 읽는다.
func parseCommand(args []string) (command, error) {
	if len(args) != 3 || (args[0] != commandNotify && args[0] != commandTossNotify) {
		return command{}, errors.New(usage)
	}
	orderID, err := uuid.Parse(args[1])
	if err != nil {
		return command{}, errors.New("주문 번호가 UUID 가 아닙니다. " + usage)
	}
	return command{kind: args[0], orderID: orderID, paymentKey: args[2]}, nil
}

// build 는 명령의 종류에 맞는 알림을 만든다.
func build(cmd command, secret string, now time.Time) (outgoing, error) {
	if cmd.kind == commandTossNotify {
		return tossNotification(cmd)
	}
	return signedNotification(cmd, secret, now)
}

// signedNotification 은 가짜 결제 대행사의 알림을 만든다. 본문에 서명한다.
func signedNotification(cmd command, secret string, now time.Time) (outgoing, error) {
	body, err := json.Marshal(map[string]string{"order_id": cmd.orderID.String(), "payment_key": cmd.paymentKey})
	if err != nil {
		return outgoing{}, err
	}
	headers := map[string]string{payment.SignatureHeader: payment.Sign(secret, now, body)}
	return outgoing{path: httpapi.APIPrefix + "/webhooks/payment", body: body, headers: headers}, nil
}

// tossNotification 은 토스페이먼츠의 결제 상태 알림과 같은 모양의 본문을 만든다. 서명은 없다.
// 상태는 아무 값이나 적는다. 서버는 상태를 읽지 않고 토스페이먼츠에 다시 묻는다.
func tossNotification(cmd command) (outgoing, error) {
	body, err := json.Marshal(map[string]any{
		"eventType": payment.TossPaymentStatusChanged,
		"createdAt": time.Now().Format("2006-01-02T15:04:05.000000"),
		"data":      map[string]string{"paymentKey": cmd.paymentKey, "orderId": cmd.orderID.String(), "status": "DONE"},
	})
	if err != nil {
		return outgoing{}, err
	}
	return outgoing{path: httpapi.TossWebhookPath, body: body}, nil
}

// send 는 알림을 서버에 보내고 서버의 답을 적는다.
func send(client *http.Client, baseURL string, message outgoing, out io.Writer) error {
	request, err := http.NewRequest(http.MethodPost, baseURL+message.path, bytes.NewReader(message.body))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	for name, value := range message.headers {
		request.Header.Set(name, value)
	}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("서버(%s)에 닿지 못했습니다. 서버가 떠 있는지 확인해 주세요", baseURL)
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
