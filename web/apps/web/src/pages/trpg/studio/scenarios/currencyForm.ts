// web/apps/web/src/pages/trpg/studio/scenarios/currencyForm.ts
// 시나리오의 화폐(#278)의 입력. 이름(20자), 단위(10자, 비워도 된다), 모두가 시작할 때 받는 돈, 상인이 사 주는 값의 백분율. 순수한 함수다.
// 화폐를 쓰지 않으면 null 이다. 값·상인·돈을 적었는데 화폐가 없으면 게시 점검이 알린다(currency_missing).
// 결제의 크레딧과 상관없는 게임 안의 돈이다.

import type { Currency } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { MONEY_MAX } from './itemRuleForm';

export const CURRENCY_NAME_MAX = 20;
export const CURRENCY_UNIT_MAX = 10;
export const DEFAULT_SELL_PERCENT = 50;

export type CurrencyDraft = { enabled: boolean; name: string; unit: string; starting: string; sellPercent: string };

export function currencyDraft(currency: Currency | null): CurrencyDraft {
  return {
    enabled: currency !== null,
    name: currency?.name ?? '',
    unit: currency?.unit ?? '',
    starting: String(currency?.starting ?? 0),
    sellPercent: String(currency?.sell_percent ?? DEFAULT_SELL_PERCENT),
  };
}

export function currencyHints(draft: CurrencyDraft): Record<string, string> {
  if (!draft.enabled) return {};
  const hints: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') hints.currency_name = '화폐의 이름을 적어 주세요.';
  else if (name.length > CURRENCY_NAME_MAX) hints.currency_name = `이름은 ${CURRENCY_NAME_MAX}자까지입니다.`;
  if (draft.unit.trim().length > CURRENCY_UNIT_MAX) hints.currency_unit = `단위는 ${CURRENCY_UNIT_MAX}자까지입니다.`;
  if (wholeNumber(draft.starting, 0, MONEY_MAX) === null) hints.starting = `0~${MONEY_MAX.toLocaleString('ko-KR')} 사이의 정수입니다.`;
  if (wholeNumber(draft.sellPercent, 0, 100) === null) hints.sell_percent = '0~100 사이의 정수입니다.';
  return hints;
}

export function toCurrency(draft: CurrencyDraft): Currency | null {
  if (!draft.enabled) return null;
  return {
    name: draft.name.trim(),
    unit: draft.unit.trim(),
    starting: Number(draft.starting.trim()),
    sell_percent: Number(draft.sellPercent.trim()),
  };
}

/** 돈의 글. "금화 30닢", 단위가 없으면 "금화 30", 화폐가 없으면 "돈 30" */
export function moneyText(currency: Currency | null, amount: number): string {
  if (!currency) return `돈 ${amount}`;
  return `${currency.name} ${amount}${currency.unit}`;
}
