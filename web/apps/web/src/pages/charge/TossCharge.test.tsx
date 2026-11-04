// web/apps/web/src/pages/charge/TossCharge.test.tsx
// 충전(A7)의 토스페이먼츠 결제창(VITE_PAYMENT_GATEWAY=toss). SDK 는 가짜로 바꾼다(실제 결제창은 띄우지 않는다).
// 결제창에 넘기는 것, 열지 못했을 때와 사용자가 닫았을 때, 돌아오는 화면의 승인(한 번만, 결과를 모르면 같은 결제 번호로 다시)과 실패를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';

const sdk = vi.hoisted(() => ({
  loadTossPayments: vi.fn(),
  requestPayment: vi.fn(),
  payment: vi.fn(),
}));

vi.mock('@tosspayments/tosspayments-sdk', () => ({
  ANONYMOUS: '@@ANONYMOUS',
  loadTossPayments: sdk.loadTossPayments,
}));

const BILLING = '/api/v1/billing';
const ORDER_ID = '00000000-0000-4000-8000-0000000000c1';
const CLIENT_KEY = 'test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq';
const PRODUCTS = [{ id: 'credits-1000', name: '1천', price: 1000, credits: '1000' }];

function order(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: ORDER_ID,
    product_id: 'credits-1000',
    price: 1000,
    credits: '1000',
    status,
    failure_code: null,
    created_at: '2026-11-04T00:00:00Z',
    expires_at: '2026-11-05T00:00:00Z',
    paid_at: null,
    refundable: false,
    refundable_until: null,
    refunded_at: null,
    refund_blocked: null,
    ...extra,
  };
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  let wallet = 0;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    // 처음에는 0, 다시 읽으면 1000 이다. 승인된 뒤 지갑을 다시 읽는지 머리말의 잔액으로 본다
    [`GET ${BILLING}/wallet`]: () => {
      wallet += 1;
      return json(200, { paid: wallet === 1 ? '0' : '1000', free: '0', total: wallet === 1 ? '0' : '1000', next_expiry: null });
    },
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/products`]: () => json(200, { products: PRODUCTS }),
    [`POST ${BILLING}/orders`]: () => json(201, order('pending')),
    [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: () => json(200, order('paid', { paid_at: '2026-11-04T00:01:00Z' })),
    ...routes,
  });
}

function confirms(seen: SeenRequest[]): string[] {
  return seen
    .filter((request) => request.method === 'POST' && request.url === `${BILLING}/orders/${ORDER_ID}/confirm`)
    .map((request) => (request.body as { payment_key: string }).payment_key);
}

beforeEach(() => {
  vi.stubEnv('VITE_PAYMENT_GATEWAY', 'toss');
  vi.stubEnv('VITE_TOSS_CLIENT_KEY', CLIENT_KEY);
  sdk.requestPayment.mockReset().mockResolvedValue(undefined);
  sdk.payment.mockReset().mockReturnValue({ requestPayment: sdk.requestPayment });
  sdk.loadTossPayments.mockReset().mockResolvedValue({ payment: sdk.payment });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

async function openCheckout() {
  renderApp('/wallet/charge');
  await userEvent.click(await screen.findByRole('button', { name: /골드 1,000/ }));
  return within(await screen.findByRole('region', { name: '결제' }));
}

describe('토스페이먼츠의 결제창', () => {
  it('주문을 만들고 결제창을 현재 창에서 연다. 승인은 아직 보내지 않는다', async () => {
    const { seen } = signedIn();
    const checkout = await openCheckout();

    await userEvent.click(checkout.getByRole('button', { name: '결제하기' }));

    expect(sdk.loadTossPayments).toHaveBeenCalledWith(CLIENT_KEY);
    expect(sdk.payment).toHaveBeenCalledWith({ customerKey: '@@ANONYMOUS' });
    expect(sdk.requestPayment).toHaveBeenCalledWith({
      method: 'CARD',
      amount: { currency: 'KRW', value: 1000 },
      orderId: ORDER_ID,
      orderName: '골드 1,000',
      successUrl: `${window.location.origin}/wallet/charge/return`,
      failUrl: `${window.location.origin}/wallet/charge/return`,
      windowTarget: 'self',
    });
    expect(confirms(seen)).toHaveLength(0);
  });

  it('열지 못하면 까닭을 보이고 다시 누를 수 있다. 사용자가 닫았으면 아무것도 보이지 않는다', async () => {
    signedIn();
    sdk.requestPayment.mockRejectedValueOnce({ code: 'USER_CANCEL' }).mockRejectedValueOnce(new Error('script blocked'));
    const checkout = await openCheckout();

    await userEvent.click(checkout.getByRole('button', { name: '결제하기' }));
    expect(checkout.queryByText(/결제창을 열지 못했습니다/)).not.toBeInTheDocument();
    await userEvent.click(checkout.getByRole('button', { name: '결제하기' }));

    expect(await checkout.findByText(/결제창을 열지 못했습니다/)).toBeInTheDocument();
    expect(checkout.getByRole('button', { name: '결제하기' })).toBeEnabled();
  });

  it('키가 없으면 결제창을 띄우지 않는다', async () => {
    vi.stubEnv('VITE_TOSS_CLIENT_KEY', '');
    signedIn();
    renderApp('/wallet/charge');

    await userEvent.click(await screen.findByRole('button', { name: /골드 1,000/ }));

    expect(await screen.findByText('결제창을 준비 중입니다.')).toBeInTheDocument();
    expect(sdk.loadTossPayments).not.toHaveBeenCalled();
  });
});

describe('결제창이 돌아오는 화면', () => {
  it('성공으로 돌아오면 그 결제 번호로 승인을 한 번 요청하고 결과를 보인다', async () => {
    const { seen } = signedIn();
    renderApp(`/wallet/charge/return?paymentType=NORMAL&orderId=${ORDER_ID}&paymentKey=tviva20261104&amount=1000`);

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    expect(confirms(seen)).toEqual(['tviva20261104']);
    expect(screen.getByRole('link', { name: '지갑 보기' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: '지갑: 골드 1000 · 실버 0' })).toBeInTheDocument();
  });

  it('결과를 모르면 다시 확인은 같은 결제 번호로 보낸다', async () => {
    let calls = 0;
    const { seen } = signedIn({
      [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: () => {
        calls += 1;
        return calls === 1 ? json(202, order('confirming')) : json(200, order('paid'));
      },
    });
    renderApp(`/wallet/charge/return?orderId=${ORDER_ID}&paymentKey=tviva20261104&amount=1000`);

    await userEvent.click(await screen.findByRole('button', { name: '다시 확인' }));

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    expect(confirms(seen)).toEqual(['tviva20261104', 'tviva20261104']);
  });

  it('승인의 답을 받지 못하면 같은 결제 번호로 다시 보낸다', async () => {
    let calls = 0;
    const { seen } = signedIn({
      [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: () => {
        calls += 1;
        return calls === 1 ? json(503, { detail: 'busy' }) : json(200, order('paid'));
      },
    });
    renderApp(`/wallet/charge/return?orderId=${ORDER_ID}&paymentKey=tviva20261104&amount=1000`);

    await userEvent.click(await screen.findByRole('button', { name: '다시 보내기' }));

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    expect(confirms(seen)).toEqual(['tviva20261104', 'tviva20261104']);
  });

  it('실패로 돌아오면 까닭을 보이고 승인을 보내지 않는다. 주소의 글은 쓰지 않는다', async () => {
    const { seen } = signedIn();
    renderApp(`/wallet/charge/return?code=PAY_PROCESS_CANCELED&message=${encodeURIComponent('여기로 송금하세요')}&orderId=${ORDER_ID}`);

    expect(await screen.findByText('결제를 그만두었습니다. 돈은 나가지 않았습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/송금/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '충전으로' })).toHaveAttribute('href', '/wallet/charge');
    expect(confirms(seen)).toHaveLength(0);
  });

  it('주소를 읽지 못하면 서버에 보내지 않는다', async () => {
    const { seen } = signedIn();
    renderApp(`/wallet/charge/return?orderId=order-1&paymentKey=tviva`);

    expect(await screen.findByText(/결제창의 결과를 읽지 못했습니다/)).toBeInTheDocument();
    expect(confirms(seen)).toHaveLength(0);
  });
});
