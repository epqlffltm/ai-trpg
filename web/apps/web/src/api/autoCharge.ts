// web/apps/web/src/api/autoCharge.ts
// 자동 충전(결제 서버, #980). 카드를 등록하고 설정을 적는다. 골드가 기준 아래로 떨어지면 결제 서버가 그 카드로 산다.
//
// 카드 등록은 두 걸음이다(billing-server/README.md 의 "자동 충전").
//   1. 고객 키를 받는다(createCustomerKey). 결제 대행사의 카드 등록 창에 넣는다
//   2. 등록 창이 준 인증 키와 고객 키를 보낸다(registerCard). 서버가 빌링키를 받아 적는다. 빌링키는 화면에 오지 않는다
//
// 실패:
//   - 설정: 400 autocharge.invalid_settings, 409 autocharge.no_card, 403 payment.verification_required·payment.guardian_consent_required
//   - 카드: 400 card.invalid_request, 409 card.customer_key_mismatch(처음부터), 422 card.refused, 503 card.issuer_unavailable(다시)

import { apiRequest } from './http';
import type { AutoCharge, PaymentCard } from './types';

const BILLING = '/api/v1/billing';

/** 적어 둔 대로 사는 설정. 기준 골드는 다른 양처럼 글자다 */
export type AutoChargeSettings = { enabled: boolean; threshold: string; product_id: string; monthly_limit: number };

export function fetchAutoCharge(signal?: AbortSignal): Promise<AutoCharge> {
  return apiRequest<AutoCharge>(`${BILLING}/auto-charge`, signal ? { signal } : {});
}

export function saveAutoCharge(settings: AutoChargeSettings): Promise<AutoCharge> {
  return apiRequest<AutoCharge>(`${BILLING}/auto-charge`, { method: 'PUT', body: settings });
}

/** 카드 등록 창에 넣을 고객 키. 몇 번을 불러도 같다 */
export async function createCustomerKey(): Promise<string> {
  const answer = await apiRequest<{ customer_key: string }>(`${BILLING}/cards/customer-key`, { method: 'POST' });
  return answer.customer_key;
}

/** 등록 창이 준 인증 키로 카드를 등록한다. 이미 있으면 바꾼다 */
export function registerCard(authKey: string, customerKey: string): Promise<PaymentCard> {
  return apiRequest<PaymentCard>(`${BILLING}/cards`, { method: 'POST', body: { auth_key: authKey, customer_key: customerKey } });
}

/** 카드를 지우고 자동 충전을 끈다. 카드가 없어도 된다 */
export function removeCard(): Promise<void> {
  return apiRequest<void>(`${BILLING}/cards`, { method: 'DELETE' });
}
