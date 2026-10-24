// web/apps/web/src/pages/trpg/room/round/action/DoorActions.test.tsx
// 문을 다루는 행동(#281)을 화면으로 본다. 지금 문의 상태로 고를 수 있는 행동을 거르고(방향은 보지 않음, 빗장은 빗장 쪽),
// 장소 칸의 "문" 목록과 단추로 행동을 채우고, 갈 수 있는 곳과 갈 곳 고르기에 막는 것을 적고, 장치가 둘이면 장치를 골라 보내고, 결과에 해낸 일과 못 한 까닭을 보인다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../../api/refresh';
import type { TableDetail } from '../../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../../test/fakeFetch';
import { renderApp } from '../../../../../test/renderApp';
import { declaration, ME, member, round, roomRoutes, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { outcomeLine } from '../roundView';
import { emptyActionDraft, toAction } from './actionDraft';
import { availableKinds } from './actionOptions';
import { doorDevices, doorsFor, doorsHere, doorState } from './doorOptions';

const TABLE_ID = '00000000-0000-4000-8000-0000000000ed';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const GATE = '00000000-0000-4000-8000-0000000000c1';
const TOWER = '00000000-0000-4000-8000-0000000000c2';
const CRYPT = '00000000-0000-4000-8000-0000000000c3';
const YARD = '00000000-0000-4000-8000-0000000000c4';
const CHECK = { ability: 'dex', difficulty: 'normal' };

/** 수도원 문–종탑: 잠긴 자물쇠와 걸린 빗장(수도원 문 쪽), 따기와 부수기. 지하 묘지 → 수도원 문(한쪽 길): 부서진 문, 고치기. 마당: 문 없음 */
const MAP = {
  places: [
    { entry_id: GATE, name: '수도원 문', items: [] },
    { entry_id: TOWER, name: '종탑', items: [] },
    { entry_id: CRYPT, name: '지하 묘지', items: [] },
    { entry_id: YARD, name: '마당', items: [] },
  ],
  routes: [
    { from_place: GATE, to_place: TOWER, two_way: true, locked: true, barred: true, bar_side: GATE, broken: false, pick: CHECK, force: { ability: 'str', difficulty: 'normal' } },
    { from_place: CRYPT, to_place: GATE, two_way: false, locked: false, barred: null, broken: true, repair: CHECK },
    { from_place: GATE, to_place: YARD, two_way: true, broken: false },
  ],
};

function playing(place: string = GATE) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    map: MAP,
    members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({ place_id: place }) })],
  }) as unknown as TableDetail;
}

function ctx(table: TableDetail) {
  return { table, me: table.members[0] as TableDetail['members'][number], cast: null };
}

function open() {
  let current = round(2);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, playing()),
      [`GET ${BASE}/rounds/current`]: () => json(200, current),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      [`PUT ${BASE}/rounds/current/declaration`]: (request) => {
        current = round(2, { waiting_for: [], declarations: [declaration(ME, request.body as Record<string, unknown>)] });
        return json(200, current);
      },
    }),
  });
}

