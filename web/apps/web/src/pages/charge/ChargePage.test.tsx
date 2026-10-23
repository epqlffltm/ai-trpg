// web/apps/web/src/pages/charge/ChargePage.test.tsx
// 충전(A7). 지갑에서 충전으로, 상품을 고르면 주문(Idempotency-Key), 시험용 결제창의 결과로 승인 요청,
// 승인되면 지갑을 다시 읽기, 거절, 결과를 모름(다시 확인은 같은 결제 번호), 503 은 같은 열쇠로 다시 보내기, 본인인증 전의 403 을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';

const BILLING = '/api/v1/billing';
const ORDER_ID = '00000000-0000-4000-8000-0000000000c1';
const PRODUCTS = [
  { id: 'credits-1000', name: '1천', price: 1000, credits: '1000' },
  { id: 'credits-5000', name: '5천', price: 5000, credits: '5000' },
];

function order(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: ORDER_ID,
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

type Routes = Record<string, (request: SeenRequest) => Response>;

/** 승인 요청의 답을 결제 번호의 앞머리로 정한다(결제 서버의 가짜 결제 대행사처럼) */
function confirmLikeFake(request: SeenRequest): Response {
  const key = (request.body as { payment_key: string }).payment_key;
  if (key.startsWith('fake_ok_')) return json(200, order('paid', { paid_at: '2026-10-23T00:01:00Z' }));
  if (key.startsWith('fake_declined_')) return json(200, order('failed', { failure_code: 'card_declined' }));
  return json(202, order('confirming'));
}

function signedIn(routes: Routes = {}) {
  let wallet = 0;
  const fake = installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => {
      wallet += 1;
      return json(200, { paid: wallet === 1 ? '0' : '1000', free: '0', total: wallet === 1 ? '0' : '1000', next_expiry: null });
    },
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/products`]: () => json(200, { products: PRODUCTS }),
    [`POST ${BILLING}/orders`]: () => json(201, order('pending')),
    [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: confirmLikeFake,
    ...routes,
  });
  return fake;
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === `${BILLING}${path}`);
}

async function chooseThousand() {
  await userEvent.click(await screen.findByRole('button', { name: /골드 1,000/ }));
  return within(await screen.findByRole('region', { name: '시험용 결제창' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('충전', () => {
  it('지갑에서 충전으로 가서, 상품을 고르면 열쇠를 붙여 주문하고, 결제 성공이면 골드를 받고 잔액을 다시 읽는다', async () => {
    const { seen } = signedIn();
    renderApp('/wallet');

    await userEvent.click(await screen.findByRole('link', { name: '충전하기' }));
    const checkout = await chooseThousand();
    const created = sent(seen, 'POST', '/orders')[0];
    expect(created?.body).toEqual({ product_id: 'credits-1000' });
    expect(created?.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);

    await userEvent.click(checkout.getByRole('button', { name: '결제 성공' }));

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    expect((sent(seen, 'POST', `/orders/${ORDER_ID}/confirm`)[0]?.body as { payment_key: string }).payment_key).toMatch(/^fake_ok_/);
    expect(await screen.findByRole('link', { name: '지갑: 골드 1000 · 실버 0' })).toBeInTheDocument();
  });

  it('거절되면 이유와 돈이 나가지 않았음을 알리고 처음부터 다시 고르게 한다', async () => {
    signedIn();
    renderApp('/wallet/charge');

    await userEvent.click((await chooseThousand()).getByRole('button', { name: '카드 거절' }));

    expect(await screen.findByText('카드사가 결제를 거절했습니다. 돈은 나가지 않았습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '처음부터 다시' }));
    expect(await screen.findByRole('list', { name: '충전할 상품' })).toBeInTheDocument();
  });

  it('결과를 모르면 실패로 보이지 않고, 다시 확인은 같은 결제 번호로 보낸다', async () => {
    let confirms = 0;
    const { seen } = signedIn({
      [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: () => {
        confirms += 1;
        return confirms === 1 ? json(202, order('confirming')) : json(200, order('paid'));
      },
    });
    renderApp('/wallet/charge');

    await userEvent.click((await chooseThousand()).getByRole('button', { name: '답이 오지 않음' }));
    expect(await screen.findByText(/실패한 것이 아닙니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 확인' }));

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    const keys = sent(seen, 'POST', `/orders/${ORDER_ID}/confirm`).map((request) => (request.body as { payment_key: string }).payment_key);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('주문의 답을 받지 못하면 같은 열쇠로 다시 보낸다. 다른 상품을 고르면 새 열쇠다', async () => {
    let orders = 0;
    const { seen } = signedIn({
      [`POST ${BILLING}/orders`]: () => {
        orders += 1;
        return orders === 1 ? json(503, { detail: 'busy' }) : json(201, order('pending'));
      },
    });
    renderApp('/wallet/charge');

    await userEvent.click(await screen.findByRole('button', { name: /골드 1,000/ }));
    expect(await screen.findByText(/다시 보내도 주문은 하나만 생깁니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 보내기' }));

    expect(await screen.findByRole('region', { name: '시험용 결제창' })).toBeInTheDocument();
    const keys = sent(seen, 'POST', '/orders').map((request) => request.headers.get('Idempotency-Key'));
    expect(keys[0]).toBe(keys[1]);
  });

  it('승인의 답을 받지 못하면 결제창을 막고, 같은 결제 번호로만 다시 보낸다', async () => {
    let confirms = 0;
    const { seen } = signedIn({
      [`POST ${BILLING}/orders/${ORDER_ID}/confirm`]: () => {
        confirms += 1;
        return confirms === 1 ? json(503, { detail: 'busy' }) : json(200, order('paid'));
      },
    });
    renderApp('/wallet/charge');

    const checkout = await chooseThousand();
    await userEvent.click(checkout.getByRole('button', { name: '결제 성공' }));
    expect(await screen.findByText(/결제가 실패한 것이 아닙니다/)).toBeInTheDocument();
    expect(checkout.getByRole('button', { name: '카드 거절' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '다시 보내기' }));

    expect(await screen.findByText('충전을 마쳤습니다: 골드 1,000')).toBeInTheDocument();
    const keys = sent(seen, 'POST', `/orders/${ORDER_ID}/confirm`).map((request) => (request.body as { payment_key: string }).payment_key);
    expect(keys[0]).toBe(keys[1]);
  });

  it('본인인증 전이면 403 을 알리고 상품 고르기로 돌아간다', async () => {
    signedIn({ [`POST ${BILLING}/orders`]: () => json(403, { detail: 'x', code: 'payment.verification_required' }) });
    renderApp('/wallet/charge');

    await userEvent.click(await screen.findByRole('button', { name: /골드 1,000/ }));

    expect(await screen.findByText(/본인인증을 마친 계정만 충전할 수 있습니다/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다시 보내기' })).not.toBeInTheDocument();
    expect(screen.getByRole('list', { name: '충전할 상품' })).toBeInTheDocument();
  });
});
