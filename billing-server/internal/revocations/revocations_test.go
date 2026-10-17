// billing-server/internal/revocations/revocations_test.go

package revocations_test

import (
	"bytes"
	"context"
	"errors"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/revocations"
)

// 인증 서버의 테스트(accounts/tests/test_session_revocations.py)와 같은 예시다. 두 서버가 같은 값을 계산해야 한다
const (
	exampleSub    = "0d3f7a52-6f0a-4c1e-9d55-2b8a4c1f7e90"
	exampleDigest = "08f6625d1aecc747bd6122bbf85ef9fb3fc0f25f7986169f057f12639fe6c0ed"
)

func TestDigestMatchesTheAuthServer(t *testing.T) {
	if got := revocations.Digest(exampleSub); got != exampleDigest {
		t.Errorf("Digest = %s, 기대 = %s", got, exampleDigest)
	}
}

func TestATokenOlderThanTheRevocationIsRevoked(t *testing.T) {
	list := revocations.List{exampleDigest: 3}

	for version, want := range map[int]bool{0: true, 2: true, 3: false, 4: false} {
		if got := list.Revoked(exampleSub, version); got != want {
			t.Errorf("ver %d: Revoked = %v, 기대 = %v", version, got, want)
		}
	}
	if list.Revoked("1b4e28ba-2fa1-11d2-883f-0016d3cca427", 0) {
		t.Error("목록에 없는 사용자를 끊긴 것으로 봤다")
	}
}

func TestParseListReadsTheDocument(t *testing.T) {
	list, err := revocations.ParseList([]byte(`{"revocations":[{"sub_sha256":"` + exampleDigest + `","min_ver":3}],"refresh_interval_seconds":30}`))
	if err != nil {
		t.Fatalf("읽지 못했다: %v", err)
	}
	if len(list) != 1 || list[exampleDigest] != 3 {
		t.Errorf("목록 = %v", list)
	}

	empty, err := revocations.ParseList([]byte(`{"revocations":[]}`))
	if err != nil || len(empty) != 0 {
		t.Errorf("빈 목록 = %v, %v", empty, err)
	}
}

func TestParseListRefusesAWrongDocument(t *testing.T) {
	// 한 줄이라도 틀리면 문서 전체를 받지 않는다. 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다
	cases := map[string]string{
		"JSON 이 아니다":  `not json`,
		"목록이 없다":      `{}`,
		"해시가 대문자다":    `{"revocations":[{"sub_sha256":"` + strings.ToUpper(exampleDigest) + `","min_ver":1}]}`,
		"해시가 짧다":      `{"revocations":[{"sub_sha256":"08f6","min_ver":1}]}`,
		"버전이 없다":      `{"revocations":[{"sub_sha256":"` + exampleDigest + `"}]}`,
		"버전이 음수다":     `{"revocations":[{"sub_sha256":"` + exampleDigest + `","min_ver":-1}]}`,
		"버전이 숫자가 아니다": `{"revocations":[{"sub_sha256":"` + exampleDigest + `","min_ver":"3"}]}`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := revocations.ParseList([]byte(body)); !errors.Is(err, revocations.ErrFetch) {
				t.Errorf("오류 = %v. ErrFetch 이어야 한다", err)
			}
		})
	}
}

// captureLog 는 표준 로그(slog 의 기본)를 모은다. 테스트가 끝나면 되돌린다.
func captureLog(t *testing.T) func() string {
	t.Helper()
	var buffer bytes.Buffer
	previous := log.Writer()
	log.SetOutput(&buffer)
	t.Cleanup(func() { log.SetOutput(previous) })
	return buffer.String
}

func serve(t *testing.T, handler http.HandlerFunc) revocations.HTTPFetcher {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	return revocations.HTTPFetcher{Client: server.Client(), URL: server.URL + "/api/v1/auth/session-revocations"}
}

