// billing-server/internal/jwks/cache_test.go

package jwks_test

import (
	"context"
	"crypto/rsa"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/jwks"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// fakeClock 은 테스트가 마음대로 돌리는 시계다. 한 시간을 기다리지 않고 한 시간 뒤로 간다.
type fakeClock struct {
	mu  sync.Mutex
	now time.Time
}

func newClock() *fakeClock {
	return &fakeClock{now: time.Date(2026, 10, 11, 9, 0, 0, 0, time.UTC)}
}

func (c *fakeClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *fakeClock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// fakeFetcher 는 정해 둔 대로 답하는 가짜 인증 서버다. 몇 번 불렸는지 센다.
type fakeFetcher struct {
	mu    sync.Mutex
	keys  jwks.KeySet
	err   error
	calls int
	// gate 가 있으면 닫힐 때까지 답하지 않는다. 가져오는 도중의 일을 볼 때 쓴다
	gate chan struct{}
	// entered 가 있으면 불릴 때마다 하나씩 보낸다. 가져오기가 시작된 것을 테스트가 안다
	entered chan struct{}
	// lastCtxErr 는 마지막으로 받은 context 가 그때 취소돼 있었는지다
	lastCtxErr error
}

func (f *fakeFetcher) Fetch(ctx context.Context) (jwks.KeySet, error) {
	f.mu.Lock()
	f.calls++
	gate, entered := f.gate, f.entered
	f.mu.Unlock()

	if entered != nil {
		// 받는 쪽이 없어도 멈추지 않는다. 알리지 못한 것은 버린다
		select {
		case entered <- struct{}{}:
		default:
		}
	}
	if gate != nil {
		<-gate
	}

	f.mu.Lock()
	defer f.mu.Unlock()
	f.lastCtxErr = ctx.Err()
	return f.keys, f.err
}

func (f *fakeFetcher) set(keys jwks.KeySet, err error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.keys, f.err = keys, err
}

func (f *fakeFetcher) count() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

// waitUntilFetching 은 가져오기가 시작될 때까지 기다린다. 시작되지 않으면 테스트를 실패시킨다.
// 그냥 기다리면, 가져오기가 아예 일어나지 않는 버그에서 테스트가 실패하지 않고 멈춘다.
func waitUntilFetching(t *testing.T, fetcher *fakeFetcher) {
	t.Helper()
	select {
	case <-fetcher.entered:
	case <-time.After(5 * time.Second):
		t.Fatal("가져오기가 시작되지 않았다")
	}
}

// keySet 은 kid 들로 키 목록을 만든다. 키의 내용은 테스트에 중요하지 않아서 같은 키를 돌려 쓴다.
func keySet(t *testing.T, kids ...string) jwks.KeySet {
	t.Helper()
	keys := jwks.KeySet{}
	for _, kid := range kids {
		keys[kid] = &testenv.NewSigningKey(t, 0, kid).Private.PublicKey
	}
	return keys
}

// newCache 는 가짜 인증 서버와 가짜 시계를 쓰는 캐시를 만든다. 로그는 찍지 않는다.
func newCache(t *testing.T, keys jwks.KeySet) (*jwks.Cache, *fakeFetcher, *fakeClock) {
	t.Helper()
	captureLog(t)
	fetcher := &fakeFetcher{keys: keys}
	clock := newClock()
	return jwks.NewCache(fetcher, clock.Now), fetcher, clock
}

func mustFind(t *testing.T, cache *jwks.Cache, kid string) *rsa.PublicKey {
	t.Helper()
	key, err := cache.Key(context.Background(), kid)
	if err != nil {
		t.Fatalf("%s 를 찾지 못했다: %v", kid, err)
	}
	return key
}

func TestCacheDoesNotFetchUntilAsked(t *testing.T) {
	_, fetcher, _ := newCache(t, keySet(t, "key-1"))

	// 만드는 것만으로는 인증 서버를 부르지 않는다. 인증 서버가 죽어 있어도 이 서버는 뜬다
	if fetcher.count() != 0 {
		t.Errorf("만들기만 했는데 %d번 불렀다", fetcher.count())
	}
}

func TestCacheFetchesOnceAndRemembers(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "key-1"))

	first := mustFind(t, cache, "key-1")
	clock.Advance(jwks.CacheDuration - time.Second)
	second := mustFind(t, cache, "key-1")

	if fetcher.count() != 1 {
		t.Errorf("%d번 불렀다. 기억하는 동안은 한 번이어야 한다", fetcher.count())
	}
	if first != second {
		t.Error("같은 kid 인데 다른 키가 돌아왔다")
	}
}

