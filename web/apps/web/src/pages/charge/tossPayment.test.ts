// web/apps/web/src/pages/charge/tossPayment.test.ts
// 토스페이먼츠의 결제창에 넘기는 것과 돌아온 주소를 읽는 것. 순수한 함수다(SDK 는 부르지 않는다).

import { describe, expect, it } from 'vitest';
import type { Order } from '../../api/types';
import { CHARGE_RETURN_PATH, chargeRequest, closedByUser, readChargeReturn, returnFailureText } from './tossPayment';

const ORDER_ID = '00000000-0000-4000-8000-0000000000c1';

const ORDER = {
  id: ORDER_ID,
  product_id: 'credits-5000',
  price: 5000,
  credits: '5000',
  status: 'pending',
  failure_code: null,
  created_at: '2026-11-04T00:00:00Z',
  expires_at: '2026-11-05T00:00:00Z',
  paid_at: null,
  refundable: false,
  refundable_until: null,
  refunded_at: null,
  refund_blocked: null,
} as Order;

describe('결제창에 넘기는 것', () => {
  it('카드, 원화, 서버의 주문 번호와 값, 같은 화면으로 돌아오기, 현재 창', () => {
    expect(chargeRequest(ORDER, 'https://trpg.example')).toEqual({
      method: 'CARD',
      amount: { currency: 'KRW', value: 5000 },
      orderId: ORDER_ID,
      orderName: '골드 5,000',
      successUrl: `https://trpg.example${CHARGE_RETURN_PATH}`,
      failUrl: `https://trpg.example${CHARGE_RETURN_PATH}`,
      windowTarget: 'self',
    });
  });

  it('사용자가 닫은 것은 오류로 보이지 않는다', () => {
    expect(closedByUser({ code: 'USER_CANCEL' })).toBe(true);
    expect(closedByUser({ code: 'PAY_PROCESS_CANCELED' })).toBe(true);
    expect(closedByUser({ code: 'INVALID_PARAMETERS' })).toBe(false);
    expect(closedByUser(new Error('network'))).toBe(false);
    expect(closedByUser(null)).toBe(false);
  });
});

describe('돌아온 주소', () => {
  const read = (query: string) => readChargeReturn(new URLSearchParams(query));

  it('성공이면 주문 번호와 결제 번호를 읽는다', () => {
    expect(read(`paymentType=NORMAL&orderId=${ORDER_ID}&paymentKey=tviva20261104abc&amount=5000`)).toEqual({
      kind: 'paid',
      orderId: ORDER_ID,
      paymentKey: 'tviva20261104abc',
    });
  });

  it('모양이 틀리면 읽지 않는다', () => {
    expect(read(`paymentKey=tviva&amount=5000`).kind).toBe('unreadable');
    expect(read(`orderId=order-1&paymentKey=tviva`).kind).toBe('unreadable');
    expect(read(`orderId=${ORDER_ID}&paymentKey=${encodeURIComponent('tviva/../x')}`).kind).toBe('unreadable');
    expect(read(`orderId=${ORDER_ID}&paymentKey=${'a'.repeat(201)}`).kind).toBe('unreadable');
    expect(read('').kind).toBe('unreadable');
  });

  it('실패면 코드만 읽는다. 글(message)은 쓰지 않는다', () => {
    expect(read(`code=PAY_PROCESS_CANCELED&message=${encodeURIComponent('아무 글')}&orderId=${ORDER_ID}`)).toEqual({
      kind: 'failed',
      code: 'PAY_PROCESS_CANCELED',
    });
    expect(read(`code=${encodeURIComponent('<b>x</b>')}`)).toEqual({ kind: 'failed', code: null });
  });

  it('실패의 글은 화면의 말이다', () => {
    expect(returnFailureText('PAY_PROCESS_CANCELED')).toMatch(/그만두었습니다/);
    expect(returnFailureText('REJECT_CARD_COMPANY')).toMatch(/카드사가/);
    expect(returnFailureText('SOMETHING_NEW')).toMatch(/결제하지 못했습니다/);
    expect(returnFailureText(null)).toMatch(/결제하지 못했습니다/);
  });
});
