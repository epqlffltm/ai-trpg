// web/apps/web/src/pages/trpg/room/round/action/ActionDeclare.test.tsx
// 행동을 붙인 선언(③-2). 장면의 인물을 공격하기, 상태 패널의 단추로 행동 칸을 채우기(낸 선언을 고칠 때도),
// 쓰러진 캐릭터는 글만 내기를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../../test/fakeFetch';
import { renderApp } from '../../../../../test/renderApp';
import { declaration, ME, member, OTHER, round, roomRoutes, sheet, tableDetail } from '../../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000d3';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const NPC = '00000000-0000-4000-8000-0000000000f1';

function playing(mySheet: Record<string, unknown> = {}) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    members: [
      member(ME, {
        is_host: true,
        character: { name: '렌', description: '' },
        sheet: sheet({ place_id: 'p1', items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', count: 3 }], ...mySheet }),
      }),
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet({ place_id: 'p1' }) }),
    ],
    items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light' }],
    map: {
      places: [
        { entry_id: 'p1', name: '수도원 문', items: [] },
        { entry_id: 'p2', name: '부엌', items: [] },
      ],
      routes: [{ from_place: 'p1', to_place: 'p2', travel_minutes: 5, two_way: true }],
    },
  });
}

const CAST = {
  round: 2,
  people: [{ id: NPC, name: '문지기', named: false, status: 'alive', injuries: [], attitude: 'hostile', items: [] }],
  monsters: [],
};

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  // 실제 서버처럼, 선언을 낸 뒤의 지금 라운드 읽기에도 낸 것이 보인다(이벤트의 묶은 읽기가 언제 와도 같다)
  let current = round(2);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, playing()),
      [`GET ${BASE}/rounds/current`]: () => json(200, current),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      [`GET ${BASE}/rounds/current/people`]: () => json(200, CAST),
      [`PUT ${BASE}/rounds/current/declaration`]: (request) => {
        current = round(2, { waiting_for: [OTHER], declarations: [declaration(ME, request.body as Record<string, unknown>)] });
        return json(200, current);
      },
      ...routes,
    }),
  });
}

function puts(seen: SeenRequest[]): SeenRequest[] {
  return seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/rounds/current/declaration`);
}

async function declarationForm() {
  return within(await screen.findByRole('form', { name: '선언' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('행동을 붙인 선언', () => {
  it('장면의 인물을 골라 공격한다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = await declarationForm();
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '문지기를 벤다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '판정');
    await userEvent.click(form.getByRole('radio', { name: '공격' }));
    expect(form.getByRole('button', { name: '선언하기' })).toBeDisabled();
    await userEvent.selectOptions(await form.findByLabelText('대상'), '문지기');
    await userEvent.selectOptions(form.getByLabelText('피해'), '무거움(2d6)');
    await userEvent.click(form.getByRole('checkbox', { name: '죽이려 한다' }));
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await screen.findByText('판정 · 근력, 보통, 죽이려는 공격')).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toEqual({
      content: '문지기를 벤다',
      action: { kind: 'check', ability: 'str', difficulty: 'normal', harm: 'heavy', lethal: true, npc: NPC },
    });
  });

  it('소지품의 "건네기"가 행동 칸을 채운다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /소지품/ }));
    await userEvent.click(await status.findByRole('button', { name: '약초 건네기' }));

    const form = await declarationForm();
    expect(form.getByLabelText('행동')).toHaveValue('give');
    expect(form.getByLabelText('건넬 물건')).toHaveValue('i1');
    expect(form.getByLabelText('무엇을 하나요')).toHaveFocus();
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '미아에게 약초를 준다');
    await userEvent.selectOptions(form.getByLabelText('받을 사람'), '미아');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await screen.findByText('건네기 · 약초 ×1 → 미아')).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toMatchObject({ action: { kind: 'give', item: 'i1', count: 1, target: OTHER } });
  });

  it('낸 선언을 보던 중에 "가기"를 누르면 고치는 입력이 열리고 갈 곳이 채워진다', async () => {
    const mine = declaration(ME, { content: '둘러본다', action: null });
    open({ [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { waiting_for: [OTHER], declarations: [mine] })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('button', { name: '고치기' })).toBeInTheDocument();
    const status = within(screen.getByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /퀘스트·장소/ }));
    await userEvent.click(await status.findByRole('button', { name: '부엌 가기' }));

    const form = await declarationForm();
    expect(form.getByLabelText('행동')).toHaveValue('move');
    expect(form.getByLabelText('갈 곳')).toHaveValue('p2');
    expect(form.getByLabelText('무엇을 하나요')).toHaveValue('둘러본다');
    expect(form.getByRole('button', { name: '고쳐 내기' })).toBeEnabled();
  });

  it('쓰러졌으면 행동 없이 글만 낸다. 패널의 단추도 막힌다', async () => {
    open({ [`GET ${BASE}`]: () => json(200, playing({ hp: 0 })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = await declarationForm();
    expect(form.getByText(/행동을 붙일 수 없습니다/)).toBeInTheDocument();
    expect(form.queryByLabelText('행동')).not.toBeInTheDocument();
    const status = within(screen.getByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /소지품/ }));
    expect(status.getByRole('button', { name: '약초 쓰기' })).toBeDisabled();
  });
});
