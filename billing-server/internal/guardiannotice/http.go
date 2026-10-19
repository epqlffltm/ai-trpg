// billing-server/internal/guardiannotice/http.go

package guardiannotice

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// SendTimeout 은 인증 서버의 답을 기다리는 가장 긴 시간이다.
const SendTimeout = 5 * time.Second

// maxAnswerBytes 는 인증 서버의 답에서 읽는 가장 큰 크기다.
const maxAnswerBytes = 4 << 10

// 인증 서버가 받았다고 답하는 결과. 셋 다 이 서버에는 끝난 일이다.
var finishedAnswers = map[string]bool{
	// queued 는 보호자에게 보낼 메일을 적었다는 것이다
	"queued": true,
	// skipped 는 알릴 보호자가 없다는 것이다(그새 동의를 철회했다)
	"skipped": true,
	// duplicate 는 이미 받은 일이라는 것이다(답을 못 받고 다시 보냈다)
	"duplicate": true,
}

// HTTPSender 는 인증 서버의 알림 주소에 서명한 요청을 보낸다.
type HTTPSender struct {
	// Client 는 요청을 보내는 것이다. 다른 주소로 가라는 답을 따라가지 않게 만든다(NewHTTPSender).
	Client *http.Client
	// URL 은 인증 서버의 알림 주소다(…/api/v1/auth/service/guardian-notices).
	URL string
	// Secret 은 인증 서버와 함께 아는 비밀이다(AUTH_SERVER_SECRET). 인증 서버가 결제 서버를 부를 때와 같은 짝이다.
	// 서명에 주소가 들어가므로, 한쪽 방향의 요청을 다른 방향의 주소에 다시 쓸 수 없다.
	Secret string
	// Now 는 서명에 넣는 지금 시각이다.
	Now func() time.Time
}

// NewHTTPSender 는 HTTPSender 를 만든다. 다른 주소로 가라는 답은 따라가지 않는다. 서명한 요청이 우리가 고르지 않은 곳으로 가면 안 된다.
func NewHTTPSender(rawURL string, secret string, now func() time.Time) *HTTPSender {
	client := &http.Client{
		// 작업 안에서 보내면 span 을 걸고 traceparent 를 붙인다. 받는 서버도 우리 서버다
		Transport: tracing.Transport(nil, true),
		Timeout:   SendTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	return &HTTPSender{Client: client, URL: rawURL, Secret: secret, Now: now}
}

// noticeBody 는 인증 서버에 보내는 본문이다.
type noticeBody struct {
	OrderID    string `json:"order_id"`
	Kind       Kind   `json:"kind"`
	UserID     string `json:"user_id"`
	ProductID  string `json:"product_id"`
	Price      int64  `json:"price"`
	Credits    int64  `json:"credits"`
	OccurredAt string `json:"occurred_at"`
}

// answerBody 는 인증 서버의 답이다.
type answerBody struct {
	Status string `json:"status"`
}

// errNotAccepted 는 인증 서버가 받지 않았다는 오류다. 다시 보낸다.
var errNotAccepted = errors.New("인증 서버가 알림을 받지 않았습니다")

// Send 는 알릴 일을 보낸다. 200 과 아는 결과가 아니면 오류다. 오류에는 상태 코드나 오류의 종류만 싣는다.
func (h *HTTPSender) Send(ctx context.Context, notice Notice) error {
	body, err := json.Marshal(noticeBody{
		OrderID: notice.OrderID.String(), Kind: notice.Kind, UserID: notice.UserID.String(), ProductID: notice.ProductID,
		Price: notice.Price, Credits: notice.Credits, OccurredAt: notice.OccurredAt.UTC().Format(time.RFC3339),
	})
	if err != nil {
		return err
	}
	request, err := h.request(ctx, body)
	if err != nil {
		return err
	}
	response, err := h.Client.Do(request)
	if err != nil {
		// 오류의 글에는 주소가 들어 있다. 종류만 적는다
		return fmt.Errorf("%w: 인증 서버에 닿지 못했다(%T)", errNotAccepted, errors.Unwrap(err))
	}
	defer response.Body.Close()
	return readAnswer(response)
}

// request 는 서명한 요청을 만든다. 서명하는 주소는 호스트를 뺀 경로다.
func (h *HTTPSender) request(ctx context.Context, body []byte) (*http.Request, error) {
	target, err := url.Parse(h.URL)
	if err != nil {
		return nil, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, h.URL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(serviceauth.SignatureHeader, serviceauth.Sign(h.Secret, h.Now(), http.MethodPost, target.RequestURI(), body))
	return request, nil
}

// readAnswer 는 인증 서버의 답을 읽는다.
func readAnswer(response *http.Response) error {
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("%w: %d 로 답했다", errNotAccepted, response.StatusCode)
	}
	var answer answerBody
	if err := json.NewDecoder(io.LimitReader(response.Body, maxAnswerBytes)).Decode(&answer); err != nil {
		return fmt.Errorf("%w: 답을 읽지 못했다", errNotAccepted)
	}
	if !finishedAnswers[answer.Status] {
		return fmt.Errorf("%w: 모르는 결과로 답했다", errNotAccepted)
	}
	return nil
}
