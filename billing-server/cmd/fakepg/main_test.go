// billing-server/cmd/fakepg/main_test.go

// 알림을 만드는 일과 보내는 일을 서버 없이 확인한다. 서버 자리에는 받은 것을 적어 두는 가짜를 띄운다.
package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/payment"
)

const (
	testOrderID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
	testSecret  = "this-is-a-test-secret-of-32-chars!"
)

var testNow = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

func TestParseCommandAcceptsBothKinds(t *testing.T) {
	for _, kind := range []string{"notify", "toss-notify"} {
		got, err := parseCommand([]string{kind, testOrderID, "tgen_1"})
		if err != nil || got.kind != kind || got.orderID.String() != testOrderID || got.paymentKey != "tgen_1" {
			t.Errorf("%s: 명령 = %+v, %v", kind, got, err)
		}
	}
}

func TestParseCommandRefusesWhatItDoesNotKnow(t *testing.T) {
	cases := map[string][]string{
		"없다":          {},
		"모르는 종류":      {"notify-all", testOrderID, "k"},
		"주문 번호가 이상하다": {"toss-notify", "order-1", "k"},
		"결제 번호가 없다":   {"notify", testOrderID},
	}
	for name, args := range cases {
		if _, err := parseCommand(args); err == nil {
			t.Errorf("%s: 오류가 나야 한다", name)
		}
	}
}

func TestTossNotificationIsReadByTheServerAsTheSamePayment(t *testing.T) {
	cmd := command{kind: commandTossNotify, orderID: uuid.MustParse(testOrderID), paymentKey: "tgen_1"}

	message, err := build(cmd, testSecret, testNow)

	if err != nil || message.path != httpapi.TossWebhookPath || len(message.headers) != 0 {
		t.Fatalf("알림 = %+v, %v", message, err)
	}
	// 서버가 쓰는 것으로 읽으면 같은 주문, 같은 결제다
	got, relevant, err := payment.ReadTossNotification(message.body)
	if err != nil || !relevant || got.OrderID.String() != testOrderID || got.PaymentKey != "tgen_1" {
		t.Errorf("서버가 읽은 알림 = %+v, %v, %v", got, relevant, err)
	}
}

func TestSignedNotificationCarriesAValidSignature(t *testing.T) {
	cmd := command{kind: commandNotify, orderID: uuid.MustParse(testOrderID), paymentKey: "fake_ok_1"}

	message, err := build(cmd, testSecret, testNow)

	if err != nil || message.path != httpapi.APIPrefix+"/webhooks/payment" {
		t.Fatalf("알림 = %+v, %v", message, err)
	}
	if err := payment.VerifySignature(testSecret, message.headers[payment.SignatureHeader], message.body, testNow); err != nil {
		t.Errorf("서명이 맞지 않는다: %v", err)
	}
	var body map[string]string
	if err := json.Unmarshal(message.body, &body); err != nil || body["order_id"] != testOrderID || body["payment_key"] != "fake_ok_1" {
		t.Errorf("본문 = %s", message.body)
	}
}

func TestSendPostsTheNotificationAndPrintsTheAnswer(t *testing.T) {
	var gotPath, gotType, gotSignature string
	var gotBody []byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotType, gotSignature = r.URL.Path, r.Header.Get("Content-Type"), r.Header.Get(payment.SignatureHeader)
		gotBody, _ = io.ReadAll(r.Body)
		_, _ = w.Write([]byte(`{"received":true}` + "\n"))
	}))
	defer server.Close()
	message := outgoing{path: "/x", body: []byte(`{"a":1}`), headers: map[string]string{payment.SignatureHeader: "t=1,v1=ab"}}
	var out bytes.Buffer

	err := send(server.Client(), server.URL, message, &out)

	if err != nil || out.String() != "200 {\"received\":true}\n" {
		t.Errorf("오류 = %v, 찍은 것 = %q", err, out.String())
	}
	if gotPath != "/x" || gotType != "application/json" || gotSignature != "t=1,v1=ab" || string(gotBody) != `{"a":1}` {
		t.Errorf("서버가 받은 것 = %s, %s, %s, %s", gotPath, gotType, gotSignature, gotBody)
	}
}

func TestSendSaysWhenTheServerIsDown(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	url := server.URL
	server.Close()

	err := send(&http.Client{Timeout: time.Second}, url, outgoing{path: "/x"}, io.Discard)

	if err == nil || !strings.Contains(err.Error(), "서버가 떠 있는지") {
		t.Errorf("오류 = %v", err)
	}
}
