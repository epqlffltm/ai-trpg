// web/apps/web/src/pages/trpg/room/money.ts
// 판의 돈(#278). 순수한 함수다. 돈의 이름과 단위는 테이블의 화폐(TableDetail.currency)이고, 가진 돈은 시트(sheet.money)다.
// 결제의 크레딧(골드·실버)과 상관없다. 화면에서도 "돈"이라 부르고, 크레딧과 다른 자리에 둔다.
//
// 값을 정하는 것은 서버다(trpg-server/app/tables/money.py). 여기서 계산하는 것은 보내기 전에 보이는 어림이다.
//   - 사기: 물건의 값 × 개수
//   - 팔기: 하나의 값에 화폐의 백분율을 곱해 내림한 것 × 개수
// 화폐가 없는 판(currency: null)이면 돈도, 사고팔기도, 돈 건네기도 없다.

import type { TableDetail, TableMember } from '../../../api/types';

export type Currency = NonNullable<TableDetail['currency']>;

/** "30닢". 화폐가 없으면 숫자만 */
export function amountLabel(currency: Currency | null | undefined, amount: number): string {
  return `${amount.toLocaleString('ko-KR')}${currency?.unit ?? ''}`;
}

/** "금화 30닢" */
export function moneyLabel(currency: Currency, amount: number): string {
  return `${currency.name} ${amountLabel(currency, amount)}`;
}

/** 내 캐릭터가 가진 돈. 시트가 없으면 0 */
export function moneyOf(member: TableMember | undefined): number {
  return member?.sheet?.money ?? 0;
}

/** 판의 물건의 값. 화폐가 없거나 값이 없으면(사고팔 수 없는 물건) null */
export function itemPrice(table: TableDetail, entryId: string): number | null {
  if (!table.currency) return null;
  return table.items.find((item) => item.entry_id === entryId)?.price ?? null;
}

/** 상인이 사 주는가. 화폐가 있고 백분율이 0 이 아니다 */
export function merchantsBuy(table: TableDetail): boolean {
  return Boolean(table.currency && table.currency.sell_percent > 0);
}

/** 사는 값. 물건의 값 × 개수 */
export function buyingCost(price: number, count: number): number {
  return price * count;
}

/** 파는 값. 하나의 값에 백분율을 곱해 내림하고 개수를 곱한다(서버의 selling_price 와 같다) */
export function sellingGain(currency: Currency, price: number, count: number): number {
  return Math.floor((price * currency.sell_percent) / 100) * count;
}
