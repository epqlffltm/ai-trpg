// web/apps/web/src/pages/wallet/autoChargeQueries.ts
// 자동 충전(#980)의 설정과 카드, 최근 내역을 읽는 열쇠. 지갑(A6)의 자동 충전 칸이 쓴다. 바꾸면 이 열쇠에 넣거나 다시 읽는다.
// 최근 내역의 열쇠는 설정의 열쇠 아래에 있다. 설정이나 카드를 바꿔 설정을 다시 읽으면 내역도 다시 읽는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchAutoCharge } from '../../api/autoCharge';
import { fetchAutoChargeHistory } from '../../api/autoChargeHistory';

export const AUTO_CHARGE_KEY = ['billing', 'auto-charge'] as const;

export function autoChargeQuery() {
  return queryOptions({
    queryKey: AUTO_CHARGE_KEY,
    queryFn: ({ signal }) => fetchAutoCharge(signal),
  });
}

export const AUTO_CHARGE_HISTORY_KEY = [...AUTO_CHARGE_KEY, 'history'] as const;

export function autoChargeHistoryQuery() {
  return queryOptions({
    queryKey: AUTO_CHARGE_HISTORY_KEY,
    queryFn: ({ signal }) => fetchAutoChargeHistory(signal),
  });
}
