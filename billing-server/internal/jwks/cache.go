// billing-server/internal/jwks/cache.go

package jwks

import (
	"context"
	"crypto/rsa"
	"errors"
	"log"
	"sync"
	"time"

	"golang.org/x/sync/singleflight"
)

// 토큰을 검증할 때마다 인증 서버에 묻지 않는다. 한 번 가져온 키를 기억해 두고 쓴다.
// 인증 서버가 죽어 있어도, 기억한 키가 있으면 이미 로그인한 사용자의 요청을 계속 처리한다.
// 게임 서버(game-server/app/auth/jwks.py)와 같은 규칙이다. 두 서버가 인증 서버의 장애에 똑같이 굴어야 한다.
//
// 규칙은 넷이다.
//  1. 기억한 지 CacheDuration 이 지나면 다시 가져온다.
//  2. 기억에 없는 키 ID(kid)가 오면 다시 가져온다. 인증 서버가 키를 바꾼 경우다.
//  3. 다시 가져오기는 RefetchInterval 에 한 번만 시도한다.
//     가짜 kid 를 계속 보내 인증 서버에 요청이 몰리게 하는 것을 막고, 죽은 인증 서버를 요청마다 기다리지 않는다.
//  4. 다시 가져오기에 실패하면 기억하던 키를 계속 쓴다.
const (
	// CacheDuration 은 가져온 키를 기억하는 시간이다.
	CacheDuration = time.Hour
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
	return c.find(kid)
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
		log.Printf("기억한 키 %d개를 계속 쓴다", c.count())
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
