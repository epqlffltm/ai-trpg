// web/apps/web/src/pages/trpg/room/round/action/TradeDeclare.test.tsx
// 돈과 사고팔기(#278)를 화면으로 본다. 소지품 탭의 돈과 값, 장면의 상인에게서 사기,
// 소지품의 "팔기"가 상인과 물건을 채우기, 돈이 모자란다는 409 뒤에 테이블을 다시 읽기.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../../test/fakeFetch';
import { renderApp } from '../../../../../test/renderApp';
import { declaration, ME, member, OTHER, round, roomRoutes, sheet, tableDetail } from '../../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000d4';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const SHOP = '00000000-0000-4000-8000-0000000000f4';

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  currency: { name: '금화', unit: '닢', sell_percent: 50 },
  members: [
    member(ME, {
      is_host: true,
      character: { name: '렌', description: '' },
      sheet: sheet({ money: 30, items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', count: 2 }] }),
    }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet({ money: 4 }) }),
  ],
  items: [
    { entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light', price: 8 },
    { entry_id: 'i4', name: '횃불', kind: 'gear', rarity: 'normal', heals: null, price: 5 },
  ],
});

const CAST = {
  round: 2,
  people: [
    {
      id: SHOP,
      name: '행상',
      named: false,
      status: 'alive',
      injuries: [],
      attitude: 'neutral',
      merchant: true,
      items: [{ entry_id: 'i4', name: '횃불', rarity: 'normal', count: 3, equipped: false, price: 5 }],
    },
  ],
  monsters: [],
};

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      [`GET ${BASE}/rounds/current/people`]: () => json(200, CAST),
      [`PUT ${BASE}/rounds/current/declaration`]: (request) =>
        json(200, round(2, { waiting_for: [OTHER], declarations: [declaration(ME, request.body as Record<string, unknown>)] })),
      ...routes,
    }),
  });
}

function puts(seen: SeenRequest[]): SeenRequest[] {
  return seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/rounds/current/declaration`);
}

async function inventory() {
  const status = within(await screen.findByRole('region', { name: '상태' }));
  await userEvent.click(status.getByRole('tab', { name: /소지품/ }));
  return status;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('돈과 사고팔기', () => {
  it('소지품 탭에 저마다 가진 돈과 물건의 값을 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await inventory();
    expect(within(status.getByRole('region', { name: '렌의 소지품' })).getByText('돈 금화 30닢')).toBeInTheDocument();
    expect(within(status.getByRole('region', { name: '미아의 소지품' })).getByText('돈 금화 4닢')).toBeInTheDocument();
    expect(status.getByText(/값 8닢/)).toBeInTheDocument();
  });

  it('장면의 상인에게서 산다. 낼 돈과 가진 돈이 보인다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '횃불을 산다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '사기');
    await userEvent.selectOptions(form.getByLabelText('상인'), '행상');
    await userEvent.selectOptions(form.getByLabelText('살 물건'), '횃불 ×3 · 5닢');
    await userEvent.clear(form.getByLabelText('개수'));
    await userEvent.type(form.getByLabelText('개수'), '2');
    expect(form.getByText('낼 돈 10닢 · 가진 돈 30닢')).toBeInTheDocument();
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await screen.findByText('사기 · 횃불 ×2')).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toEqual({ content: '횃불을 산다', action: { kind: 'buy', npc: SHOP, item: 'i4', count: 2 } });
  });

  it('소지품의 "팔기"가 상인과 물건을 채운다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await inventory();
    await userEvent.click(await status.findByRole('button', { name: '약초 팔기' }));

    const form = within(await screen.findByRole('form', { name: '선언' }));
    expect(form.getByLabelText('행동')).toHaveValue('sell');
    expect(form.getByLabelText('상인')).toHaveValue(`npc:${SHOP}`);
    expect(form.getByLabelText('팔 물건')).toHaveValue('i1');
    expect(form.getByText('받을 돈 4닢 · 가진 돈 30닢')).toBeInTheDocument();
  });

  it('돈이 모자란다는 409 를 알리고 테이블을 다시 읽는다', async () => {
    let tableReads = 0;
    open({
      [`GET ${BASE}`]: () => {
        tableReads += 1;
        return json(200, PLAYING);
      },
      [`PUT ${BASE}/rounds/current/declaration`]: () => json(409, { detail: 'x', reason: 'not_enough_money' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '돈을 준다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '돈 건네기');
    await userEvent.selectOptions(form.getByLabelText('받을 사람'), '미아');
    const before = tableReads;
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await form.findByText('돈이 모자랍니다.')).toBeInTheDocument();
    await vi.waitFor(() => expect(tableReads).toBeGreaterThan(before));
  });
});
