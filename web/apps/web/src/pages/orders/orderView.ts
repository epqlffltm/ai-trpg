// web/apps/web/src/pages/orders/orderView.ts
// 주문 내역(A8)이 보일 글. 순수한 함수다. 철회할 수 있는지는 서버가 정한 것(refundable, refund_blocked)만 본다.
// 화면이 7일을 세거나 크레딧을 썼는지 따지지 않는다.

import type { Order } from '../../api/types';

const STATUS: Record<Order['status'], string> = {
  pending: '결제 전',
  confirming: '결제 확인 중',
  paid: '충전됨',
  failed: '결제되지 않음',
  expired: '시간이 지남',
  refunding: '환불 처리 중',
  refunded: '환불됨',
};

/** 결제가 일어난(또는 일어났을 수 있는) 주문. 목록에 처음부터 보인다. 결제창만 열고 끝낸 것(결제 전, 시간이 지남)은 따로 */
const ATTEMPTED: ReadonlySet<Order['status']> = new Set<Order['status']>(['confirming', 'paid', 'failed', 'refunding', 'refunded']);

const BLOCKED: Record<NonNullable<Order['refund_blocked']>, string> = {
  window_closed: '결제한 지 7일이 지나 환불할 수 없습니다.',
  credits_used: '이 주문의 골드를 썼거나 서술 값으로 묶여 있어 환불할 수 없습니다.',
};

export function statusLabel(status: Order['status']): string {
  return STATUS[status];
}

export function isAttempted(order: Order): boolean {
  return ATTEMPTED.has(order.status);
}

/** 보일 주문. 치르지 않은 것까지 보이기를 켜지 않았으면 결제가 일어난 것만 */
export function visibleOrders(orders: Order[], showAll: boolean): Order[] {
  return showAll ? orders : orders.filter(isAttempted);
}

/** 숨긴 주문의 수. 켜는 단추에 적는다 */
export function hiddenCount(orders: Order[]): number {
  return orders.filter((order) => !isAttempted(order)).length;
}

/** 환불할 수 없는 까닭. 치른 주문이 아니거나 할 수 있으면 null */
export function blockedText(order: Order): string | null {
  return order.refund_blocked ? BLOCKED[order.refund_blocked] : null;
}

/** 청약철회의 409 의 까닭(code). 모르는 것은 한 말 */
const REFUSED: Record<string, string> = {
  'refund.window_closed': '결제한 지 7일이 지나 환불할 수 없습니다.',
  'refund.credits_used': '이 주문의 골드를 썼거나 서술 값으로 묶여 있어 환불할 수 없습니다.',
  'refund.not_paid': '결제가 끝난 주문이 아닙니다.',
  'refund.refused': '결제 대행사가 취소를 거절했습니다. 골드는 그대로 있습니다.',
  'refund.busy': '같은 주문의 다른 요청과 엇갈렸습니다. 다시 보내 주세요.',
};

export function refusedText(code: string | undefined): string {
  return (code ? REFUSED[code] : undefined) ?? '환불할 수 없습니다.';
}

/** 다시 보내면 될 수 있는 까닭(엇갈림) */
export function refusalRetryable(code: string | undefined): boolean {
  return code === 'refund.busy';
}
