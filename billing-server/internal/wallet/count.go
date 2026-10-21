// billing-server/internal/wallet/count.go

package wallet

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet/walletdb"
)

// CountChunk 는 사람 수를 셀 때 한 쿼리에 싣는 사용자 번호의 가장 많은 수다.
// 명단이 수십만 명이어도 쿼리 하나의 인자가 끝없이 커지지 않게 나눠 센다.
const CountChunk = 1000

// CountGranted 는 users 가운데 그 이름(key)의 지급을 이미 받은 사람이 몇인지 센다. 다 썼거나 사라진 것도 받은 것이다.
// 읽기만 하고 잠그지 않는다. 운영자가 주기 전에 미리 보는 것이라 그사이 받은 사람이 생겨도 주는 쪽(GrantFreeOnce)이 다시 막는다.
func (s *Service) CountGranted(ctx context.Context, key string, users []uuid.UUID) (int, error) {
	queries := walletdb.New(s.pool)
	return countInChunks(users, func(chunk []uuid.UUID) (int64, error) {
		return queries.CountFreeGrantsWithKey(ctx, walletdb.CountFreeGrantsWithKeyParams{GrantKey: key, UserIds: chunk})
	})
}

// CountWallets 는 users 가운데 지갑이 있는 사람이 몇인지 센다. 지갑은 크레딧이 처음 바뀔 때 생긴다.
// 읽기만 한다.
func (s *Service) CountWallets(ctx context.Context, users []uuid.UUID) (int, error) {
	queries := walletdb.New(s.pool)
	return countInChunks(users, func(chunk []uuid.UUID) (int64, error) {
		return queries.CountWallets(ctx, chunk)
	})
}

// countInChunks 는 users 를 CountChunk 명씩 나눠 count 로 세고 더한다. users 에 같은 번호가 두 번 없어야 맞다.
func countInChunks(users []uuid.UUID, count func([]uuid.UUID) (int64, error)) (int, error) {
	total := 0
	for start := 0; start < len(users); start += CountChunk {
		end := min(start+CountChunk, len(users))
		n, err := count(users[start:end])
		if err != nil {
			return 0, err
		}
		total += int(n)
	}
	return total, nil
}
