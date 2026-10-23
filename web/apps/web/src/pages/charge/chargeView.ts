// web/apps/web/src/pages/charge/chargeView.ts
// 충전(A7)이 보일 글과 고를 것. 순수한 함수다. 값과 크레딧은 서버가 정한 것을 그대로 보인다.
// 결제 대행사의 거절 사유(failure_code)는 그대로 보이지 않고 화면의 말로 바꾼다(screens.md 의 A7 "확인할 것").

import type { Order, Product } from '../../api/types';

const WON = new Intl.NumberFormat('ko-KR');

/** "1,000원" */
export function wonLabel(price: number): string {
  return `${WON.format(price)}원`;
}

/** "1,000". 크레딧은 글자라 정수일 때만 쉼표를 넣는다 */
export function goldAmount(credits: string): string {
  return /^\d+$/.test(credits) ? WON.format(Number(credits)) : credits;
}

/** "골드 1,000" */
export function goldLabel(credits: string): string {
  return `골드 ${goldAmount(credits)}`;
}

export function productLabel(product: Product): string {
  return `${wonLabel(product.price)} · ${goldLabel(product.credits)}`;
}

/** 결제 대행사의 거절 사유. 가짜(card_declined …)와 토스페이먼츠의 것을 함께 받는다. 모르는 것은 한 말로 */
const FAILURES: Record<string, string> = {
  card_declined: '카드사가 결제를 거절했습니다.',
  unknown_payment_key: '결제창의 결과를 확인하지 못했습니다.',
  PAYMENT_MISMATCH: '결제 금액이나 주문이 맞지 않아 취소했습니다.',
  REJECT_CARD_PAYMENT: '카드사가 결제를 거절했습니다.',
  EXCEED_MAX_AMOUNT: '카드의 한도를 넘었습니다.',
};

export function failureText(code: string | null): string {
  return (code ? FAILURES[code] : undefined) ?? '결제가 이루어지지 않았습니다.';
}

/** 주문이 더 바뀌지 않는가. confirming 은 아직 모른다 */
export function isSettled(status: Order['status']): boolean {
  return status === 'paid' || status === 'failed' || status === 'expired' || status === 'refunded';
}

/** 결과 한 줄. 돈이 나가지 않은 실패는 그렇다고 함께 적는다 */
export function resultText(order: Order): string {
  switch (order.status) {
    case 'paid':
      return `충전을 마쳤습니다: ${goldLabel(order.credits)}`;
    case 'failed':
      return `${failureText(order.failure_code)} 돈은 나가지 않았습니다.`;
    case 'confirming':
      return '결제를 확인하는 중입니다. 실패한 것이 아닙니다. 잠시 뒤 다시 확인하거나 지갑에서 잔액을 보세요.';
    case 'expired':
      return '주문의 시간이 지났습니다. 돈은 나가지 않았습니다. 처음부터 다시 해 주세요.';
    default:
      return '결제를 마치지 않았습니다.';
  }
}

/**
 * 주문 만들기에 붙일 열쇠. 같은 상품을 다시 보내는 것(답을 받지 못함)이면 앞의 열쇠, 아니면 새 열쇠.
 * 같은 열쇠로 다른 상품을 보내면 서버가 409 다
 */
export function orderKey(pending: { productId: string; key: string } | null, productId: string, fresh: () => string): string {
  return pending && pending.productId === productId ? pending.key : fresh();
}
