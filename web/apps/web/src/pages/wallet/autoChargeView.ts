// web/apps/web/src/pages/wallet/autoChargeView.ts
// 자동 충전(#980)의 순수한 함수. 설정의 입력 칸, 보낼 값과 그 검사, 시험용 카드 등록의 인증 키.

import type { AutoChargeSettings } from '../../api/autoCharge';
import type { AutoCharge, Product } from '../../api/types';

/** 기준 골드의 가장 큰 값. 서버와 같다 */
export const MAX_THRESHOLD = 100_000;
/** 한 달 상한의 가장 큰 값(원). 서버와 같다 */
export const MAX_MONTHLY_LIMIT = 500_000;

export type AutoChargeDraft = { enabled: boolean; threshold: string; productId: string; monthlyLimit: string };

/** 입력 칸의 처음 값. 적은 적이 없으면 꺼 둔 채 기준 500, 첫 상품, 한 달 30,000 원이다 */
export function initialDraft(current: AutoCharge, products: Product[]): AutoChargeDraft {
  const settings = current.settings;
  if (settings) {
    return {
      enabled: settings.enabled,
      threshold: settings.threshold,
      productId: settings.product_id,
      monthlyLimit: String(settings.monthly_limit),
    };
  }
  return { enabled: false, threshold: '500', productId: products[0]?.id ?? '', monthlyLimit: '30000' };
}

export type DraftCheck = { settings: AutoChargeSettings; problem: null } | { settings: null; problem: string };

function wholeNumber(text: string): number | null {
  return /^\d{1,7}$/.test(text.trim()) ? Number(text.trim()) : null;
}

/** 입력 칸을 보낼 값으로 바꾼다. 틀렸으면 그 까닭이다. 서버도 같은 것을 다시 본다 */
export function toSettings(draft: AutoChargeDraft, products: Product[]): DraftCheck {
  const threshold = wholeNumber(draft.threshold);
  if (threshold === null || threshold > MAX_THRESHOLD) {
    return { settings: null, problem: `기준 골드는 0 에서 ${MAX_THRESHOLD.toLocaleString('ko-KR')} 사이의 정수로 적어 주세요.` };
  }
  const product = products.find((one) => one.id === draft.productId);
  if (!product) return { settings: null, problem: '살 상품을 골라 주세요.' };
  const limit = wholeNumber(draft.monthlyLimit);
  if (limit === null || limit < 1 || limit > MAX_MONTHLY_LIMIT) {
    return { settings: null, problem: `한 달 상한은 1 에서 ${MAX_MONTHLY_LIMIT.toLocaleString('ko-KR')} 원 사이로 적어 주세요.` };
  }
  if (limit < product.price) return { settings: null, problem: '한 달 상한은 고른 상품의 값보다 작을 수 없습니다.' };
  return {
    settings: { enabled: draft.enabled, threshold: String(threshold), product_id: product.id, monthly_limit: limit },
    problem: null,
  };
}

/** 시험용 카드 등록 창에서 고를 결과. prefix 는 인증 키의 앞머리다(결제 서버의 가짜 결제 대행사) */
export const FAKE_CARD_OUTCOMES = [
  { prefix: 'fake_card_ok_', label: '카드 등록', hint: '등록됩니다.' },
  { prefix: 'fake_card_refused_', label: '카드 거절', hint: '등록되지 않습니다.' },
  { prefix: 'fake_card_lost_', label: '답이 오지 않음', hint: '등록했는지 모르는 채로 끝납니다. 다시 등록하면 됩니다.' },
] as const;

/** 시험용 카드로 자동 결제할 때의 결과. 표시는 빌링키에 들어가 결제 서버의 가짜가 읽는다 */
export const FAKE_CHARGE_MARKS = [
  { mark: '', label: '자동 결제가 승인됨' },
  { mark: 'charge_declined', label: '자동 결제가 거절됨' },
  { mark: 'charge_lost', label: '자동 결제에 답이 오지 않음' },
] as const;

/** 시험용 카드 등록의 인증 키. 등록마다 다르게 만든다 */
export function fakeAuthKey(prefix: string, mark: string, unique: string): string {
  return `${prefix}${unique.replace(/[^A-Za-z0-9]/g, '')}${mark ? `_${mark}` : ''}`;
}
