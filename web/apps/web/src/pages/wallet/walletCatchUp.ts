// web/apps/web/src/pages/wallet/walletCatchUp.ts
// 지갑에 늦게 들어오는 돈을 따라잡는 때(순수한 값과 함수). 출석의 실버처럼 받은 것을 다른 서버의 워커가 나중에 맡기면
// 받기의 답이 온 직후에 읽은 잔액은 아직 그 전의 것이다. 몇 번 더 읽어 잔액이 바뀌면 멈춘다.

import type { Wallet } from '../../api/types';

/**
 * 다시 읽는 사이(밀리초, 앞의 읽기에서부터). 모두 더하면 약 20초다.
 * 인증 서버의 워커는 맡길 것이 없으면 5초 쉰다(auth-server 의 send_welcome_credits). 그 뒤 결제 서버에 맡긴다
 */
export const CATCH_UP_DELAYS = [1_000, 2_000, 3_000, 4_000, 5_000, 5_000];

/** 잔액이 바뀌었는가. 전의 잔액을 모르면 바뀐 것으로 본다(더 기다릴 기준이 없다) */
export function walletChanged(before: Wallet | undefined, after: Wallet | undefined): boolean {
  if (!before || !after) return true;
  return before.paid !== after.paid || before.free !== after.free;
}
