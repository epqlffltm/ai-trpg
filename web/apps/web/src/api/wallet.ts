// web/apps/web/src/api/wallet.ts
// 내 지갑(결제 서버, A6). 잔액(골드는 paid, 실버는 free)과 원장. 읽기만 한다.
// 지갑이 없는 사람도 200 이고 모두 "0" 이다. 503 은 잠시 뒤 다시 부를 것이다(로그아웃시키지 않는다).

import { apiRequest } from './http';
import type { Wallet, WalletEntries } from './types';

const BILLING = '/api/v1/billing';

/** 원장의 한 쪽에 읽는 줄 수(서버는 1~100) */
export const ENTRY_PAGE_SIZE = 20;

/** 지금 쓸 수 있는 크레딧과 곧 사라질 실버 */
export function fetchWallet(signal?: AbortSignal): Promise<Wallet> {
  return apiRequest<Wallet>(`${BILLING}/wallet`, signal ? { signal } : {});
}

/** 원장의 한 쪽. 최근 것부터. before 는 앞 쪽의 next_before(첫 쪽이면 비운다) */
export function fetchWalletEntries(before: string | undefined, signal?: AbortSignal): Promise<WalletEntries> {
  return apiRequest<WalletEntries>(`${BILLING}/wallet/entries`, {
    query: { limit: ENTRY_PAGE_SIZE, before },
    ...(signal ? { signal } : {}),
  });
}