func TestFetchReadsTheList(t *testing.T) {
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"revocations":[{"sub_sha256":"` + exampleDigest + `","min_ver":2}]}`))
	})

	list, err := fetcher.Fetch(context.Background())
	if err != nil || list[exampleDigest] != 2 {
		t.Errorf("목록 = %v, 오류 = %v", list, err)
	}
}

func TestFetchFailureIsLoggedWithoutTheAddress(t *testing.T) {
	logged := captureLog(t)
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	})

	if _, err := fetcher.Fetch(context.Background()); !errors.Is(err, revocations.ErrFetch) {
		t.Fatalf("오류 = %v", err)
	}
	if !strings.Contains(logged(), "error_code=auth.revocations_unavailable") {
		t.Errorf("로그에 오류 코드가 없다: %s", logged())
	}
	if strings.Contains(logged(), "127.0.0.1") || strings.Contains(logged(), "session-revocations") {
		t.Errorf("로그에 주소가 남았다: %s", logged())
	}
}

func TestFetchRefusesAHugeDocument(t *testing.T) {
	captureLog(t)
	fetcher := serve(t, func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(bytes.Repeat([]byte(" "), 9<<20))
	})

	if _, err := fetcher.Fetch(context.Background()); !errors.Is(err, revocations.ErrFetch) {
		t.Errorf("오류 = %v", err)
	}
}

// fakeFetcher 는 정해 둔 대로 답하고 몇 번 불렸는지 센다.
type fakeFetcher struct {
	mu    sync.Mutex
	list  revocations.List
	err   error
	calls int
}

func (f *fakeFetcher) Fetch(context.Context) (revocations.List, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	return f.list, f.err
}

func (f *fakeFetcher) set(list revocations.List, err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.list, f.err = list, err
}

func (f *fakeFetcher) count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

func TestCacheRevokesNothingBeforeTheFirstList(t *testing.T) {
	cache := revocations.NewCache(&fakeFetcher{})

	if cache.Revoked(exampleSub, 0) {
		t.Error("목록을 받기 전인데 끊긴 것으로 봤다")
	}
}

func TestCacheKeepsTheLastListWhenAFetchFails(t *testing.T) {
	fetcher := &fakeFetcher{list: revocations.List{exampleDigest: 1}}
	cache := revocations.NewCache(fetcher)
	if err := cache.Refresh(context.Background()); err != nil {
		t.Fatal(err)
	}

	fetcher.set(nil, revocations.ErrFetch)
	if err := cache.Refresh(context.Background()); !errors.Is(err, revocations.ErrFetch) {
		t.Fatalf("오류 = %v", err)
	}

	if !cache.Revoked(exampleSub, 0) {
		t.Error("받지 못한 뒤에 기억하던 목록을 버렸다")
	}
}

func TestCacheReplacesTheList(t *testing.T) {
	// 인증 서버가 뺀 줄(15분이 지난 것)은 여기서도 빠진다
	fetcher := &fakeFetcher{list: revocations.List{exampleDigest: 1}}
	cache := revocations.NewCache(fetcher)
	_ = cache.Refresh(context.Background())

	fetcher.set(revocations.List{}, nil)
	_ = cache.Refresh(context.Background())

	if cache.Revoked(exampleSub, 0) {
		t.Error("새 목록에 없는 줄이 남았다")
	}
}

func TestRunFetchesAtOnceThenEveryIntervalUntilStopped(t *testing.T) {
	fetcher := &fakeFetcher{list: revocations.List{exampleDigest: 1}}
	cache := revocations.NewCache(fetcher)
	ctx, cancel := context.WithCancel(context.Background())
	stopped := make(chan struct{})
	go func() {
		cache.Run(ctx, 10*time.Millisecond)
		close(stopped)
	}()

	deadline := time.Now().Add(5 * time.Second)
	for fetcher.count() < 3 {
		if time.Now().After(deadline) {
			t.Fatalf("5초 동안 %d번만 받았다", fetcher.count())
		}
		time.Sleep(5 * time.Millisecond)
	}
	if !cache.Revoked(exampleSub, 0) {
		t.Error("받은 목록을 쓰지 않는다")
	}

	cancel()
	select {
	case <-stopped:
	case <-time.After(5 * time.Second):
		t.Fatal("ctx 가 끝났는데 멈추지 않았다")
	}
}

func TestRunDoesNotStopWhenFetchesFail(t *testing.T) {
	fetcher := &fakeFetcher{err: revocations.ErrFetch}
	cache := revocations.NewCache(fetcher)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go cache.Run(ctx, 10*time.Millisecond)

	deadline := time.Now().Add(5 * time.Second)
	for fetcher.count() < 3 {
		if time.Now().After(deadline) {
			t.Fatalf("실패한 뒤 다시 받지 않는다(%d번)", fetcher.count())
		}
		time.Sleep(5 * time.Millisecond)
	}
}

func TestTheIntervalMatchesTheAuthServer(t *testing.T) {
	// 인증 서버가 문서에 싣는 refresh_interval_seconds(30)와 같다
	if revocations.RefreshInterval != 30*time.Second {
		t.Errorf("간격 = %v", revocations.RefreshInterval)
	}
}

func TestFetchRefusesAWrongDocumentAndAnUnreachableServer(t *testing.T) {
	logged := captureLog(t)
	wrong := serve(t, func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"revocations":[{"sub_sha256":"nope","min_ver":1}]}`))
	})
	closed := httptest.NewServer(http.NotFoundHandler())
	closed.Close()
	unreachable := revocations.HTTPFetcher{Client: closed.Client(), URL: closed.URL}
	malformed := revocations.HTTPFetcher{Client: http.DefaultClient, URL: "http://\x7f"}

	for name, fetcher := range map[string]revocations.HTTPFetcher{"틀린 문서": wrong, "닫힌 서버": unreachable, "읽을 수 없는 주소": malformed} {
		if _, err := fetcher.Fetch(context.Background()); !errors.Is(err, revocations.ErrFetch) {
			t.Errorf("%s: 오류 = %v", name, err)
		}
	}
	for _, reason := range []string{"모양이 틀린 문서다", "연결하지 못했다", "주소를 읽을 수 없다"} {
		if !strings.Contains(logged(), reason) {
			t.Errorf("로그에 %q 가 없다: %s", reason, logged())
		}
	}
}
