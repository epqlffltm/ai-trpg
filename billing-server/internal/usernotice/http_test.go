// billing-server/internal/usernotice/http_test.go

package usernotice_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice"
)

const notificationSecret = "notification-server-test-secret-of-32"

var sentAt = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)

// fakeNotification 은 알림 서버가 되어 받은 요청을 적고 정해 둔 상태로 답한다.
type fakeNotification struct {
	status int

	path      string
	signature string
	body      []byte
}

func (f *fakeNotification) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 다른 주소로 가라는 답을 따라오면 받았다고 답한다. 따라가지 않아야 받지 않은 것이 된다
	if r.URL.Path == "/elsewhere" {
		w.WriteHeader(http.StatusCreated)
		return
	}
	if f.status == http.StatusFound {
		w.Header().Set("Location", "/elsewhere")
	}
	f.path = r.URL.RequestURI()
	f.signature = r.Header.Get(serviceauth.SignatureHeader)
	f.body, _ = io.ReadAll(r.Body)
	w.WriteHeader(f.status)
}

func sampleNotice() usernotice.Notice {
	return usernotice.Notice{
		ID: 7, Key: "order.paid:11111111-2222-4333-8444-555555555555",
		UserID: uuid.MustParse("99999999-8888-4777-8666-555555555555"), Kind: usernotice.KindOrderPaid,
		Payload: []byte(`{"order_id":"11111111-2222-4333-8444-555555555555","price":1000,"credits":"1000"}`),
	}
}

func serve(t *testing.T, status int) (*fakeNotification, *usernotice.HTTPSender) {
	t.Helper()
	fake := &fakeNotification{status: status}
	server := httptest.NewServer(fake)
	t.Cleanup(server.Close)
	// 끝의 / 는 떼고 쓴다. 주소에 // 가 생기면 서명한 경로와 어긋난다
	return fake, usernotice.NewHTTPSender(server.URL+"/", notificationSecret, func() time.Time { return sentAt })
}

func TestTheRequestIsSignedLikeTheNotificationServerExpects(t *testing.T) {
	fake, sender := serve(t, http.StatusCreated)

	sent := sender.Send(context.Background(), sampleNotice())

	if sent.Delivery != usernotice.Delivered || fake.path != usernotice.PutPath {
		t.Fatalf("결과 = %+v, 경로 = %s", sent, fake.path)
	}
	if err := serviceauth.Verify(notificationSecret, fake.signature, http.MethodPost, usernotice.PutPath, fake.body, sentAt); err != nil {
		t.Errorf("서명이 맞지 않는다: %v", err)
	}
	var body map[string]any
	if err := json.Unmarshal(fake.body, &body); err != nil {
		t.Fatalf("본문을 읽지 못했다: %v", err)
	}
	// 알림 서버가 받는 칸만 있다. 모르는 칸이 있으면 422 다
	if len(body) != 4 || body["source_key"] != sampleNotice().Key || body["user_id"] != sampleNotice().UserID.String() ||
		body["kind"] != "order.paid" || body["payload"].(map[string]any)["credits"] != "1000" {
		t.Errorf("본문 = %v", body)
	}
}

func TestTheAnswerDecidesWhatHappensNext(t *testing.T) {
	for status, want := range map[int]usernotice.Sent{
		http.StatusCreated:               {Delivery: usernotice.Delivered},
		http.StatusOK:                    {Delivery: usernotice.Delivered},
		http.StatusUnauthorized:          {Delivery: usernotice.Unavailable, Reason: "unauthorized"},
		http.StatusRequestTimeout:        {Delivery: usernotice.Unavailable, Reason: "status_408"},
		http.StatusTooManyRequests:       {Delivery: usernotice.Unavailable, Reason: "status_429"},
		http.StatusInternalServerError:   {Delivery: usernotice.Unavailable, Reason: "status_500"},
		http.StatusServiceUnavailable:    {Delivery: usernotice.Unavailable, Reason: "status_503"},
		http.StatusConflict:              {Delivery: usernotice.Rejected, Reason: "status_409"},
		http.StatusRequestEntityTooLarge: {Delivery: usernotice.Rejected, Reason: "status_413"},
		http.StatusUnprocessableEntity:   {Delivery: usernotice.Rejected, Reason: "status_422"},
		http.StatusNotFound:              {Delivery: usernotice.Rejected, Reason: "status_404"},
		// 다른 주소로 가라는 답은 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다
		http.StatusFound: {Delivery: usernotice.Rejected, Reason: "status_302"},
	} {
		_, sender := serve(t, status)

		if sent := sender.Send(context.Background(), sampleNotice()); sent != want {
			t.Errorf("%d: 결과 = %+v, 기대 = %+v", status, sent, want)
		}
	}
}

func TestNoAnswerIsSentAgain(t *testing.T) {
	sender := usernotice.NewHTTPSender("http://127.0.0.1:1", notificationSecret, time.Now)

	sent := sender.Send(context.Background(), sampleNotice())

	if sent != (usernotice.Sent{Delivery: usernotice.Unavailable, Reason: "unreachable"}) {
		t.Errorf("결과 = %+v", sent)
	}
}

// timeoutTransport 는 언제나 시간이 다 된 오류를 내는 연결이다.
type timeoutTransport struct{}

type timeoutError struct{}

func (timeoutError) Error() string { return "시간이 다 됐다" }
func (timeoutError) Timeout() bool { return true }

func (timeoutTransport) RoundTrip(*http.Request) (*http.Response, error) { return nil, timeoutError{} }

func TestATimeoutIsSentAgain(t *testing.T) {
	sender := usernotice.NewHTTPSender("http://notification.test", notificationSecret, time.Now)
	sender.Client.Transport = timeoutTransport{}

	sent := sender.Send(context.Background(), sampleNotice())

	if sent != (usernotice.Sent{Delivery: usernotice.Unavailable, Reason: "timeout"}) {
		t.Errorf("결과 = %+v", sent)
	}
}

func TestABrokenNoticeIsNotSent(t *testing.T) {
	fake, sender := serve(t, http.StatusCreated)
	broken := sampleNotice()
	broken.Payload = []byte(`{"not json`)

	sent := sender.Send(context.Background(), broken)

	// 다시 보내도 같다. 버그로 둔다
	if sent != (usernotice.Sent{Delivery: usernotice.Rejected, Reason: "bad_payload"}) || fake.body != nil {
		t.Errorf("결과 = %+v, 보낸 본문 = %q", sent, fake.body)
	}
}

func TestABadAddressIsNotSent(t *testing.T) {
	sender := usernotice.NewHTTPSender("http://bad host", notificationSecret, time.Now)

	if sent := sender.Send(context.Background(), sampleNotice()); sent.Delivery != usernotice.Rejected {
		t.Errorf("결과 = %+v", sent)
	}
}
