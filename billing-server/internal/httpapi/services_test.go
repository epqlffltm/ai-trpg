// billing-server/internal/httpapi/services_test.go

// 가짜를 끼우지 않고 실제 서비스와 DB 로 주소들을 끝까지 지나는 테스트가 함께 쓰는 도구.
package httpapi_test

import (
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/app"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
)

// realRules 는 그 테스트들이 쓰는 규칙이다. 무료 크레딧은 1시간, 홀드와 주문은 하루 뒤에 만료된다.
var realRules = config.Rules{SpendFreeFirst: true, FreeCreditTTL: time.Hour, HoldTTL: 24 * time.Hour, OrderTTL: 24 * time.Hour}

// realServices 는 서버와 같은 방법으로 서비스들을 만든다. 만들지 못하면 테스트를 멈춘다.
func realServices(t *testing.T, pool *pgxpool.Pool, now func() time.Time) app.Services {
	t.Helper()
	services, err := app.NewServices(pool, realRules, now)
	if err != nil {
		t.Fatalf("서비스를 만들지 못했다: %v", err)
	}
	return services
}