func TestCacheRefetchesAfterItExpires(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "key-1"))
	mustFind(t, cache, "key-1")

	clock.Advance(jwks.CacheDuration)
	fetcher.set(keySet(t, "key-2"), nil)
	mustFind(t, cache, "key-2")

	if fetcher.count() != 2 {
		t.Errorf("%d번 불렀다. 기억 시간이 지났으니 두 번이어야 한다", fetcher.count())
	}
	// 새 목록으로 통째로 바뀐다. 인증 서버가 뺀 키는 더 믿지 않는다
	if _, err := cache.Key(context.Background(), "key-1"); !errors.Is(err, jwks.ErrUnknownKey) {
		t.Errorf("빠진 키의 오류 = %v, 기대 = ErrUnknownKey", err)
	}
}

func TestCacheRefetchesForAnUnknownKeyID(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "old"))
	mustFind(t, cache, "old")

	// 인증 서버가 키를 바꿨다. 기억 시간이 남았어도 모르는 kid 를 만나면 다시 가져온다
	fetcher.set(keySet(t, "old", "new"), nil)
	clock.Advance(jwks.RefetchInterval)
	mustFind(t, cache, "new")

	if fetcher.count() != 2 {
		t.Errorf("%d번 불렀다. 두 번이어야 한다", fetcher.count())
	}
}

func TestCacheLimitsRefetchesForUnknownKeyIDs(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "real"))
	mustFind(t, cache, "real")

	// 가짜 kid 를 쏟아부어도 인증 서버를 요청마다 부르지 않는다
	for range 50 {
		if _, err := cache.Key(context.Background(), "made-up"); !errors.Is(err, jwks.ErrUnknownKey) {
			t.Fatalf("오류 = %v, 기대 = ErrUnknownKey", err)
		}
	}
	if fetcher.count() != 1 {
		t.Errorf("간격 안에 %d번 불렀다. 처음의 한 번뿐이어야 한다", fetcher.count())
	}

	clock.Advance(jwks.RefetchInterval)
	_, _ = cache.Key(context.Background(), "made-up")
	if fetcher.count() != 2 {
		t.Errorf("간격이 지났는데 %d번 불렀다. 두 번이어야 한다", fetcher.count())
	}
}

func TestCacheKeepsOldKeysWhenRefetchFails(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "key-1"))
	original := mustFind(t, cache, "key-1")

	// 기억 시간이 지났는데 인증 서버가 죽어 있다. 기억하던 키를 계속 쓴다.
	// 인증 서버가 죽었다고 이미 로그인한 사용자가 쫓겨나지 않는다
	clock.Advance(2 * jwks.CacheDuration)
	fetcher.set(nil, jwks.ErrFetch)

	if kept := mustFind(t, cache, "key-1"); kept != original {
		t.Error("실패한 뒤에 키가 바뀌었다")
	}
	if fetcher.count() != 2 {
		t.Errorf("%d번 불렀다. 두 번이어야 한다", fetcher.count())
	}
}

func TestCacheDoesNotHammerADeadAuthServer(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "key-1"))
	mustFind(t, cache, "key-1")
	clock.Advance(2 * jwks.CacheDuration)
	fetcher.set(nil, jwks.ErrFetch)

	// 실패한 직후에 또 시도하지 않는다. 죽은 인증 서버를 요청마다 기다리지 않는다
	for range 20 {
		mustFind(t, cache, "key-1")
	}
	if fetcher.count() != 2 {
		t.Errorf("간격 안에 %d번 불렀다. 처음과 실패한 한 번, 두 번이어야 한다", fetcher.count())
	}

	// 간격이 지나면 다시 시도하고, 살아났으면 새 키를 받는다
	clock.Advance(jwks.RefetchInterval)
	fetcher.set(keySet(t, "key-2"), nil)
	mustFind(t, cache, "key-2")
	if fetcher.count() != 3 {
		t.Errorf("%d번 불렀다. 세 번이어야 한다", fetcher.count())
	}
}

