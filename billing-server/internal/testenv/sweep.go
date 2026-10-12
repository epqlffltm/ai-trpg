// billing-server/internal/testenv/sweep.go

package testenv

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// 정리 작업(만료된 홀드, 주문, 무료 크레딧)과 대사를 시험하는 테스트가 쓰는 것들.
//
// 정리 작업은 사용자를 가리지 않는다. "지금"보다 앞서 만료된 줄을 스키마에서 모두 찾는다.
// 테스트들은 스키마 하나(billing_test)를 함께 쓰고, 패키지마다 동시에 돈다. 그래서 둘을 지킨다.
//
//  1. 정리 작업의 테스트는 SweepEra(2001년)의 시계를 쓴다. 다른 테스트는 모두 2026년의 시계를 쓴다.
//     정리 작업은 "지금"보다 앞선 줄만 건드리므로, 2001년의 정리는 다른 테스트의 줄에 닿지 않는다.
//  2. 정리 작업의 테스트끼리는 같은 시대를 쓰므로 ExclusiveSweep 으로 한 번에 하나만 돈다.
//     잠금은 DB 의 advisory lock 이라 패키지(프로세스)가 달라도 지켜진다.
//
// 앞서 돈 정리 작업의 테스트가 남긴 줄은 다음 정리에 함께 정리될 수 있다. 그래서 정리 작업의 테스트는 시작할 때
// SweepEnd 의 시계로 한 번 정리해 남은 것을 치우고, 센 수보다 자기가 만든 줄의 상태를 본다.

var (
	// SweepEra 는 정리 작업의 테스트가 쓰는 시각의 시작이다. 다른 테스트의 시각(2026년)보다 앞서야 한다.
	SweepEra = time.Date(2001, 1, 1, 9, 0, 0, 0, time.UTC)
	// SweepEnd 는 정리 작업의 테스트가 쓰는 시각의 끝이다. 이 시각으로 정리하면 앞선 테스트가 남긴 것이 모두 치워진다.
	// 다른 테스트의 시각보다 앞서므로 그 줄에는 닿지 않는다.
	SweepEnd = SweepEra.AddDate(10, 0, 0)
)

// sweepLockKey 는 정리 작업의 테스트끼리 나누는 advisory lock 의 번호다. 다른 곳에서 쓰지 않는 값이면 된다.
const sweepLockKey int64 = 0x5eed_b111

// ExclusiveSweep 은 정리 작업의 테스트가 한 번에 하나만 돌게 잠근다. 테스트가 끝나면 푼다.
// 잠금은 연결에 묶인다. 연결 하나를 테스트가 끝날 때까지 빌려 둔다.
// 테스트 하나에서 한 번만 부른다. 두 번 부르면 다른 연결로 같은 잠금을 기다려 멈춘다.
func ExclusiveSweep(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	conn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("잠글 연결을 얻지 못했다: %v", err)
	}
	if _, err := conn.Exec(ctx, "SELECT pg_advisory_lock($1)", sweepLockKey); err != nil {
		conn.Release()
		t.Fatalf("정리 작업의 테스트를 잠그지 못했다: %v", err)
	}
	t.Cleanup(func() {
		// 풀을 닫기 전에 돈다(Cleanup 은 나중에 건 것부터 돈다). 풀지 못해도 연결이 닫히면 풀린다
		_, _ = conn.Exec(context.Background(), "SELECT pg_advisory_unlock($1)", sweepLockKey)
		conn.Release()
	})
}
