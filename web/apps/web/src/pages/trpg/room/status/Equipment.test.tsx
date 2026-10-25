// web/apps/web/src/pages/trpg/room/status/Equipment.test.tsx
// 장비(#276)를 화면으로 본다. 소지품 탭의 칸별 착용, 벗기(DELETE), 정해진 칸의 착용(PUT), 칸을 고르는 착용,
// 라운드가 닫는 중이면 막힘, 409 의 알림, 공격에 무기와 부위를 붙여 선언하기.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { declaration, ME, member, OTHER, RULES, round, roomRoutes, sheet, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e9';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const NPC = '00000000-0000-4000-8000-0000000000f1';
const SLOTS = [
  { key: 'main_hand', name: '주손', hit_weight: 0 },
  { key: 'off_hand', name: '보조손', hit_weight: 0 },
  { key: 'body', name: '몸', hit_weight: 3 },
];
const ITEMS = [
  { entry_id: 'sword', name: '장검', kind: 'gear', rarity: 'normal', effects: [], slots: ['main_hand', 'off_hand'], slot_count: 2, attack: 2 },
  { entry_id: 'mail', name: '사슬 갑옷', kind: 'gear', rarity: 'normal', effects: [], slots: ['body'], slot_count: 1, defense: 4 },
  { entry_id: 'dagger', name: '단검', kind: 'gear', rarity: 'normal', effects: [], slots: ['main_hand', 'off_hand'], slot_count: 1, attack: 1 },
];
const HELD = ITEMS.map((item) => ({ entry_id: item.entry_id, name: item.name, kind: 'gear', rarity: 'normal', count: 1 }));
const SWORD = { entry_id: 'sword', name: '장검', slots: ['main_hand', 'off_hand'] };

function playing(worn: unknown[]) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    rules: { ...RULES, equipment_slots: SLOTS, armor: { mode: 'ac' }, called_shot: { raise: 2 } },
    items: ITEMS,
    members: [
      member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({ items: HELD, worn }) }),
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
    ],
  });
}

const CAST = { round: 2, people: [{ id: NPC, name: '문지기', named: false, status: 'alive', injuries: [], attitude: 'hostile', items: [] }], monsters: [] };

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  let current = round(2);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, playing([SWORD])),
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

async function myGear() {
  const status = within(await screen.findByRole('region', { name: '상태' }));
  await userEvent.click(status.getByRole('tab', { name: /소지품/ }));
  return within(await status.findByRole('group', { name: '렌의 장비' }));
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === `${BASE}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장비', () => {
  it('칸마다 착용한 것을 보이고, 벗기를 누르면 그 칸을 비우고 받은 테이블로 바꾼다', async () => {
    const { seen } = open({ [`DELETE ${BASE}/equipment/main_hand`]: () => json(200, playing([])) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const gear = await myGear();
    expect(gear.getByText('주손·보조손')).toBeInTheDocument();
    expect(gear.getByText('장검')).toBeInTheDocument();
    expect(gear.getByText(/방어는 맞히기 어렵게/)).toBeInTheDocument();
    await userEvent.click(await gear.findByRole('button', { name: '장검 벗기' }));

    expect(await gear.findAllByText('비어 있음')).toHaveLength(3);
    expect(sent(seen, 'DELETE', '/equipment/main_hand')).toHaveLength(1);
    expect(screen.getByRole('group', { name: '미아의 장비' })).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: '미아의 장비' })).queryByRole('button')).toBeNull();
  });

  it('들어갈 칸이 정해진 물건은 바로 착용하고, 고를 수 있으면 칸을 골라 착용한다', async () => {
    const { seen } = open({
      [`PUT ${BASE}/equipment`]: (request) => {
        const body = request.body as { entry_id: string; slots: string[] };
        return json(200, playing([SWORD, { entry_id: body.entry_id, name: body.entry_id === 'mail' ? '사슬 갑옷' : '단검', slots: body.slots }]));
      },
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await myGear();
    await userEvent.click(await screen.findByRole('button', { name: '사슬 갑옷 착용' }));
    expect(await screen.findByText(/착용\(몸\)/)).toBeInTheDocument();
    expect(sent(seen, 'PUT', '/equipment')[0]?.body).toEqual({ entry_id: 'mail', slots: ['body'] });

    await userEvent.click(screen.getByRole('button', { name: '단검 착용' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: '착용하기' })).toBeDisabled();
    await userEvent.click(dialog.getByRole('checkbox', { name: /보조손/ }));
    expect(dialog.getByRole('checkbox', { name: /주손/ })).toBeDisabled();
    await userEvent.click(dialog.getByRole('button', { name: '착용하기' }));

    await vi.waitFor(() => expect(sent(seen, 'PUT', '/equipment')[1]?.body).toEqual({ entry_id: 'dagger', slots: ['off_hand'] }));
  });

  it('라운드가 닫는 중이면 착용과 벗기를 막는다', async () => {
    open({ [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { status: 'closing', waiting_for: [] })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const gear = await myGear();
    expect(await gear.findByRole('button', { name: '장검 벗기' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '사슬 갑옷 착용' })).toBeDisabled();
  });

  it('그 사이 닫기 시작했으면 409 를 알린다', async () => {
    open({ [`DELETE ${BASE}/equipment/main_hand`]: () => json(409, { detail: 'x', reason: 'round_closing' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const gear = await myGear();
    await userEvent.click(await gear.findByRole('button', { name: '장검 벗기' }));
    expect(await gear.findByText(/라운드를 마감하는 중에는 장비를 바꿀 수 없습니다/)).toBeInTheDocument();
  });

  it('공격에 착용한 무기와 노릴 부위를 붙인다. 부위를 고르면 부상 노리기를 비운다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '장검으로 벤다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '판정');
    await userEvent.click(form.getByRole('radio', { name: '공격' }));
    await userEvent.selectOptions(await form.findByLabelText('대상'), '문지기');
    await userEvent.selectOptions(form.getByLabelText('노려 치기(선택)'), '부러진 팔');
    await userEvent.selectOptions(form.getByLabelText('무기(선택)'), '장검(+2)');
    await userEvent.selectOptions(form.getByLabelText('노릴 부위(선택)'), '몸');
    expect(form.getByLabelText('노려 치기(선택)')).toHaveValue('');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await screen.findByText(/장검, 몸 노림/)).toBeInTheDocument();
    expect(sent(seen, 'PUT', '/rounds/current/declaration')[0]?.body).toMatchObject({
      action: { kind: 'check', harm: 'light', npc: NPC, weapon: 'sword', strike: 'body' },
    });
  });
});
