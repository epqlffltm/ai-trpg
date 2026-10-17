// billing-server/internal/revocations/revocations.go

// Package revocations 는 인증 서버가 내주는 끊긴 세션의 목록을 받아 기억한다(#274).
//
// 이 서버는 토큰의 서명과 만료만 보고 인증 서버에 묻지 않는다. 그래서 인증 서버에서 세션을 끊어도
// (비밀번호 변경, 계정 정지 등) 그 사용자의 access 토큰은 만료(15분)까지 통했다.
// 인증 서버가 끊긴 세션의 목록을 내주고, 이 서버가 RefreshInterval 마다 받아 간다. 끊은 뒤 30초쯤이면 여기서도 막힌다.
// 목록의 모양은 인증 서버 README 의 "다른 서버에서 토큰을 검증하는 방법" 5단계에 있다.
//
// 목록은 요청과 상관없이 따로 받는다(Cache.Run). 요청이 인증 서버를 기다리지 않는다.
// 받지 못하면 마지막으로 받은 목록을 그대로 쓴다. 한 번도 받지 못했으면 아무 세션도 끊긴 것으로 보지 않는다.
// 줄은 access 토큰의 수명이 지나면 어차피 무의미해지므로, 공개키(jwks)와 달리 버리는 상한을 두지 않는다.
package revocations

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"log/slog"
	"sync"
	"time"
)

// RefreshInterval 은 목록을 다시 받는 간격이다. 인증 서버가 정한 값(refresh_interval_seconds)과 같다.
const RefreshInterval = 30 * time.Second

// Digest 는 토큰의 sub 를 목록에 실린 모양(SHA-256 의 16진수 64자)으로 바꾼다. 인증 서버와 같은 식이다.
func Digest(sub string) string {
	sum := sha256.Sum256([]byte(sub))
	return hex.EncodeToString(sum[:])
}

// List 는 끊긴 세션들이다. 사용자(sub 의 Digest)마다, 받아들이는 가장 낮은 세션 버전을 담는다.
type List map[string]int

// Revoked 는 그 사용자의 그 버전의 토큰이 끊긴 세션의 것인지 본다. 목록에 있고 버전이 min_ver 보다 작으면 끊긴 것이다.
func (l List) Revoked(sub string, version int) bool {
	minVersion, listed := l[Digest(sub)]
	return listed && version < minVersion
}

// Fetcher 는 목록을 받아 오는 것의 모양이다. 실제 서버는 HTTPFetcher 를, 테스트는 가짜를 넣는다.
type Fetcher interface {
	Fetch(ctx context.Context) (List, error)
}

// Cache 는 마지막으로 받은 목록을 기억한다. 앱 하나에 하나만 만들어 모든 요청이 함께 쓴다.
type Cache struct {
	fetcher Fetcher

	// mu 는 list 를 지킨다. 요청들이 읽고, 받았을 때만 바꾼다
	mu   sync.RWMutex
	list List
}

// NewCache 는 빈 캐시를 만든다. 받기 전에는 아무 세션도 끊긴 것으로 보지 않는다.
func NewCache(fetcher Fetcher) *Cache {
	return &Cache{fetcher: fetcher}
}

// Revoked 는 기억한 목록으로 그 토큰이 끊긴 세션의 것인지 본다.
func (c *Cache) Revoked(sub string, version int) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.list.Revoked(sub, version)
}

// Refresh 는 목록을 한 번 받아 바꾼다. 받지 못하면 기억하던 목록을 그대로 두고 오류를 돌려준다.
func (c *Cache) Refresh(ctx context.Context) error {
	list, err := c.fetcher.Fetch(ctx)
	if err != nil {
		return err
	}
	c.mu.Lock()
	c.list = list
	c.mu.Unlock()
	return nil
}

// Run 은 ctx 가 끝날 때까지 interval 마다 목록을 받는다. 처음 한 번은 바로 받는다.
// 받지 못한 것은 HTTPFetcher 가 남긴다. 다음 바퀴가 다시 받는다.
func (c *Cache) Run(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if err := c.Refresh(ctx); err != nil {
			slog.DebugContext(ctx, "끊긴 세션의 목록을 받지 못해 기억한 것을 쓴다")
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
