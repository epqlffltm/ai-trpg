// billing-server/internal/stepup/stepup.go

// Package stepup 은 민감한 작업(청약철회, 카드 등록·바꾸기·지우기) 앞에서 인증 서버에 본인 확인 창을 묻는다(F5).
//
// 이 서버는 본인 확인의 수단(메일 코드 등)을 모른다. 사용자의 access 토큰에 실린 sub 와 세션의 이름(sid)을
// 인증 서버의 서버끼리 주소(…/api/v1/auth/service/step-up/check)에 서명해 보내고 답의 상태만 읽는다.
//   - open: 창이 열려 있다. 인증 서버가 창을 늘렸다. 작업을 한다
//   - required: 창이 닫혔거나 확인한 적이 없다. 화면이 본인 확인을 받게 한다
//   - disabled: 본인 확인을 끈 사람이다. 카드 작업은 확인 없이 하고, 청약철회는 받지 않는다(httpapi 가 정한다)
//
// 짧은 증표를 받는 대신 묻는 방식을 골랐다. 코드와 메일은 인증 서버만 알고, 다시 쓰기 걱정이 없다.
// 대가로 인증 서버가 답하지 않으면 민감한 작업이 잠깐 막힌다(ErrUnavailable, 503).
package stepup

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

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/tracing"
)

// State 는 인증 서버가 답한 창의 상태다.
type State string

const (
	// Open 은 창이 열려 있다는 것이다. 인증 서버가 창을 늘렸다.
	Open State = "open"
	// Required 는 창이 닫혔거나 확인한 적이 없다는 것이다.
	Required State = "required"
	// Disabled 는 본인 확인을 끈 사람이라는 것이다.
	Disabled State = "disabled"
)

// CheckTimeout 은 인증 서버의 답을 기다리는 가장 긴 시간이다. 사용자가 기다리는 요청 안에서 부른다.
const CheckTimeout = 5 * time.Second

// maxAnswerBytes 는 인증 서버의 답에서 읽는 가장 큰 크기다.
const maxAnswerBytes = 4 << 10

// ErrUnavailable 은 인증 서버에 묻지 못했거나 답을 알아듣지 못했다는 것이다. 같은 요청을 다시 보내면 된다.
var ErrUnavailable = errors.New("본인 확인 창을 인증 서버에 묻지 못했습니다")

// HTTPChecker 는 인증 서버의 서버끼리 주소에 서명한 요청을 보낸다.
type HTTPChecker struct {
	// Client 는 요청을 보내는 것이다. 다른 주소로 가라는 답을 따라가지 않게 만든다(NewHTTPChecker).
	Client *http.Client
	// URL 은 인증 서버의 묻는 주소다(…/api/v1/auth/service/step-up/check).
	URL string
	// Secret 은 인증 서버와 함께 아는 비밀이다(AUTH_SERVER_SECRET). 서명에 주소가 들어가 다른 주소에 다시 쓸 수 없다.
	Secret string
	// Now 는 서명에 넣는 지금 시각이다.
	Now func() time.Time
}

// NewHTTPChecker 는 HTTPChecker 를 만든다. 다른 주소로 가라는 답은 따라가지 않는다.
func NewHTTPChecker(rawURL string, secret string, now func() time.Time) *HTTPChecker {
	client := &http.Client{
		// 요청 안에서 부르면 span 을 걸고 traceparent 를 붙인다. 받는 서버도 우리 서버다
		Transport: tracing.Transport(nil, true),
		Timeout:   CheckTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	return &HTTPChecker{Client: client, URL: rawURL, Secret: secret, Now: now}
}

// checkBody 는 인증 서버에 보내는 본문이다.
type checkBody struct {
	UserID    string `json:"user_id"`
	SessionID string `json:"session_id"`
}

// answerBody 는 인증 서버의 답이다. expires_at 은 읽지 않는다(창의 시각은 화면이 인증 서버에서 읽는다).
type answerBody struct {
	State State `json:"state"`
}

// Check 는 그 사용자의 그 세션의 창을 묻는다. 세션의 이름이 없으면(옛 토큰) 묻지 않고 Required 다.
// 인증 서버에 그 사용자가 없으면(404) Required 다. 그 밖의 실패는 ErrUnavailable 이다.
func (h *HTTPChecker) Check(ctx context.Context, userID uuid.UUID, sessionID string) (State, error) {
	if sessionID == "" {
		return Required, nil
	}
	body, err := json.Marshal(checkBody{UserID: userID.String(), SessionID: sessionID})
	if err != nil {
		return "", err
	}
	request, err := h.request(ctx, body)
	if err != nil {
		return "", err
	}
	response, err := h.Client.Do(request)
	if err != nil {
		// 오류의 글에는 주소가 들어 있다. 종류만 적는다
		return "", fmt.Errorf("%w: 인증 서버에 닿지 못했다(%T)", ErrUnavailable, errors.Unwrap(err))
	}
	defer response.Body.Close()
	return readAnswer(response)
}

// request 는 서명한 요청을 만든다. 서명하는 주소는 호스트를 뺀 경로다.
func (h *HTTPChecker) request(ctx context.Context, body []byte) (*http.Request, error) {
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
func readAnswer(response *http.Response) (State, error) {
	if response.StatusCode == http.StatusNotFound {
		return Required, nil
	}
	if response.StatusCode != http.StatusOK {
		return "", fmt.Errorf("%w: %d 로 답했다", ErrUnavailable, response.StatusCode)
	}
	var answer answerBody
	if err := json.NewDecoder(io.LimitReader(response.Body, maxAnswerBytes)).Decode(&answer); err != nil {
		return "", fmt.Errorf("%w: 답을 읽지 못했다", ErrUnavailable)
	}
	switch answer.State {
	case Open, Required, Disabled:
		return answer.State, nil
	default:
		return "", fmt.Errorf("%w: 모르는 상태로 답했다", ErrUnavailable)
	}
}
