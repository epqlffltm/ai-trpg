// web/apps/web/src/pages/wallet/AutoChargeHistory.test.tsx
// 지갑(A6)의 최근 자동 결제(#980). 누를 때만 받는 것, 상태와 까닭의 글, 결제된 것의 주문 길, 빈 내역과 읽지 못함을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { AutoChargeHistoryItem } from '../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { historyNote, historyStatusLabel } from './autoChargeHistoryView';

const BILLING = '/api/v1/billing';
const HISTORY = `${BILLING}/auto-charge/history`;
const PAID = '0b6f3c1e-7d2a-4c55-9a51-3c1d2e4f5a61';

function item(overrides: Partial<AutoChargeHistoryItem> = {}): AutoChargeHistoryItem {
  return {
    id: PAID,
    product_id: 'credits-1000',
    price: 1000,
    credits: '1000',
    status: 'paid',
    reason: null,
    turned_off: false,
    created_at: '2026-11-04T01:00:00Z',
    finished_at: '2026-11-04T01:00:05Z',
    ...overrides,
  };
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => json(200, { paid: '80', free: '0', total: '80', next_expiry: null }),
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/products`]: () => json(200, { products: [{ id: 'credits-1000', name: '크레딧 1,000', price: 1000, credits: '1000' }] }),
    [`GET ${BILLING}/auto-charge`]: () =>
      json(200, { settings: null, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } }),
    ...routes,
  });
}

async function section() {
  return within(await screen.findByRole('region', { name: '최근 자동 결제' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('최근 자동 결제', () => {
  it('보기를 누를 때만 받는다. 결제된 것은 그 주문으로 가는 길이 있다', async () => {
    const { seen } = signedIn({ [`GET ${HISTORY}`]: () => json(200, { items: [item()] }) });
    renderApp('/wallet');
    const history = await section();
    await screen.findByRole('region', { name: '자동 충전' });
    expect(seen.some((request) => request.url.endsWith('/auto-charge/history'))).toBe(false);

    await userEvent.click(history.getByRole('button', { name: '보기' }));

    const list = within(await history.findByRole('list', { name: /최근 자동 결제/ }));
    expect(list.getByRole('link', { name: /1,000/ })).toHaveAttribute('href', `/wallet/orders/${PAID}`);
    expect(list.getByText(/결제됨/)).toBeInTheDocument();
    expect(history.getByRole('button', { name: '접기' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('거절, 하지 않음, 처리 중을 까닭과 함께 보이고 주문 길은 붙이지 않는다', async () => {
    signedIn({
      [`GET ${HISTORY}`]: () =>
        json(200, {
          items: [
            item({ id: '1', status: 'processing', finished_at: null }),
            item({ id: '2', status: 'skipped', reason: 'monthly_limit' }),
            item({ id: '3', status: 'declined', turned_off: true }),
          ],
        }),
    });
    renderApp('/wallet');
    const history = await section();

    await userEvent.click(history.getByRole('button', { name: '보기' }));

    const list = within(await history.findByRole('list', { name: /최근 자동 결제/ }));
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(list.queryByRole('link')).toBeNull();
    expect(list.getByText('이번 달 자동 충전 상한에 닿아 결제하지 않았습니다.')).toBeInTheDocument();
    expect(list.getByText(/카드사가 결제를 거절했습니다.*자동 충전을 껐습니다/)).toBeInTheDocument();
    expect(list.getByText(/결과를 기다리거나/)).toBeInTheDocument();
  });

  it('없으면 없다고 하고, 읽지 못하면 다시 시도한다', async () => {
    let fail = true;
    signedIn({ [`GET ${HISTORY}`]: () => (fail ? json(503, { detail: 'x' }) : json(200, { items: [] })) });
    renderApp('/wallet');
    const history = await section();

    await userEvent.click(history.getByRole('button', { name: '보기' }));
    expect(await history.findByText(/결제 서버가 지금 답하지 못합니다/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(history.getByRole('button', { name: '다시 시도' }));

    expect(await history.findByText('아직 자동 결제가 없습니다.')).toBeInTheDocument();
  });
});

describe('최근 자동 결제의 글', () => {
  it('상태마다 이름이 있다', () => {
    expect(historyStatusLabel('processing')).toBe('처리 중');
    expect(historyStatusLabel('paid')).toBe('결제됨');
    expect(historyStatusLabel('declined')).toBe('거절됨');
    expect(historyStatusLabel('skipped')).toBe('하지 않음');
  });

  it('결제된 것에는 덧붙일 말이 없고, 모르는 까닭은 한 말이다', () => {
    expect(historyNote(item())).toBeNull();
    expect(historyNote(item({ status: 'skipped', reason: 'stale' }))).toMatch(/다음에 골드가 떨어지면 다시 삽니다/);
    expect(historyNote(item({ status: 'skipped', reason: 'terms_outdated' }))).toMatch(/동의하고 저장하면 다시 삽니다/);
    expect(historyNote(item({ status: 'skipped', reason: 'something_new' as AutoChargeHistoryItem['reason'] }))).toBe('결제하지 않았습니다.');
    expect(historyNote(item({ status: 'skipped', reason: 'no_card', turned_off: true }))).toBe(
      '등록한 카드가 없어 결제하지 않았습니다. 이어서 실패해 자동 충전을 껐습니다.',
    );
  });
});
