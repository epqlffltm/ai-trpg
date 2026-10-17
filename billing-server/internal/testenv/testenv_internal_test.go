// billing-server/internal/testenv/testenv_internal_test.go

package testenv

import (
	"net/url"
	"testing"
)

func TestTheLimitHoldsWhateverTheAddressAsks(t *testing.T) {
	// 접속 주소가 더 많이 열라고 해도(pool_max_conns) 테스트의 풀은 4개까지다. PC 의 CPU 수와 상관없이 이 테스트로 확인한다
	address, err := url.Parse(DatabaseURL(t))
	if err != nil {
		t.Fatalf("접속 주소를 읽지 못했다: %v", err)
	}
	query := address.Query()
	query.Set("pool_max_conns", "50")
	address.RawQuery = query.Encode()

	pool, err := newPool(address.String())
	if err != nil {
		t.Fatalf("풀을 만들지 못했다: %v", err)
	}
	defer pool.Close()

	if got := pool.Config().MaxConns; got != MaxConns {
		t.Errorf("풀의 가장 많은 연결 수 = %d. %d 여야 한다", got, MaxConns)
	}
}