func TestCacheIsUnavailableWithoutAnyKeys(t *testing.T) {
	cache, fetcher, clock := newCache(t, nil)
	fetcher.set(nil, jwks.ErrFetch)

	// 기억한 키가 하나도 없고 가져올 수도 없다. 토큰이 틀렸다(ErrUnknownKey)고 답하면 안 된다.
	// 맞는지 틀린지 모르는 것이다
	if _, err := cache.Key(context.Background(), "key-1"); !errors.Is(err, jwks.ErrUnavailable) {
		t.Errorf("오류 = %v, 기대 = ErrUnavailable", err)
	}

	// 간격이 지나 인증 서버가 살아나면 그때부터 된다
	clock.Advance(jwks.RefetchInterval)
	fetcher.set(keySet(t, "key-1"), nil)
	mustFind(t, cache, "key-1")
}

func TestCacheFetchesOnceForConcurrentRequests(t *testing.T) {
	const requests = 50
	cache, fetcher, _ := newCache(t, keySet(t, "key-1"))
	fetcher.gate = make(chan struct{})
	fetcher.entered = make(chan struct{}, requests)

	// 요청 여럿이 동시에 온다. 키는 아직 없다
	results := make(chan error, requests)
	for range requests {
		go func() {
			_, err := cache.Key(context.Background(), "key-1")
			results <- err
		}()
	}

	// 하나가 가져오기 시작했다. 나머지는 그 결과를 기다리는 중이다. 아직 아무도 답을 받지 못했다
	waitUntilFetching(t, fetcher)
	select {
	case err := <-results:
		t.Fatalf("가져오기가 끝나기 전에 답이 나왔다: %v", err)
	case <-time.After(50 * time.Millisecond):
	}

	close(fetcher.gate)
	for range requests {
		select {
		case err := <-results:
			// 먼저 온 요청이 가져오는 동안 지나가 버리면, 키가 아직 없어서 멀쩡한 요청이 실패한다
			if err != nil {
				t.Errorf("기다리던 요청이 실패했다: %v", err)
			}
		case <-time.After(5 * time.Second):
			t.Fatal("가져오기가 끝났는데 답을 받지 못한 요청이 있다")
		}
	}
	if fetcher.count() != 1 {
		t.Errorf("%d번 불렀다. 동시에 와도 한 번이어야 한다", fetcher.count())
	}
}

func TestCacheFetchSurvivesTheFirstCallerLeaving(t *testing.T) {
	cache, fetcher, _ := newCache(t, keySet(t, "key-1"))
	fetcher.gate = make(chan struct{})
	fetcher.entered = make(chan struct{}, 1)

	// 먼저 온 요청의 사용자가 가져오는 도중에 연결을 끊는다
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := cache.Key(ctx, "key-1")
		done <- err
	}()
	waitUntilFetching(t, fetcher)
	cancel()
	close(fetcher.gate)
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("먼저 온 요청이 끝나지 않았다")
	}

	// 가져오기는 취소되지 않은 채로 끝났다. 뒤의 요청이 그 키를 쓴다
	fetcher.mu.Lock()
	ctxErr := fetcher.lastCtxErr
	fetcher.mu.Unlock()
	if ctxErr != nil {
		t.Errorf("가져오는 쪽이 받은 context 가 취소됐다: %v", ctxErr)
	}
	mustFind(t, cache, "key-1")
	if fetcher.count() != 1 {
		t.Errorf("%d번 불렀다. 한 번이어야 한다", fetcher.count())
	}
}

func TestCacheServesReadersWhileFetching(t *testing.T) {
	cache, fetcher, clock := newCache(t, keySet(t, "known"))
	mustFind(t, cache, "known")

	// 모르는 kid 때문에 다시 가져오는 중이다. 인증 서버가 답하지 않고 있다
	clock.Advance(jwks.RefetchInterval)
	fetcher.gate = make(chan struct{})
	fetcher.entered = make(chan struct{}, 1)
	go func() { _, _ = cache.Key(context.Background(), "unknown") }()
	waitUntilFetching(t, fetcher)

	// 그동안에도 아는 키로 온 요청은 기다리지 않고 답을 받는다.
	// 가져오는 동안 잠금을 쥐고 있으면 여기서 멈춘다
	answered := make(chan error, 1)
	go func() {
		_, err := cache.Key(context.Background(), "known")
		answered <- err
	}()
	select {
	case err := <-answered:
		if err != nil {
			t.Errorf("아는 키인데 실패했다: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("가져오는 동안 아는 키의 요청이 멈췄다")
	}
	close(fetcher.gate)
}
