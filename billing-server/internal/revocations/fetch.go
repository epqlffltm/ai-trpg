// billing-server/internal/revocations/fetch.go

package revocations

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

const (
	// FetchTimeout 은 인증 서버의 응답을 기다리는 시간이다. 요청과 따로 받으므로 길어도 요청이 기다리지 않는다.
	FetchTimeout = 5 * time.Second
	// maxDocumentBytes 는 읽는 문서의 가장 큰 크기다. 줄 하나가 100바이트쯤이라 15분 동안 끊긴 세션이 8만 개를 넘어도 들어간다.
	// 제한이 없으면 잘못된(또는 악의적인) 응답이 메모리를 끝없이 채운다.
	maxDocumentBytes = 8 << 20
	// 로그에 적는 이 일의 이름과, 실패했을 때의 오류 코드(docs/observability.md)
	fetchOperation = "auth.revocations_fetch"
	fetchErrorCode = "auth.revocations_unavailable"
)

// ErrFetch 는 목록을 받지 못했다는 오류다. 이유는 로그에만 남긴다.
var ErrFetch = errors.New("끊긴 세션의 목록을 받지 못했다")

// digestPattern 은 목록의 사용자(sub 의 SHA-256, 소문자 16진수 64자)의 모양이다.
var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

// HTTPFetcher 는 인증 서버의 주소에서 목록을 받는다.
type HTTPFetcher struct {
	// Client 는 요청을 보내는 클라이언트다. 앱 하나가 하나를 함께 쓴다.
	Client *http.Client
	// URL 은 인증 서버가 목록을 내주는 주소다. 설정에서 온 것만 쓴다.
	URL string
}

// document 는 인증 서버가 내주는 문서의 모양이다.
type document struct {
	Revocations []struct {
		SubSHA256 string `json:"sub_sha256"`
		MinVer    *int   `json:"min_ver"`
	} `json:"revocations"`
}

// Fetch 는 목록을 받는다. 어떤 이유로든 받지 못하면 ErrFetch 다.
// 이유는 종류만 로그에 남긴다. 주소를 적지 않는다. 내부 주소가 로그에 남는다.
func (f HTTPFetcher) Fetch(ctx context.Context) (List, error) {
	ctx, cancel := context.WithTimeout(ctx, FetchTimeout)
	defer cancel()

	body, reason := f.get(ctx)
	if reason != "" {
		slog.WarnContext(ctx, "끊긴 세션의 목록을 받지 못했다", fetchAttrs(reason)...)
		return nil, ErrFetch
	}
	list, err := ParseList(body)
	if err != nil {
		slog.WarnContext(ctx, "끊긴 세션의 목록을 받지 못했다", fetchAttrs("모양이 틀린 문서다")...)
		return nil, ErrFetch
	}
	return list, nil
}

// ParseList 는 문서를 읽어 목록으로 바꾼다. 한 줄이라도 모양이 틀리면 문서 전체를 받지 않는다(기억하던 목록을 쓴다).
// 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다.
func ParseList(body []byte) (List, error) {
	var parsed document
	if err := json.Unmarshal(body, &parsed); err != nil || parsed.Revocations == nil {
		return nil, ErrFetch
	}
	list := List{}
	for _, entry := range parsed.Revocations {
		if !digestPattern.MatchString(entry.SubSHA256) || entry.MinVer == nil || *entry.MinVer < 0 {
			return nil, ErrFetch
		}
		list[entry.SubSHA256] = *entry.MinVer
	}
	return list, nil
}

// fetchAttrs 는 받지 못했다는 로그에 싣는 칸들이다.
func fetchAttrs(reason string) []any {
	return []any{
		slog.String(obs.FieldOperation, fetchOperation),
		slog.String(obs.FieldErrorCode, fetchErrorCode),
		slog.String("reason", reason),
	}
}

// get 은 주소를 불러 본문을 돌려준다. 실패하면 그 종류를 짧은 글로 돌려준다(성공이면 빈 글).
func (f HTTPFetcher) get(ctx context.Context) ([]byte, string) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, f.URL, nil)
	if err != nil {
		return nil, "주소를 읽을 수 없다"
	}
	// 인증 서버의 로그와 이 요청의 로그가 같은 trace_id 로 이어진다
	obs.SetOutgoingHeaders(request)
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
