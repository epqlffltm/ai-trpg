// web/apps/web/src/pages/wallet/walletQueries.ts
// 지갑(A6)이 읽는 것의 열쇠와 부르는 함수. 머리의 잔액, 지갑 화면, 테이블 방이 함께 쓴다.
// 잔액은 주기로 읽지 않는다. 다시 읽는 때는 둘이다.
//   - 창에 돌아올 때. 앱의 기본은 끔이지만 잔액만 켠다. 30초 안이면 읽지 않는다(staleTime)
//   - 크레딧을 바꿀 수 있는 테이블의 일이 올 때(walletView.ts 의 WALLET_EVENTS, TableRoom)
// 열쇠의 앞(WALLET_KEY)을 무르면 잔액과 원장이 함께 다시 읽힌다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchWallet, fetchWalletEntries } from '../../api/wallet';

export const WALLET_KEY = ['billing', 'wallet'] as const;

export function walletQuery() {
  return queryOptions({
    queryKey: [...WALLET_KEY, 'balance'],
    queryFn: ({ signal }) => fetchWallet(signal),
    refetchOnWindowFocus: true,
  });
}

/** 원장. 최근 것부터 한 쪽씩. 다음 쪽은 앞 쪽의 next_before 로 읽고, null 이면 끝이다 */
export function walletEntriesQuery() {
  return infiniteQueryOptions({
    queryKey: [...WALLET_KEY, 'entries'],
    queryFn: ({ pageParam, signal }) => fetchWalletEntries(pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before ?? undefined,
  });
}
