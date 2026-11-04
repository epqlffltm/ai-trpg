// web/apps/web/src/api/autoChargeHistory.ts
// 자동 충전(결제 서버, #980)의 최근 내역. 충전할 일을 늦게 적힌 것부터 20개 받는다(결제됨, 거절, 하지 않음, 처리 중).
// 결제된 것의 번호는 주문 번호와 같다. 카드와 결제 대행사의 거절 코드는 오지 않는다.

import { apiRequest } from './http';
import type { AutoChargeHistory } from './types';

export function fetchAutoChargeHistory(signal?: AbortSignal): Promise<AutoChargeHistory> {
  return apiRequest<AutoChargeHistory>('/api/v1/billing/auto-charge/history', signal ? { signal } : {});
}
