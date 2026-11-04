// web/apps/web/src/pages/wallet/autoChargeQueries.ts
// 자동 충전(#980)의 설정과 카드를 읽는 열쇠. 지갑(A6)의 자동 충전 칸이 쓴다. 바꾸면 이 열쇠에 넣거나 다시 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchAutoCharge } from '../../api/autoCharge';

export const AUTO_CHARGE_KEY = ['billing', 'auto-charge'] as const;

export function autoChargeQuery() {
  return queryOptions({
    queryKey: AUTO_CHARGE_KEY,
    queryFn: ({ signal }) => fetchAutoCharge(signal),
  });
}
