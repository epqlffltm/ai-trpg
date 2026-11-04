// web/apps/web/src/pages/wallet/TossCardWindow.test.tsx
// 자동 충전(#980)의 토스페이먼츠 카드 등록 창(VITE_PAYMENT_GATEWAY=toss). SDK 는 가짜로 바꾼다(실제 창은 띄우지 않는다).
// 고객 키를 받아 창을 여는 것, 닫음과 열지 못함, 돌아오는 화면의 등록(한 번만)과 실패를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';

const sdk = vi.hoisted(() => ({
  loadTossPayments: vi.fn(),
  requestBillingAuth: vi.fn(),
  payment: vi.fn(),
}));

vi.mock('@tosspayments/tosspayments-sdk', () => ({
  ANONYMOUS: '@@ANONYMOUS',
  loadTossPayments: sdk.loadTossPayments,
}));

const BILLING = '/api/v1/billing';
const CLIENT_KEY = 'test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq';
const CUSTOMER_KEY = '6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11';
const CARD = { issuer_code: '61', number: '43301234****123*', registered_at: '2026-11-04T01:00:00Z' };
const NOTHING = { settings: null, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } };

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => json(200, { paid: '80', free: '0', total: '80', next_expiry: null }),
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/products`]: () => json(200, { products: [] }),
    [`GET ${BILLING}/auto-charge`]: () => json(200, NOTHING),
    [`POST ${BILLING}/cards/customer-key`]: () => json(200, { customer_key: CUSTOMER_KEY }),
    [`POST ${BILLING}/cards`]: () => json(201, CARD),
    ...routes,
  });
}

function registrations(seen: SeenRequest[]) {
  return seen.filter((request) => request.method === 'POST' && request.url === `${BILLING}/cards`).map((request) => request.body);
}

beforeEach(() => {
  vi.stubEnv('VITE_PAYMENT_GATEWAY', 'toss');
  vi.stubEnv('VITE_TOSS_CLIENT_KEY', CLIENT_KEY);
  sdk.requestBillingAuth.mockReset().mockResolvedValue(undefined);
  sdk.payment.mockReset().mockReturnValue({ requestBillingAuth: sdk.requestBillingAuth });
  sdk.loadTossPayments.mockReset().mockResolvedValue({ payment: sdk.payment });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

async function section() {
  return within(await screen.findByRole('region', { name: '자동 충전' }));
}

describe('토스페이먼츠의 카드 등록 창', () => {
  it('고객 키를 받아 그 키로 창을 현재 창에서 연다. 등록은 아직 보내지 않는다', async () => {
    const { seen } = signedIn();
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('button', { name: '카드 등록' }));

    expect(sdk.loadTossPayments).toHaveBeenCalledWith(CLIENT_KEY);
    expect(sdk.payment).toHaveBeenCalledWith({ customerKey: CUSTOMER_KEY });
    expect(sdk.requestBillingAuth).toHaveBeenCalledWith({
      method: 'CARD',
      successUrl: `${window.location.origin}/wallet/card/return`,
      failUrl: `${window.location.origin}/wallet/card/return`,
      windowTarget: 'self',
    });
    expect(registrations(seen)).toHaveLength(0);
    // 시험용 등록 창은 없다
    expect(auto.queryByRole('region', { name: '시험용 카드 등록 창' })).not.toBeInTheDocument();
  });

  it('닫으면 아무것도 보이지 않고, 열지 못하면 까닭을 보인다', async () => {
    signedIn();
    sdk.requestBillingAuth.mockRejectedValueOnce({ code: 'USER_CANCEL' }).mockRejectedValueOnce(new Error('script blocked'));
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('button', { name: '카드 등록' }));
    expect(auto.queryByText(/열지 못했습니다/)).not.toBeInTheDocument();
    await userEvent.click(auto.getByRole('button', { name: '카드 등록' }));

    expect(await auto.findByText('카드 등록 창을 열지 못했습니다. 잠시 뒤에 다시 시도하세요.')).toBeInTheDocument();
  });

  it('고객 키를 받지 못하면 서버의 까닭을 보이고 창을 열지 않는다', async () => {
    signedIn({ [`POST ${BILLING}/cards/customer-key`]: () => json(503, { detail: 'busy' }) });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('button', { name: '카드 등록' }));

    expect(await auto.findByText(/결제 서버가 지금 답하지 못합니다/)).toBeInTheDocument();
    expect(sdk.loadTossPayments).not.toHaveBeenCalled();
  });
});

describe('카드 등록 창이 돌아오는 화면', () => {
  it('성공으로 돌아오면 인증 키와 고객 키로 한 번 등록하고 결과를 보인다', async () => {
    const { seen } = signedIn();
    renderApp(`/wallet/card/return?customerKey=${CUSTOMER_KEY}&authKey=bln_a1B2c3`);

    expect(await screen.findByText(/카드를 등록했습니다: 43301234\*\*\*\*123\*/)).toBeInTheDocument();
    expect(registrations(seen)).toEqual([{ auth_key: 'bln_a1B2c3', customer_key: CUSTOMER_KEY }]);
    expect(screen.getByRole('link', { name: '지갑으로' })).toHaveAttribute('href', '/wallet');
  });

  it('등록이 거절되면 서버의 까닭을 보이고 다시 보내지 않는다', async () => {
    const { seen } = signedIn({ [`POST ${BILLING}/cards`]: () => json(409, { detail: 'x', code: 'card.customer_key_mismatch' }) });
    renderApp(`/wallet/card/return?customerKey=${CUSTOMER_KEY}&authKey=bln_a1B2c3`);

    expect(await screen.findByText('카드 등록을 처음부터 다시 해 주세요.')).toBeInTheDocument();
    expect(registrations(seen)).toHaveLength(1);
  });

  it('실패로 돌아오면 까닭을 보이고 등록을 보내지 않는다. 주소의 글은 쓰지 않는다', async () => {
    const { seen } = signedIn();
    renderApp(`/wallet/card/return?code=PAY_PROCESS_CANCELED&message=${encodeURIComponent('여기로 송금하세요')}`);

    expect(await screen.findByText('카드 등록을 그만두었습니다.')).toBeInTheDocument();
    expect(screen.queryByText(/송금/)).not.toBeInTheDocument();
    expect(registrations(seen)).toHaveLength(0);
  });

  it('주소를 읽지 못하면 서버에 보내지 않는다', async () => {
    const { seen } = signedIn();
    renderApp('/wallet/card/return?customerKey=me&authKey=bln');

    expect(await screen.findByText(/결과를 읽지 못했습니다/)).toBeInTheDocument();
    expect(registrations(seen)).toHaveLength(0);
  });
});
