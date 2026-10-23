// web/apps/web/src/pages/charge/chargePure.test.ts
// 충전(A7)의 순수한 함수. 값과 골드의 글, 결과의 글, 거절 사유, 주문의 열쇠, 실패의 할 일, 결제창의 갈래와 가짜 결제 번호를 본다.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import type { Order } from '../../api/types';
import { describeChargeProblem } from './chargeProblem';
import { failureText, goldLabel, isSettled, orderKey, productLabel, resultText, wonLabel } from './chargeView';
import { fakePaymentKey, gatewayKind } from './paymentGateway';

function order(extra: Partial<Order> = {}): Order {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    product_id: 'credits-1000',
    price: 1000,
    credits: '1000',
    status: 'pending',
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

describe('글', () => {
  it('값은 원, 크레딧은 골드로 쉼표를 넣어 적는다', () => {
    expect(wonLabel(30000)).toBe('30,000원');
    expect(goldLabel('30000')).toBe('골드 30,000');
    expect(goldLabel('12.5')).toBe('골드 12.5');
    expect(productLabel({ id: 'credits-5000', name: '5천', price: 5000, credits: '5000' })).toBe('5,000원 · 골드 5,000');
  });

  it('결과는 상태마다, 실패는 돈이 나가지 않았다고, 모름은 실패가 아니라고 적는다', () => {
    expect(resultText(order({ status: 'paid' }))).toBe('충전을 마쳤습니다: 골드 1,000');
    expect(resultText(order({ status: 'failed', failure_code: 'card_declined' }))).toBe('카드사가 결제를 거절했습니다. 돈은 나가지 않았습니다.');
    expect(resultText(order({ status: 'confirming' }))).toContain('실패한 것이 아닙니다');
    expect(failureText('SOMETHING_NEW')).toBe('결제가 이루어지지 않았습니다.');
    expect(isSettled('confirming')).toBe(false);
    expect(isSettled('paid')).toBe(true);
  });
});

describe('주문의 열쇠', () => {
  it('같은 상품을 다시 보낼 때만 앞의 열쇠를 쓴다', () => {
    const fresh = () => 'new-key';
    expect(orderKey(null, 'credits-1000', fresh)).toBe('new-key');
    expect(orderKey({ productId: 'credits-1000', key: 'old-key' }, 'credits-1000', fresh)).toBe('old-key');
    expect(orderKey({ productId: 'credits-1000', key: 'old-key' }, 'credits-5000', fresh)).toBe('new-key');
  });
});

describe('실패의 할 일', () => {
  it('답을 받지 못했거나 503 이면 같은 것을 다시 보낸다. 결제가 실패한 것이 아니다', () => {
    expect(describeChargeProblem(new NetworkError(new Error('x')), 'order')).toMatchObject({ retry: true, restart: false });
    const busy = describeChargeProblem(new ApiError({ status: 503, detail: 'x' }), 'confirm');
    expect(busy).toMatchObject({ retry: true });
    expect(busy.message).toContain('실패한 것이 아닙니다');
  });

  it('본인인증, 보호자 동의, 409 는 처음부터 다시', () => {
    const verify = describeChargeProblem(new ApiError({ status: 403, detail: 'x', code: 'payment.verification_required' }), 'order');
    expect(verify).toMatchObject({ retry: false, restart: true });
    expect(verify.message).toContain('본인인증');
    expect(describeChargeProblem(new ApiError({ status: 403, detail: 'x', code: 'payment.guardian_consent_required' }), 'confirm').message).toContain('보호자');
    expect(describeChargeProblem(new ApiError({ status: 409, detail: 'x' }), 'confirm')).toMatchObject({ retry: false, restart: true });
  });
});

describe('결제창', () => {
  it('빌드 설정이 없거나 fake 면 가짜, 모르는 값이면 띄우지 않는다', () => {
    expect(gatewayKind(undefined)).toBe('fake');
    expect(gatewayKind('fake')).toBe('fake');
    expect(gatewayKind('toss')).toBe('none');
  });

  it('가짜 결제 번호는 앞머리에 서버가 받는 글자만 붙인다', () => {
    expect(fakePaymentKey('fake_ok_', 'ab12-cd34!')).toBe('fake_ok_ab12-cd34');
  });
});
