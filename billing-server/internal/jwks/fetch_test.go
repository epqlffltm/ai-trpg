// billing-server/internal/jwks/fetch_test.go

package jwks_test

import (
	"bytes"
	"context"
	"errors"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// serve 는 handler 로 답하는 가짜 인증 서버를 띄우고, 그 서버에서 가져오는 Fetcher 를 돌려준다.
func serve(t *testing.T, handler http.HandlerFunc) jwks.HTTPFetcher {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	return jwks.HTTPFetcher{Client: server.Client(), URL: server.URL + "/api/v1/auth/jwks"}
}

// captureLog 는 테스트 동안 찍힌 로그를 모아 돌려주는 함수를 돌려준다.
func captureLog(t *testing.T) func() string {
	t.Helper()
	var buffer bytes.Buffer
	previous := log.Writer()
	log.SetOutput(&buffer)
	t.Cleanup(func() { log.SetOutput(previous) })
	return buffer.String
}

func TestFetchReadsTheKeySet(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	var asked string
	fetcher := serve(t, func(w http.ResponseWriter, r *http.Request) {
		asked = r.Method + " " + r.URL.Path
		_, _ = w.Write(testenv.JWKS(t, key))
	})

	keys, err := fetcher.Fetch(context.Background())
	if err != nil {
		t.Fatalf("가져오지 못했다: %v", err)
	}

	if asked != "GET /api/v1/auth/jwks" {
		t.Errorf("부른 주소 = %q", asked)
	}
	if len(keys) != 1 || !keys["key-1"].Equal(&key.Private.PublicKey) {
		t.Error("가져온 키가 인증 서버의 키와 다르다")
	}
}

func TestFetchFailsOnBadResponses(t *testing.T) {
	cases := map[string]http.HandlerFunc{
		"500": func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusInternalServerError) },
		"404": http.NotFound,
		"JSON 이 아니다": func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte("<html>maintenance</html>"))
		},
		"키가 없다": func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(`{"keys": []}`)) },
	}
	for name, handler := range cases {
		t.Run(name, func(t *testing.T) {
			captureLog(t)

			keys, err := serve(t, handler).Fetch(context.Background())

			if !errors.Is(err, jwks.ErrFetch) {
				t.Errorf("오류 = %v, 기대 = ErrFetch", err)
			}
			if keys != nil {
				t.Error("실패했는데 키가 돌아왔다")
			}
		})
	}
}

func TestFetchIgnoresTheBodyOfAFailedResponse(t *testing.T) {
	captureLog(t)
	key := testenv.NewSigningKey(t, 0, "key-1")
	// 본문은 멀쩡한 키 목록이지만 상태 코드가 실패다. 본문을 믿지 않는다
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write(testenv.JWKS(t, key))
	})

	keys, err := fetcher.Fetch(context.Background())

	if !errors.Is(err, jwks.ErrFetch) || keys != nil {
		t.Errorf("실패한 응답의 키를 받았다: 오류 = %v", err)
	}
}

func TestFetchRejectsAnOversizedDocument(t *testing.T) {
	captureLog(t)
	key := testenv.NewSigningKey(t, 0, "key-1")
	// 키는 멀쩡하다. 크기만 제한을 넘는다. 제한이 없으면 이 문서는 받아들여진다
	document := testenv.MustJSON(t, map[string]any{
		"keys":    []any{key.JWK()},
		"padding": strings.Repeat("x", 2<<20),
	})
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write(document) })

	keys, err := fetcher.Fetch(context.Background())

	if !errors.Is(err, jwks.ErrFetch) || keys != nil {
		t.Errorf("제한을 넘은 문서를 받았다: 오류 = %v", err)
	}
}

func TestFetchFailsWhenTheServerIsDown(t *testing.T) {
	captureLog(t)
	// 서버를 띄웠다가 바로 닫는다. 주소는 남아 있지만 아무도 듣지 않는다
	closed := httptest.NewServer(http.NotFoundHandler())
	closed.Close()
	fetcher := jwks.HTTPFetcher{Client: &http.Client{}, URL: closed.URL}

	_, err := fetcher.Fetch(context.Background())

	if !errors.Is(err, jwks.ErrFetch) {
		t.Errorf("오류 = %v, 기대 = ErrFetch", err)
	}
}

func TestFetchGivesUpWhenTheCallerDoes(t *testing.T) {
	captureLog(t)
	release := make(chan struct{})
	fetcher := serve(t, func(http.ResponseWriter, *http.Request) { <-release })
	defer close(release)
	// 인증 서버가 답하지 않는다. 부른 쪽이 정한 시간이 지나면 그만둔다
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	started := time.Now()
	_, err := fetcher.Fetch(ctx)

	if !errors.Is(err, jwks.ErrFetch) {
		t.Errorf("오류 = %v, 기대 = ErrFetch", err)
	}
	if waited := time.Since(started); waited > 2*time.Second {
		t.Errorf("%v 를 기다렸다. 정한 시간에 그만두지 않았다", waited)
	}
}

func TestFetchDoesNotLogTheAddress(t *testing.T) {
	logged := captureLog(t)
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusBadGateway) })

	_, _ = fetcher.Fetch(context.Background())

	if logged() == "" {
		t.Error("실패를 로그에 남기지 않았다")
	}
	// 내부 주소가 로그에 남지 않게 한다
	if strings.Contains(logged(), "127.0.0.1") || strings.Contains(logged(), "/api/v1/auth/jwks") {
		t.Errorf("로그에 주소가 실렸다: %s", logged())
	}
}

func TestFetchContinuesTheTraceOfTheRequest(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	var headers http.Header
	fetcher := serve(t, func(w http.ResponseWriter, r *http.Request) {
		headers = r.Header.Clone()
		_, _ = w.Write(testenv.JWKS(t, key))
	})
	trace := obs.NewTrace()
	ctx := obs.WithRequest(context.Background(), "request-12345", trace)

	if _, err := fetcher.Fetch(ctx); err != nil {
		t.Fatalf("가져오지 못했다: %v", err)
	}

	// 인증 서버의 로그와 이 요청의 로그가 같은 trace_id 로 이어진다
	if got, ok := obs.ParseTraceparent(headers.Get(obs.TraceparentHeader)); !ok || got != trace {
		t.Errorf("traceparent = %q", headers.Get(obs.TraceparentHeader))
	}
	// 요청의 식별자는 넘기지 않는다. 인증 서버가 제 것을 따로 만든다
	if headers.Get(obs.RequestIDHeader) != "" {
		t.Error("요청의 식별자를 인증 서버에 넘겼다")
	}
}

func TestFetchOutsideARequestSendsNoTrace(t *testing.T) {
	key := testenv.NewSigningKey(t, 0, "key-1")
	var headers http.Header
	fetcher := serve(t, func(w http.ResponseWriter, r *http.Request) {
		headers = r.Header.Clone()
		_, _ = w.Write(testenv.JWKS(t, key))
	})

	if _, err := fetcher.Fetch(context.Background()); err != nil {
		t.Fatalf("가져오지 못했다: %v", err)
	}

	if headers.Get(obs.TraceparentHeader) != "" {
		t.Error("추적이 없는데 traceparent 를 보냈다")
	}
}
