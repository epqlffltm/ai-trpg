// billing-server/internal/jwks/fetch.go

package jwks

import (
	"context"
	"io"
	"log"
	"net/http"
	"time"
)

const (
	// FetchTimeout 은 인증 서버의 응답을 기다리는 시간이다. 이 시간 동안 요청이 멈춰 있으므로 짧게 잡는다.
	FetchTimeout = 5 * time.Second
	// maxDocumentBytes 는 읽는 문서의 가장 큰 크기다. 키 몇 개가 든 문서는 수 KB 다.
	// 제한이 없으면 잘못된(또는 악의적인) 응답이 메모리를 끝없이 채운다.
	maxDocumentBytes = 1 << 20
)

// Fetcher 는 키 목록을 가져오는 것의 모양이다. 캐시가 이것을 받는다.
// 실제 서버는 HTTPFetcher 를, 테스트는 정해 둔 대로 답하는 가짜를 넣는다.
type Fetcher interface {
	Fetch(ctx context.Context) (KeySet, error)
}

// HTTPFetcher 는 인증 서버의 JWKS 주소에서 키 목록을 가져온다.
type HTTPFetcher struct {
	// Client 는 요청을 보내는 클라이언트다. 앱 하나가 하나를 함께 쓴다.
	Client *http.Client
	// URL 은 인증 서버가 공개키를 내주는 주소다. 설정에서 온 것만 쓴다.
	// 토큰 안에 적힌 주소는 쓰지 않는다. 그 주소는 토큰을 만든 쪽이 정한 것이다.
	URL string
}

// Fetch 는 키 목록을 가져온다. 어떤 이유로든 받지 못하면 ErrFetch 다.
// 이유는 종류만 로그에 남긴다. 주소를 적지 않는다. 내부 주소가 로그에 남는다.
func (f HTTPFetcher) Fetch(ctx context.Context) (KeySet, error) {
	ctx, cancel := context.WithTimeout(ctx, FetchTimeout)
	defer cancel()

	body, reason := f.get(ctx)
	if reason != "" {
		log.Printf("JWKS 를 가져오지 못했다: %s", reason)
		return nil, ErrFetch
	}
	keys, err := ParseKeySet(body)
	if err != nil {
		log.Printf("JWKS 를 가져오지 못했다: 쓸 수 있는 키가 없다")
		return nil, ErrFetch
	}
	return keys, nil
}

// get 은 주소를 불러 본문을 돌려준다. 실패하면 그 종류를 짧은 글로 돌려준다(성공이면 빈 글).
func (f HTTPFetcher) get(ctx context.Context) ([]byte, string) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, f.URL, nil)
	if err != nil {
		return nil, "주소를 읽을 수 없다"
	}
	response, err := f.Client.Do(request)
	if err != nil {
		return nil, "연결하지 못했다"
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return nil, "상태 코드가 200 이 아니다"
	}
	// 제한보다 한 바이트 더 읽어 본다. 더 읽히면 제한을 넘은 문서다
	body, err := io.ReadAll(io.LimitReader(response.Body, maxDocumentBytes+1))
	if err != nil {
		return nil, "본문을 읽지 못했다"
	}
	if len(body) > maxDocumentBytes {
		return nil, "문서가 너무 크다"
	}
	return body, ""
}