function declared(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/rounds/current/declaration`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('문을 다루는 행동의 고를 거리', () => {
  it('내 장소에 닿은 문만, 방향은 보지 않고, 지금 상태로 할 수 있어 보이는 행동만 고른다', () => {
    const table = playing();
    expect(doorsHere(table.map, GATE).map((door) => door.name)).toEqual(['종탑', '지하 묘지']);
    const kinds = availableKinds(ctx(table));
    expect(kinds).toEqual(expect.arrayContaining(['unlock', 'pick', 'force', 'repair']));
    expect(kinds).not.toContain('lock');
    const [tower] = doorsHere(table.map, GATE);
    expect(doorDevices('unlock', tower!.route, GATE)).toEqual(['lock', 'bar']);
    expect(doorDevices('unlock', tower!.route, TOWER)).toEqual(['lock']);
    expect(doorsFor('lock', table.map, CRYPT)).toEqual([]);
    expect(doorState(tower!, table.map!)).toBe('자물쇠 잠김 · 빗장 걸림(수도원 문 쪽)');
    expect(availableKinds(ctx(playing(YARD)))).not.toContain('unlock');
  });

  it('열기와 잠그기는 장치를 적어 보낸다. 고른 장치를 할 수 없으면 할 수 있는 것으로 바꾼다', () => {
    const table = playing(TOWER);
    const draft = { ...emptyActionDraft(table.rules), kind: 'unlock' as const, place: GATE, device: 'bar' };
    expect(toAction(draft, ctx(table))).toEqual({ kind: 'unlock', place: GATE, device: 'lock' });
    expect(toAction({ ...draft, kind: 'pick' }, ctx(table))).toEqual({ kind: 'pick', place: GATE });
  });

  it('결과에 해낸 일과 못 한 까닭, 판정을 보인다', () => {
    const rules = playing().rules;
    const to = { entry_id: TOWER, name: '종탑' };
    const base = { user_id: ME, character_name: '렌', from: { entry_id: GATE, name: '수도원 문' }, to, check: null };
    expect(outcomeLine({ door: { ...base, act: 'unlock', device: 'bar', done: true, reason: null } }, rules)).toBe('종탑 쪽 빗장: 열었습니다');
    const check = { ability: 'dex', difficulty: 'normal', modifier: 1, roll: 8, total: 9, target: 15, success: false };
    expect(outcomeLine({ door: { ...base, act: 'pick', device: null, done: false, reason: 'failed', check } }, rules)).toBe(
      '종탑 쪽 문: 따지 못했습니다(판정에 실패했습니다) · 눈 8, 보정 +1, 합 9 / 목표 15',
    );
    expect(outcomeLine({ door: { ...base, act: 'unlock', device: 'lock', done: false, reason: 'no_key' } }, rules)).toBe('종탑 쪽 자물쇠: 열지 못했습니다(열쇠가 없었습니다)');
  });
});

describe('문을 다루는 선언', () => {
  it('장소 칸의 문 목록의 단추로 행동을 채우고, 따기를 보낸다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /퀘스트·장소/ }));
    const ways = within(await status.findByRole('list', { name: '갈 수 있는 곳' }));
    expect(ways.getByText('(걸리는 시간 모름 · 자물쇠 잠김 · 빗장 걸림(이쪽))')).toBeInTheDocument();
    const doors = within(await status.findByRole('list', { name: '문' }));
    expect(doors.getByText('(자물쇠 잠김 · 빗장 걸림(수도원 문 쪽))')).toBeInTheDocument();
    expect(doors.queryByRole('button', { name: '종탑 쪽 문 잠그기' })).toBeNull();
    expect(doors.getByRole('button', { name: '지하 묘지 쪽 문 고치기' })).toBeInTheDocument();
    await userEvent.click(doors.getByRole('button', { name: '종탑 쪽 문 따기' }));

    const form = within(screen.getByRole('form', { name: '선언' }));
    expect(form.getByLabelText('행동')).toHaveValue('pick');
    expect(form.getByLabelText('문')).toHaveValue(TOWER);
    expect(form.getByText(/판정: 민첩, 보통/)).toBeInTheDocument();
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '쇠꼬챙이로 자물쇠를 쑤신다');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    await vi.waitFor(() => expect(declared(seen)[0]).toMatchObject({ action: { kind: 'pick', place: TOWER } }));
  });

  it('열기에서 장치가 둘이면 장치를 골라 보낸다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.selectOptions(await form.findByLabelText('행동'), 'move');
    expect(within(form.getByLabelText('갈 곳')).getByRole('option', { name: '종탑(자물쇠 잠김 · 빗장 걸림(이쪽))' })).toBeInTheDocument();
    await userEvent.selectOptions(form.getByLabelText('행동'), 'unlock');
    expect(within(form.getByLabelText('문')).queryByRole('option', { name: /지하 묘지/ })).toBeNull();
    await userEvent.selectOptions(form.getByLabelText('문'), TOWER);
    await userEvent.selectOptions(form.getByLabelText('장치'), 'bar');
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '빗장을 들어 올린다');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    await vi.waitFor(() => expect(declared(seen)[0]).toMatchObject({ action: { kind: 'unlock', place: TOWER, device: 'bar' } }));
  });
});
