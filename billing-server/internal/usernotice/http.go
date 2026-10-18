// billing-server/internal/usernotice/http.go

package usernotice

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

// SendTimeout 은 알림 서버의 답을 기다리는 가장 긴 시간이다.
const SendTimeout = 5 * time.Second

// PutPath 는 결제 서버가 알림을 넣는 주소다. 주소에 넣는 서버의 이름(billing)이 들어간다.
// 알림 서버는 주소의 이름으로 어느 서버의 비밀로 서명을 확인할지 고른다(notification-server/README.md 의 "알림 넣기").
const PutPath = "/api/v1/notification/service/billing/notifications"

// reasonUnauthorized 는 서명이 거절된 것(401)의 이름이다. 두 서버의 비밀이 다르거나 시계가 5분 넘게 어긋났다.
const reasonUnauthorized = "unauthorized"

// HTTPSender 는 알림 서버의 알림 넣기 주소에 서명한 요청을 보낸다.
//
// | 답 | 결과 |
// | 201(새로 넣었다), 200(이미 있다) | 받았다 |
// | 401, 408, 429, 5xx, 닿지 못함, 시간 초과 | 다시 보낸다 |
// | 409(같은 열쇠로 다른 알림), 413, 422, 그 밖의 4xx | 받지 않았다. 버그다 |
type HTTPSender struct {
	// Client 는 요청을 보내는 것이다. 다른 주소로 가라는 답을 따라가지 않게 만든다(NewHTTPSender).
	Client *http.Client
	// BaseURL 은 알림 서버의 주소다(http://notification-server:8004). 끝의 / 는 떼고 쓴다.
	BaseURL string
	// Secret 은 알림 서버와 함께 아는 비밀이다(NOTIFICATION_SECRET). 알림 서버의 BILLING_SERVER_SECRET 과 같은 값이다.
	Secret string
	// Now 는 서명에 넣는 지금 시각이다.
	Now func() time.Time
}

// NewHTTPSender 는 HTTPSender 를 만든다. 다른 주소로 가라는 답은 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다.
func NewHTTPSender(baseURL string, secret string, now func() time.Time) *HTTPSender {
	client := &http.Client{
		Timeout: SendTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	return &HTTPSender{Client: client, BaseURL: strings.TrimRight(baseURL, "/"), Secret: secret, Now: now}
}

// putBody 는 알림 서버에 보내는 본문이다. 알림 서버가 모르는 칸은 넣지 않는다(422).
type putBody struct {
	SourceKey string          `json:"source_key"`
	UserID    string          `json:"user_id"`
	Kind      Kind            `json:"kind"`
	Payload   json.RawMessage `json:"payload"`
}

// Send 는 알릴 일을 보낸다. 결과의 까닭에는 상태 코드나 오류의 종류만 싣는다(오류의 글에는 주소가 들어 있다).
func (h *HTTPSender) Send(ctx context.Context, notice Notice) Sent {
	body, err := encode(notice)
	if err != nil {
		return Sent{Delivery: Rejected, Reason: "bad_payload"}
	}
	request, err := h.request(ctx, body)
	if err != nil {
		return Sent{Delivery: Rejected, Reason: "bad_request"}
	}
	response, err := h.Client.Do(request)
	if err != nil {
		return Sent{Delivery: Unavailable, Reason: transportReason(err)}
	}
	defer response.Body.Close()
	return resultOf(response.StatusCode)
}

// encode 는 보낼 본문을 만든다. 이 바이트에 서명하고 이 바이트를 보낸다.
func encode(notice Notice) ([]byte, error) {
	if !json.Valid(notice.Payload) {
		return nil, errors.New("알림의 내용이 JSON 이 아니다")
	}
	return json.Marshal(putBody{
		SourceKey: notice.Key, UserID: notice.UserID.String(), Kind: notice.Kind, Payload: notice.Payload,
	})
}

// request 는 서명한 요청을 만든다. 서명하는 주소는 호스트를 뺀 경로다.
func (h *HTTPSender) request(ctx context.Context, body []byte) (*http.Request, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, h.BaseURL+PutPath, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(serviceauth.SignatureHeader, serviceauth.Sign(h.Secret, h.Now(), http.MethodPost, PutPath, body))
	return request, nil
}

// resultOf 는 알림 서버의 답을 결과로 바꾼다. 위의 표다.
func resultOf(status int) Sent {
	switch {
	case status == http.StatusOK || status == http.StatusCreated:
		return Sent{Delivery: Delivered}
	case status == http.StatusUnauthorized:
		return Sent{Delivery: Unavailable, Reason: reasonUnauthorized}
	case status >= 500 || status == http.StatusRequestTimeout || status == http.StatusTooManyRequests:
		return Sent{Delivery: Unavailable, Reason: fmt.Sprintf("status_%d", status)}
	default:
		return Sent{Delivery: Rejected, Reason: fmt.Sprintf("status_%d", status)}
	}
}

// transportReason 은 답을 받지 못한 까닭의 이름이다. 시간 초과면 timeout, 그 밖에는 unreachable 이다.
func transportReason(err error) string {
	var timeout interface{ Timeout() bool }
	if errors.As(err, &timeout) && timeout.Timeout() {
		return "timeout"
	}
	return "unreachable"
}
