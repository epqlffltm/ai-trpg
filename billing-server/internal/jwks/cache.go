// billing-server/internal/jwks/cache.go

package jwks

import (
	"context"
	"crypto/rsa"
	"errors"
	"log/slog"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/obs"
)

// 토큰을 검증할 때마다 인증 서버에 묻지 않는다. 한 번 가져온 키를 기억해 두고 쓴다.
// 인증 서버가 잠깐 죽어 있어도, 기억한 키가 있으면 이미 로그인한 사용자의 요청을 계속 처리한다.
// 게임 서버(trpg-server/app/auth/jwks.py)와 같은 규칙과 값이다. 서버마다 다르면 인증 서버가 죽었을 때 어디는 막히고 어디는 통한다.
//
// 규칙은 다섯이다.
//  1. 기억한 지 CacheDuration(5분)이 지나면 다시 가져온다.
//  2. 기억에 없는 키 ID(kid)가 오면 다시 가져온다. 인증 서버가 키를 바꾼 경우다.
//  3. 다시 가져오기는 RefetchInterval 에 한 번만 시도한다.
//     가짜 kid 를 계속 보내 인증 서버에 요청이 몰리게 하는 것을 막고, 죽은 인증 서버를 요청마다 기다리지 않는다.
//  4. 다시 가져오기에 실패하면 기억하던 키를 계속 쓴다.
//  5. 다만 마지막으로 가져온 지 MaxStale(30분)이 지나면 기억하던 키를 버린다(#274).
//     그 뒤로는 다시 가져올 때까지 토큰을 받아들이지 않는다(ErrUnavailable, 주소는 503).
//
// 5 가 없으면 인증 서버에 닿지 못하는 동안 옛 키를 끝없이 믿는다. 서명 키가 새서 인증 서버가 그 키를 빼도(긴급 폐기),
// 이 서버는 그 키로 만든 토큰을 계속 받는다. 인증 서버를 쓰러뜨리면 그 기간을 원하는 만큼 늘릴 수 있다.
// 서명 키가 새면 만료 시각도 마음대로 정한 토큰을 만들 수 있어 access 토큰의 수명은 막아 주지 못한다.
// "이 서버가 그 키를 얼마나 빨리 안 믿게 되나"만이 막는다. 인증 서버가 살아 있으면 5분, 죽어 있어도 30분이다.
// 대신 인증 서버가 30분 넘게 죽어 있으면 이 서버의 로그인이 필요한 요청도 모두 막힌다.
const (
	// CacheDuration 은 가져온 키를 기억하는 시간이다. 인증 서버가 뺀 키를 이만큼 더 믿을 수 있다(긴급 폐기에 걸리는 시간).
	CacheDuration = 5 * time.Minute
	// MaxStale 은 다시 가져오지 못해도 기억한 키를 쓰는 가장 긴 시간이다. 마지막으로 가져온 때부터 센다. 지나면 키를 버린다.
	MaxStale = 30 * time.Minute
	// RefetchInterval 은 다시 가져오기를 시도하는 최소 간격이다.
	RefetchInterval = time.Minute
)

var (
	// ErrUnavailable 은 기억한 키가 하나도 없고 지금 가져올 수도 없다는 오류다.
	// 토큰이 맞는지 틀린지 알 수 없다. 틀렸다고 답하면 안 된다.
	ErrUnavailable = errors.New("검증에 쓸 키가 없다")
	// ErrUnknownKey 는 키 목록은 있지만 그 안에 이 kid 가 없다는 오류다.
	// 이 서버가 믿는 키로 서명한 토큰이 아니다.
	ErrUnknownKey = errors.New("모르는 키 ID 다")
)

// flightKey 는 "지금 가져오는 중"을 하나로 묶는 이름이다. 주소가 하나라 이름도 하나다.
const flightKey = "jwks"

// Cache 는 가져온 키를 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.
type Cache struct {
	fetcher Fetcher
	// now 는 지금 시각을 알려 준다. 테스트가 한 시간을 기다리지 않고 시간을 돌릴 수 있게 밖에서 받는다.
	now func() time.Time

	// mu 는 아래 세 값을 지킨다. 여러 요청이 동시에 읽고, 가져왔을 때만 쓴다.
	// 인증 서버를 부르는 동안에는 쥐지 않는다. 쥐고 있으면 그동안 다른 요청이 기억한 키도 읽지 못한다.
	mu            sync.RWMutex
	keys          KeySet
	fetchedAt     time.Time
	lastAttemptAt time.Time

	// flight 는 여러 요청이 동시에 다시 가져오려 할 때 한 번만 가져오게 한다.
	// 먼저 온 요청이 가져오는 동안 나머지는 그 결과를 기다린다.
	// 기다리지 않고 지나가면, 아직 키가 도착하지 않아서 멀쩡한 토큰을 거부하게 된다.
	flight singleflight.Group
}

