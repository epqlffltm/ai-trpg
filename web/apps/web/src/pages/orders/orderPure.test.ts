// web/apps/web/src/pages/orders/orderPure.test.ts
// 주문 내역(A8)의 순수한 함수. 상태의 말, 처음에 보일 주문과 숨긴 수, 환불할 수 없는 까닭, 청약철회의 실패를 본다.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import type { Order } from '../../api/types';
import { blockedText, hiddenCount, statusLabel, visibleOrders } from './orderView';
import { describeRefundProblem } from './refundProblem';

function order(status: Order['status'], extra: Partial<Order> = {}): Order {
  return {
    id: `id-${status}`,
    product_id: 'credits-1000',
    price: 1000,
    credits: '1000',
    status,
    failure_code: null,
    created_at: '2026-10-23T00:00:00Z',
    expires_at: '2026-10-24T00:00:00Z',
    paid_at: null,
    refundable: false,
    refundable_until: null,
    refunded_at: null,
    refund_blocked: null,
    ...extra,
  };
}

describe('주문의 글', () => {
  it('결제가 일어난 주문만 처음에 보이고, 결제 전과 시간이 지난 것은 숨긴 수로 센다', () => {
    const all = [order('paid'), order('pending'), order('expired'), order('failed'), order('refunding')];
    expect(visibleOrders(all, false).map((one) => one.status)).toEqual(['paid', 'failed', 'refunding']);
    expect(visibleOrders(all, true)).toHaveLength(5);
    expect(hiddenCount(all)).toBe(2);
    expect(statusLabel('confirming')).toBe('결제 확인 중');
  });

  it('환불할 수 없는 까닭은 서버가 준 것으로', () => {
    expect(blockedText(order('paid', { refund_blocked: 'window_closed' }))).toContain('7일');
    expect(blockedText(order('paid', { refund_blocked: 'credits_used' }))).toContain('썼거나');
    expect(blockedText(order('paid', { refundable: true }))).toBeNull();
  });
});

describe('청약철회의 실패', () => {
  it('답을 받지 못하면 다시 보낸다. 엇갈림도 다시 보낸다', () => {
    expect(describeRefundProblem(new NetworkError(new Error('x')))).toMatchObject({ retry: true, refresh: false });
    expect(describeRefundProblem(new ApiError({ status: 409, detail: 'x', code: 'refund.busy' }))).toMatchObject({ retry: true, refresh: true });
  });

  it('409 의 까닭을 알리고 주문을 다시 읽는다', () => {
    const used = describeRefundProblem(new ApiError({ status: 409, detail: 'x', code: 'refund.credits_used' }));
    expect(used).toMatchObject({ retry: false, refresh: true });
    expect(used.message).toContain('썼거나');
    expect(describeRefundProblem(new ApiError({ status: 409, detail: 'x', code: 'refund.refused' })).message).toContain('골드는 그대로');
    expect(describeRefundProblem(new ApiError({ status: 404, detail: 'x' })).message).toBe('그런 주문이 없습니다.');
  });
});
