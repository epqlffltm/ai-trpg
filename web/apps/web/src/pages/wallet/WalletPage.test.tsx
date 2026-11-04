// web/apps/web/src/pages/wallet/WalletPage.test.tsx
// 지갑(A6). 머리의 잔액에서 지갑으로 가기, 잔액과 곧 사라질 실버, 원장(정리 줄은 숨김, 더 보기), 빈 원장, 503,
// 테이블 방에서 서술 값이 움직이는 일이 오면 잔액을 다시 읽는 것, 쿠폰 넣기(#979)를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { event, ME, member, round, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../test/tableFixtures';

const WALLET = '/api/v1/billing/wallet';
const ENTRIES = '/api/v1/billing/wallet/entries';
const COUPONS = '/api/v1/billing/coupons/redeem';
const BALANCE = { paid: '80', free: '10', total: '90', next_expiry: { amount: '10', expires_at: '2099-01-01T00:00:00Z' } };

function line(id: string, reason: string, amount: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    operation_id: '00000000-0000-4000-8000-000000000001',
    kind: 'free',
    reason,
    amount,
    order_id: null,
    hold_id: null,
    hold_status: null,
    source: null,
    created_at: '2026-10-22T00:00:00Z',
    ...extra,
  };
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${WALLET}`]: () => json(200, BALANCE),
    [`GET ${ENTRIES}`]: () => json(200, { entries: [], next_before: null }),
    'GET /api/v1/billing/auto-charge': () => json(200, { settings: null, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } }),
    'GET /api/v1/billing/products': () => json(200, { products: [] }),
    ...routes,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('지갑', () => {
  it('머리의 잔액을 누르면 지갑으로 간다. 골드, 실버, 합과 곧 사라질 실버를 보인다', async () => {
    signedIn();
    renderApp('/');

    await userEvent.click(await screen.findByRole('link', { name: '지갑: 골드 80 · 실버 10' }));

    const balance = within(await screen.findByRole('region', { name: '잔액' }));
    expect(await balance.findByText('80')).toBeInTheDocument();
    expect(balance.getByText('90')).toBeInTheDocument();
    expect(balance.getByText(/곧 사라질 실버 10/)).toBeInTheDocument();
    expect(await screen.findByText('아직 내역이 없습니다.')).toBeInTheDocument();
  });

  it('원장은 최근 것부터, 정리 줄은 숨기고, 더 보기로 앞의 쪽을 읽는다', async () => {
    const { seen } = signedIn({
      [`GET ${ENTRIES}`]: (request) =>
        request.url.includes('before=')
          ? json(200, { entries: [line('7', 'deposit', '80', { kind: 'paid' })], next_before: null })
          : json(200, {
              entries: [line('9', 'hold', '-3', { hold_status: 'captured' }), line('8', 'regroup', '0')],
              next_before: '8',
            }),
    });
    renderApp('/wallet');

    const ledger = within(await screen.findByRole('list', { name: /내역/ }));
    expect(ledger.getByText('서술 값 사용')).toBeInTheDocument();
    expect(ledger.getByText('-3')).toBeInTheDocument();
    expect(ledger.queryByText('정리')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '더 보기' }));

    expect(await ledger.findByText('충전')).toBeInTheDocument();
    expect(ledger.getByText('+80')).toBeInTheDocument();
    expect(seen.some((request) => request.url.includes('before=8'))).toBe(true);
    expect(screen.queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument();
  });

  it('결제 서버가 503 이면 다시 시도하게 하고 로그아웃시키지 않는다. 머리에는 잔액을 두지 않는다', async () => {
    signedIn({ [`GET ${WALLET}`]: () => json(503, { detail: 'busy' }, { 'Retry-After': '3' }) });
    renderApp('/wallet');

    expect(await screen.findByText(/결제 서버가 지금 답하지 못합니다. 3초 뒤에/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '모험가' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /지갑:/ })).not.toBeInTheDocument();
  });

  it('테이블 방에서 다음 라운드가 열리면 잔액을 다시 읽는다', async () => {
    let reads = 0;
    const TABLE_ID = '00000000-0000-4000-8000-0000000000d9';
    const BASE = `/api/v1/game/tables/${TABLE_ID}`;
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
      [`GET ${WALLET}`]: () => {
        reads += 1;
        return json(200, reads === 1 ? BALANCE : { ...BALANCE, free: '7', total: '87' });
      },
      ...roomRoutes(TABLE_ID, {
        [`GET ${BASE}`]: () =>
          json(200, tableDetail(TABLE_ID, { status: 'playing', members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() })] })),
        [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
        [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('table_event', event(4, 'round_opened', { number: 2 }), '4-0-0')]),
      }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('link', { name: '지갑: 골드 80 · 실버 7' }, { timeout: 3000 })).toBeInTheDocument();
  });
});

describe('쿠폰', () => {
  async function enter(code: string) {
    await userEvent.type(await screen.findByRole('textbox', { name: '쿠폰 코드' }), code);
    await userEvent.click(screen.getByRole('button', { name: '받기' }));
  }

  it('코드를 넣으면 받은 실버와 사라지는 때를 보이고, 잔액과 원장을 다시 읽는다', async () => {
    let redeemed = false;
    const { seen } = signedIn({
      [`GET ${WALLET}`]: () => json(200, redeemed ? { ...BALANCE, free: '510', total: '590' } : BALANCE),
      [`GET ${ENTRIES}`]: () =>
        json(200, { entries: redeemed ? [line('3', 'grant', '500', { source: 'coupon' })] : [], next_before: null }),
      [`POST ${COUPONS}`]: () => {
        redeemed = true;
        return json(201, { code: 'LAUNCH-2026', silver: '500', expires_at: '2026-12-01T00:00:00Z' });
      },
    });
    renderApp('/wallet');

    await enter(' launch-2026 ');

    expect(await screen.findByText(/쿠폰 LAUNCH-2026: 실버 500을 받았습니다/)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: '지갑: 골드 80 · 실버 510' })).toBeInTheDocument();
    expect(within(await screen.findByRole('list', { name: /내역/ })).getByText('쿠폰')).toBeInTheDocument();
    expect(seen.find((request) => request.method === 'POST' && request.url.includes(COUPONS))?.body).toEqual({ code: ' launch-2026 ' });
    expect(screen.getByRole('textbox', { name: '쿠폰 코드' })).toHaveValue('');
  });

  it('없는 코드와 이미 받은 코드는 그 까닭을 보인다', async () => {
    let calls = 0;
    signedIn({
      [`POST ${COUPONS}`]: () => {
        calls += 1;
        return calls === 1
          ? json(404, { detail: 'x', code: 'coupon.not_found' })
          : json(409, { detail: 'x', code: 'coupon.already_redeemed' });
      },
    });
    renderApp('/wallet');

    await enter('NOPE');
    expect(await screen.findByText('그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요.')).toBeInTheDocument();
    await enter('X');
    expect(await screen.findByText('이미 받은 쿠폰입니다.')).toBeInTheDocument();
    expect(screen.queryByText('그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요.')).not.toBeInTheDocument();
  });

  it('틀린 뒤에 받으면 앞의 까닭을 지운다', async () => {
    let calls = 0;
    signedIn({
      [`POST ${COUPONS}`]: () => {
        calls += 1;
        return calls === 1
          ? json(404, { detail: 'x', code: 'coupon.not_found' })
          : json(201, { code: 'LAUNCH', silver: '100', expires_at: '2026-12-01T00:00:00Z' });
      },
    });
    renderApp('/wallet');

    await enter('NOPE');
    expect(await screen.findByText('그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요.')).toBeInTheDocument();
    await userEvent.clear(screen.getByRole('textbox', { name: '쿠폰 코드' }));
    await enter('LAUNCH');

    expect(await screen.findByText(/쿠폰 LAUNCH: 실버 100을 받았습니다/)).toBeInTheDocument();
    expect(screen.queryByText('그런 쿠폰이 없습니다. 코드를 다시 확인해 주세요.')).not.toBeInTheDocument();
  });

  it('본인인증 전이면 본인인증으로 가는 길을 보인다', async () => {
    signedIn({ [`POST ${COUPONS}`]: () => json(403, { detail: 'x', code: 'coupon.verification_required' }) });
    renderApp('/wallet');

    await enter('LAUNCH');

    expect(await screen.findByText(/본인인증을 마친 계정만 쿠폰을 받습니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '본인인증하기' })).toHaveAttribute('href', '/me/identity');
  });

  it('너무 자주 틀리면 몇 분 뒤에 다시 넣으라고 한다', async () => {
    signedIn({
      [`POST ${COUPONS}`]: () => json(429, { detail: 'x', code: 'coupon.too_many_attempts' }, { 'Retry-After': '61' }),
    });
    renderApp('/wallet');

    await enter('LAUNCH');

    expect(await screen.findByText('코드를 너무 자주 틀렸습니다. 2분 뒤에 다시 넣어 주세요.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '본인인증하기' })).not.toBeInTheDocument();
  });

  it('코드가 비었으면 보내지 않는다', async () => {
    const { seen } = signedIn();
    renderApp('/wallet');

    await userEvent.type(await screen.findByRole('textbox', { name: '쿠폰 코드' }), '   ');

    expect(screen.getByRole('button', { name: '받기' })).toBeDisabled();
    expect(seen.some((request) => request.url.includes(COUPONS))).toBe(false);
  });
});