// NewCache 는 빈 캐시를 만든다. 만드는 것만으로는 인증 서버를 부르지 않는다. 처음 키가 필요할 때 부른다.
func NewCache(fetcher Fetcher, now func() time.Time) *Cache {
	return &Cache{fetcher: fetcher, now: now}
}

// Key 는 kid 에 해당하는 키를 돌려준다.
// 키 목록이 아예 없으면 ErrUnavailable, 목록에 그 kid 가 없으면 ErrUnknownKey 다.
func (c *Cache) Key(ctx context.Context, kid string) (*rsa.PublicKey, error) {
	if c.needsRefetch(kid) {
		c.refetchOnce(ctx)
	}
	c.forgetIfTooStale(ctx)
	return c.find(kid)
}

// forgetIfTooStale 은 마지막으로 가져온 지 MaxStale 이 지났으면 기억한 키를 버린다. 다시 가져올 때까지 토큰을 받아들이지 않는다.
// 로그인이 필요한 요청이 모두 막히는 일이라 사람이 봐야 한다. 버릴 때 error 로 한 번 남긴다(버린 뒤에는 버릴 키가 없다).
func (c *Cache) forgetIfTooStale(ctx context.Context) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if len(c.keys) == 0 || c.now().Sub(c.fetchedAt) < MaxStale {
		return
	}
	slog.ErrorContext(ctx, "공개키를 오래 다시 가져오지 못해 기억한 키를 버렸다. 인증 서버를 확인해야 한다",
		slog.String(obs.FieldOperation, fetchOperation),
		slog.String(obs.FieldErrorCode, fetchErrorCode),
		slog.Int("key_count", len(c.keys)),
		slog.Float64("max_stale_seconds", MaxStale.Seconds()),
	)
	c.keys = nil
}

// find 는 기억한 것에서 kid 를 찾는다.
func (c *Cache) find(kid string) (*rsa.PublicKey, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	if len(c.keys) == 0 {
		return nil, ErrUnavailable
	}
	key, ok := c.keys[kid]
	if !ok {
		return nil, ErrUnknownKey
	}
	return key, nil
}

// needsRefetch 는 기억한 것으로는 부족한지 본다. 기억 시간이 지났거나, 모르는 kid 다.
func (c *Cache) needsRefetch(kid string) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()

	if c.fetchedAt.IsZero() || c.now().Sub(c.fetchedAt) >= CacheDuration {
		return true
	}
	_, known := c.keys[kid]
	return !known
}

// refetchOnce 는 여러 요청이 동시에 와도 한 번만 다시 가져오게 한다.
//
// 가져오는 일은 이 요청의 context 를 그대로 쓰지 않는다. 취소만 떼어 낸 것을 쓴다.
// 먼저 온 요청의 사용자가 연결을 끊었다고, 같이 기다리던 다른 요청들의 가져오기까지 실패하면 안 된다.
// 시간 제한은 가져오는 쪽(Fetcher)이 건다.
func (c *Cache) refetchOnce(ctx context.Context) {
	detached := context.WithoutCancel(ctx)
	// 돌려주는 값을 쓰지 않는다. 결과는 캐시에 적히고, 부른 쪽은 캐시를 다시 읽는다
	_, _, _ = c.flight.Do(flightKey, func() (any, error) {
		c.refetch(detached)
		return nil, nil
	})
}

// refetch 는 시도해도 되는 때면 키 목록을 다시 가져온다. 실패하면 기억하던 키를 그대로 둔다.
func (c *Cache) refetch(ctx context.Context) {
	if !c.beginAttempt() {
		return
	}
	keys, err := c.fetcher.Fetch(ctx)
	if err != nil {
		slog.WarnContext(ctx, "기억한 키를 계속 쓴다", slog.Int("key_count", c.count()))
		return
	}
	c.store(keys)
}

// beginAttempt 는 지금 다시 가져오기를 시도해도 되는지 보고, 되면 시도한 시각을 적는다.
// 성공하든 실패하든 시도하기 전에 적는다. 실패한 직후에 또 시도하지 않는다.
func (c *Cache) beginAttempt() bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := c.now()
	if !c.lastAttemptAt.IsZero() && now.Sub(c.lastAttemptAt) < RefetchInterval {
		return false
	}
	c.lastAttemptAt = now
	return true
}

// store 는 새로 가져온 키 목록으로 통째로 바꾼다. 인증 서버가 뺀 키는 여기서 사라진다.
func (c *Cache) store(keys KeySet) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.keys = keys
	c.fetchedAt = c.now()
}

// count 는 기억한 키의 수다.
func (c *Cache) count() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.keys)
}
