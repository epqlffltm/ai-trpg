// billing-server/internal/testenv/testenv_test.go

package testenv_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

func TestPoolOpensAtMostFourConnections(t *testing.T) {
	pool := testenv.Pool(t)

	// PC 의 CPU 수와 상관없이 같다. 기본값(CPU 의 수)이면 16스레드 PC 에서 16 이다
	if got := pool.Config().MaxConns; got != 4 {
		t.Errorf("풀의 가장 많은 연결 수 = %d. 4 여야 한다", got)
	}
}

func TestPoolUsesTheTestSchema(t *testing.T) {
	pool := testenv.Pool(t)

	var schema string
	if err := pool.QueryRow(t.Context(), "SELECT current_schema()").Scan(&schema); err != nil {
		t.Fatalf("스키마를 읽지 못했다: %v", err)
	}
	if schema != testenv.Schema {
		t.Errorf("스키마 = %q. %q 여야 한다", schema, testenv.Schema)
	}
}
