// web/apps/web/src/pages/orders/OrdersPage.test.tsx
// 주문 내역(A8). 지갑에서 주문 내역으로, 치르지 않은 주문 숨기고 켜기, 더 보기, 한 번 더 묻고 청약철회(지갑도 다시 읽기),
// 환불 처리 중의 다시 확인, 쓴 주문의 409, 원장 줄에서 주문 하나로, 없는 주문을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';

const BILLING = '/api/v1/billing';
const PAID = '00000000-0000-4000-8000-0000000000a1';
const OLD = '00000000-0000-4000-8000-0000000000a2';
const OPENED = '00000000-0000-4000-8000-0000000000a3';

function order(id: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    product_id: 'credits-5000',
    price: 5000,
    credits: '5000',
    status,
    failure_code: null,
    created_at: '2026-10-23T00:00:00Z',
    expires_at: '2026-10-24T00:00:00Z',
    paid_at: status === 'pending' ? null : '2026-10-23T00:01:00Z',
    refundable: false,
    refundable_until: null,
    refunded_at: null,
    refund_blocked: null,
    ...extra,
  };
}

const REFUNDABLE = order(PAID, 'paid', { refundable: true, refundable_until: '2026-10-30T00:01:00Z' });

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => json(200, { paid: '5000', free: '0', total: '5000', next_expiry: null }),
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/orders`]: () => json(200, { orders: [REFUNDABLE, order(OPENED, 'pending')], next_before: null }),
    ...routes,
  });
}

function count(seen: SeenRequest[], method: string, path: string): number {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === `${BILLING}${path}`).length;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('주문 내역', () => {
  it('지갑에서 와서, 결제한 주문만 보이고 치르지 않은 주문은 켜야 보인다', async () => {
    signedIn();
    renderApp('/wallet');

    await userEvent.click(await screen.findByRole('link', { name: '주문 내역' }));
    const list = within(await screen.findByRole('list', { name: '주문' }));
    expect(list.getAllByRole('article')).toHaveLength(1);
    expect(list.getByText('충전됨')).toBeInTheDocument();
    expect(list.getByText(/까지 청약철회할 수 있습니다/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('checkbox', { name: /치르지 않은 주문도 보기/ }));
    expect(list.getAllByRole('article')).toHaveLength(2);
    expect(list.getByText('결제 전')).toBeInTheDocument();
  });

  it('더 보기로 앞의 주문을 읽는다', async () => {
    const { seen } = signedIn({
      [`GET ${BILLING}/orders`]: (request) =>
        request.url.includes('before=')
          ? json(200, { orders: [order(OLD, 'refunded', { refunded_at: '2026-10-22T00:00:00Z' })], next_before: null })
          : json(200, { orders: [REFUNDABLE], next_before: PAID }),
    });
    renderApp('/wallet/orders');

    await userEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    expect(await screen.findByText('환불됨')).toBeInTheDocument();
    expect(seen.some((request) => request.url.includes(`before=${PAID}`))).toBe(true);
  });

  it('청약철회는 한 번 더 묻고, 환불되면 주문과 지갑을 다시 읽는다', async () => {
    let refunded = false;
    const { seen } = signedIn({
      [`GET ${BILLING}/orders`]: () =>
        json(200, { orders: [refunded ? order(PAID, 'refunded', { refunded_at: '2026-10-23T01:00:00Z' }) : REFUNDABLE], next_before: null }),
      [`POST ${BILLING}/orders/${PAID}/refund`]: () => {
        refunded = true;
        return json(200, order(PAID, 'refunded'));
      },
    });
    renderApp('/wallet/orders');

    await userEvent.click(await screen.findByRole('button', { name: '골드 5,000 · 5,000원 청약철회' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText(/5,000원을 돌려받고, 이 주문으로 받은 골드\(5,000\)가 지갑에서 빠집니다/)).toBeInTheDocument();
    const walletReads = count(seen, 'GET', '/wallet');
    await userEvent.click(dialog.getByRole('button', { name: '환불하기' }));

    expect(await screen.findByText('환불됨')).toBeInTheDocument();
    expect(count(seen, 'POST', `/orders/${PAID}/refund`)).toBe(1);
    await vi.waitFor(() => expect(count(seen, 'GET', '/wallet')).toBeGreaterThan(walletReads));
  });

  it('쓴 주문이면 409 의 까닭을 창에 알린다', async () => {
    signedIn({ [`POST ${BILLING}/orders/${PAID}/refund`]: () => json(409, { detail: 'x', code: 'refund.credits_used' }) });
    renderApp('/wallet/orders');

    await userEvent.click(await screen.findByRole('button', { name: /청약철회/ }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '환불하기' }));

    expect(await dialog.findByText(/골드를 썼거나 서술 값으로 묶여 있어/)).toBeInTheDocument();
  });

  it('환불 처리 중이면 다시 확인으로 같은 취소를 다시 보낸다', async () => {
    let refunds = 0;
    signedIn({
      [`GET ${BILLING}/orders`]: () => json(200, { orders: [order(PAID, refunds > 0 ? 'refunded' : 'refunding')], next_before: null }),
      [`POST ${BILLING}/orders/${PAID}/refund`]: () => {
        refunds += 1;
        return json(200, order(PAID, 'refunded'));
      },
    });
    renderApp('/wallet/orders');

    expect(await screen.findByText(/돈이 돌아가는 중입니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '환불 다시 확인' }));

    expect(await screen.findByText('환불됨')).toBeInTheDocument();
    expect(refunds).toBe(1);
  });

  it('원장의 충전 줄에서 그 주문으로 간다. 없는 주문이면 그렇게 알린다', async () => {
    signedIn({
      [`GET ${BILLING}/wallet/entries`]: () =>
        json(200, {
          entries: [
            {
              id: '3',
              operation_id: '00000000-0000-4000-8000-000000000003',
              kind: 'paid',
              reason: 'deposit',
              amount: '5000',
              order_id: PAID,
              hold_id: null,
              hold_status: null,
              created_at: '2026-10-23T00:01:00Z',
            },
          ],
          next_before: null,
        }),
      [`GET ${BILLING}/orders/${PAID}`]: () => json(200, REFUNDABLE),
      [`GET ${BILLING}/orders/${OLD}`]: () => json(404, { detail: 'no' }),
    });
    const view = renderApp('/wallet');

    await userEvent.click(await screen.findByRole('link', { name: '주문 보기' }));
    expect(await screen.findByRole('heading', { name: '주문' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /청약철회/ })).toBeInTheDocument();
    view.unmount();

    renderApp(`/wallet/orders/${OLD}`);
    expect(await screen.findByText('그런 주문이 없습니다.')).toBeInTheDocument();
  });
});
