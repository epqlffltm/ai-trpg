// web/apps/web/src/pages/wallet/AutoCharge.test.tsx
// 지갑(A6)의 자동 충전(#980). 카드 등록(시험용 등록 창, 두 걸음), 카드 지우기, 설정 저장과 화면의 검사, 서버의 거절(카드 없음, 결제 자격)을 본다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';

const BILLING = '/api/v1/billing';
const KEY = '6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11';
const PRODUCTS = [
  { id: 'credits-1000', name: '크레딧 1,000', price: 1000, credits: '1000' },
  { id: 'credits-5000', name: '크레딧 5,000', price: 5000, credits: '5000' },
];
const CARD = { issuer_code: '61', number: '43301234****123*', registered_at: '2026-11-04T01:00:00Z' };
const NOTHING = { settings: null, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } };

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => json(200, { paid: '80', free: '0', total: '80', next_expiry: null }),
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${BILLING}/products`]: () => json(200, { products: PRODUCTS }),
    [`GET ${BILLING}/auto-charge`]: () => json(200, NOTHING),
    ...routes,
  });
}

async function section() {
  return within(await screen.findByRole('region', { name: '자동 충전' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('자동 충전', () => {
  it('시험용 등록 창에서 카드를 등록한다. 고객 키를 받고, 고른 자동 결제의 결과를 인증 키에 넣는다', async () => {
    let registered = false;
    const { seen } = signedIn({
      [`GET ${BILLING}/auto-charge`]: () => json(200, registered ? { ...NOTHING, card: CARD } : NOTHING),
      [`POST ${BILLING}/cards/customer-key`]: () => json(200, { customer_key: KEY }),
      [`POST ${BILLING}/cards`]: () => {
        registered = true;
        return json(201, CARD);
      },
    });
    renderApp('/wallet');
    const auto = await section();
    expect(await auto.findByText('등록한 카드가 없습니다.')).toBeInTheDocument();

    await userEvent.click(auto.getByRole('button', { name: '카드 등록' }));
    await userEvent.selectOptions(auto.getByRole('combobox', { name: '이 카드로 자동 결제할 때' }), '자동 결제가 거절됨');
    await userEvent.click(auto.getByRole('button', { name: '카드 등록' }));

    expect(await auto.findByText('카드를 등록했습니다.')).toBeInTheDocument();
    expect(await auto.findByText(/43301234\*\*\*\*123\*/)).toBeInTheDocument();
    const body = seen.find((request) => request.method === 'POST' && request.url.endsWith('/cards'))?.body as Record<string, string>;
    expect(body.customer_key).toBe(KEY);
    expect(body.auth_key).toMatch(/^fake_card_ok_[A-Za-z0-9]+_charge_declined$/);
    expect(auto.getByRole('button', { name: '카드 바꾸기' })).toBeInTheDocument();
  });

  it('등록이 거절되면 그 까닭을 보이고 카드는 그대로다', async () => {
    signedIn({
      [`POST ${BILLING}/cards/customer-key`]: () => json(200, { customer_key: KEY }),
      [`POST ${BILLING}/cards`]: () => json(422, { detail: 'x', code: 'card.refused' }),
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('button', { name: '카드 등록' }));
    await userEvent.click(auto.getByRole('button', { name: '카드 거절' }));

    expect(await auto.findByText('카드를 등록하지 못했습니다. 다른 카드로 해 주세요.')).toBeInTheDocument();
    expect(auto.getByText('등록한 카드가 없습니다.')).toBeInTheDocument();
  });

  it('카드를 지우려면 한 번 더 누른다. 지우면 다시 읽는다', async () => {
    let removed = false;
    const { seen } = signedIn({
      [`GET ${BILLING}/auto-charge`]: () => json(200, removed ? NOTHING : { ...NOTHING, card: CARD }),
      [`DELETE ${BILLING}/cards`]: () => {
        removed = true;
        return new Response(null, { status: 204 });
      },
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('button', { name: '카드 지우기' }));
    expect(seen.some((request) => request.method === 'DELETE')).toBe(false);
    await userEvent.click(auto.getByRole('button', { name: '지우기' }));

    expect(await auto.findByText('카드를 지우고 자동 충전을 껐습니다.')).toBeInTheDocument();
    expect(await auto.findByText('등록한 카드가 없습니다.')).toBeInTheDocument();
  });

  it('설정을 적으면 서버가 돌려준 설정을 보인다', async () => {
    const saved = {
      settings: { enabled: true, threshold: '300', product_id: 'credits-5000', monthly_limit: 20000 },
      consecutive_failures: 0,
      card: CARD,
      terms: { version: 1, agreed_version: 1 },
    };
    const { seen } = signedIn({
      [`GET ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, card: CARD }),
      [`PUT ${BILLING}/auto-charge`]: () => json(200, saved),
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: '자동 충전 켜기' }));
    await userEvent.clear(auto.getByRole('textbox', { name: '기준 골드' }));
    await userEvent.type(auto.getByRole('textbox', { name: '기준 골드' }), '300');
    await userEvent.selectOptions(auto.getByRole('combobox', { name: '살 상품' }), 'credits-5000');
    await userEvent.clear(auto.getByRole('textbox', { name: '한 달 상한(원)' }));
    await userEvent.type(auto.getByRole('textbox', { name: '한 달 상한(원)' }), '20000');
    // 동의하는 칸 위에 고른 조건이 그대로 보인다
    expect(auto.getByText('골드가 300 아래로 떨어지면 등록한 카드로 크레딧 5,000(5,000원)을 한 번 결제합니다.')).toBeInTheDocument();
    expect(auto.getByText('한 달(한국 날짜)에 자동으로 결제하는 돈은 20,000원을 넘지 않습니다.')).toBeInTheDocument();
    await userEvent.click(auto.getByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ }));
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    expect(await auto.findByText('자동 충전을 켰습니다.')).toBeInTheDocument();
    expect(seen.find((request) => request.method === 'PUT')?.body).toEqual({
      enabled: true,
      threshold: '300',
      product_id: 'credits-5000',
      monthly_limit: 20000,
      terms_version: 1,
    });
    expect(auto.getByRole('checkbox', { name: '자동 충전 켜기' })).toBeChecked();
    expect(auto.getByRole('textbox', { name: '기준 골드' })).toHaveValue('300');
  });

  it('끄고 적으면 끈 설정을 보이고, 돌려받은 것으로 끝낸다(다시 읽지 않는다)', async () => {
    const on = { enabled: true, threshold: '500', product_id: 'credits-1000', monthly_limit: 30000 };
    const { seen } = signedIn({
      [`GET ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, settings: on, card: CARD }),
      [`PUT ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, settings: { ...on, enabled: false }, card: CARD }),
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: '자동 충전 켜기' }));
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    expect(await auto.findByText('자동 충전 설정을 저장했습니다.')).toBeInTheDocument();
    expect(auto.getByRole('checkbox', { name: '자동 충전 켜기' })).not.toBeChecked();
    // 끄는 것은 동의가 필요 없다
    expect(seen.find((request) => request.method === 'PUT')?.body).not.toHaveProperty('terms_version');
    await new Promise((resolve) => setTimeout(resolve, 50));
    const reads = seen.filter((request) => request.method === 'GET' && request.url.endsWith('/auto-charge'));
    expect(reads).toHaveLength(1);
  });

  it('화면이 먼저 틀린 값을 막는다. 보내지 않는다', async () => {
    const { seen } = signedIn();
    renderApp('/wallet');
    const auto = await section();

    await userEvent.selectOptions(await auto.findByRole('combobox', { name: '살 상품' }), 'credits-5000');
    await userEvent.clear(auto.getByRole('textbox', { name: '한 달 상한(원)' }));
    await userEvent.type(auto.getByRole('textbox', { name: '한 달 상한(원)' }), '4000');
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    expect(await auto.findByText('한 달 상한은 고른 상품의 값보다 작을 수 없습니다.')).toBeInTheDocument();
    expect(seen.some((request) => request.method === 'PUT')).toBe(false);
  });

  it('카드 없이 켜거나 보호자 동의가 없으면 서버의 까닭과 갈 길을 보인다', async () => {
    let calls = 0;
    signedIn({
      [`PUT ${BILLING}/auto-charge`]: () => {
        calls += 1;
        return calls === 1
          ? json(409, { detail: 'x', code: 'autocharge.no_card' })
          : json(403, { detail: 'x', code: 'payment.guardian_consent_required' });
      },
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: '자동 충전 켜기' }));
    await userEvent.click(auto.getByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ }));
    await userEvent.click(auto.getByRole('button', { name: '저장' }));
    expect(await auto.findByText('자동 충전을 켜려면 먼저 카드를 등록해 주세요.')).toBeInTheDocument();
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    expect(await auto.findByText(/보호자가 동의해야 자동 충전을 켤 수 있습니다/)).toBeInTheDocument();
    expect(auto.getByRole('link', { name: '보호자 동의 부탁하기' })).toHaveAttribute('href', '/me/guardian');
  });

  it('동의하지 않으면 켜지 않고 보내지 않는다. 동의 칸은 미리 체크하지 않고, 조건을 바꾸면 다시 비운다', async () => {
    const { seen } = signedIn({ [`GET ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, card: CARD }) });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: '자동 충전 켜기' }));
    const agree = auto.getByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ });
    expect(agree).not.toBeChecked();
    await userEvent.click(agree);
    await userEvent.clear(auto.getByRole('textbox', { name: '기준 골드' }));
    await userEvent.type(auto.getByRole('textbox', { name: '기준 골드' }), '900');
    expect(auto.getByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ })).not.toBeChecked();
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    expect(await auto.findByText('자동 충전을 켜려면 자동 결제에 동의해 주세요.')).toBeInTheDocument();
    expect(seen.some((request) => request.method === 'PUT')).toBe(false);
  });

  it('동의 내용을 창으로 본다', async () => {
    signedIn({ [`GET ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, card: CARD }) });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: '자동 충전 켜기' }));
    await userEvent.click(auto.getByRole('button', { name: '동의 내용 보기' }));

    const dialog = await screen.findByRole('dialog', { name: '자동 충전 이용 동의' });
    expect(await within(dialog).findByRole('heading', { name: '1. 무엇에 동의하는지' })).toBeInTheDocument();
  });

  it('서버가 판이 바뀌었다고 막으면(409) 다시 읽어 바뀐 판을 보이고 동의 칸을 비운다', async () => {
    let reads = 0;
    const on = { enabled: true, threshold: '500', product_id: 'credits-1000', monthly_limit: 30000 };
    const { seen } = signedIn({
      [`GET ${BILLING}/auto-charge`]: () => {
        reads += 1;
        return json(200, { ...NOTHING, settings: on, card: CARD, terms: { version: reads === 1 ? 1 : 2, agreed_version: 1 } });
      },
      [`PUT ${BILLING}/auto-charge`]: () => json(409, { detail: 'x', code: 'autocharge.terms_outdated' }),
    });
    renderApp('/wallet');
    const auto = await section();

    await userEvent.click(await auto.findByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ }));
    await userEvent.click(auto.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(reads).toBe(2));
    expect(seen.find((request) => request.method === 'PUT')?.body).toMatchObject({ terms_version: 1 });
    const agree = await auto.findByRole('checkbox', { name: /자동 결제하는 것에 동의합니다/ });
    expect(agree).not.toBeChecked();
    // 화면이 아직 갖지 않은 판(2)이라 동의할 수 없다. 새로 고치면 받는다
    expect(agree).toBeDisabled();
    expect(auto.getAllByText('자동 결제 동의의 내용이 바뀌었습니다. 바뀐 내용을 읽고 다시 동의해 주세요.').length).toBeGreaterThan(0);
  });

  it('전에 동의한 판이 옛 판이면 켜 둔 화면에서 다시 동의하라고 알린다', async () => {
    const on = { enabled: true, threshold: '500', product_id: 'credits-1000', monthly_limit: 30000 };
    signedIn({
      [`GET ${BILLING}/auto-charge`]: () => json(200, { ...NOTHING, settings: on, card: CARD, terms: { version: 1, agreed_version: 0 } }),
    });
    renderApp('/wallet');
    const auto = await section();

    expect(await auto.findByText('자동 결제 동의의 내용이 바뀌었습니다. 바뀐 내용을 읽고 다시 동의해 주세요.')).toBeInTheDocument();
  });
});
