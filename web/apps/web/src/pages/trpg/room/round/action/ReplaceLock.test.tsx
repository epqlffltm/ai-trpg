// web/apps/web/src/pages/trpg/room/round/action/ReplaceLock.test.tsx
// 자물쇠 바꾸기(#281)를 화면으로 본다. 자물쇠 물건을 지녔고 자물쇠가 있는 문이 열려 있고 부서지지 않았을 때만 고를 수 있고,
// 장소 칸의 문 단추나 행동 고르기로 문과 달 자물쇠를 골라 보내며, 결과와 행동 한 줄에 바꾼 것과 못 한 까닭을 보인다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../../api/refresh';
import type { TableDetail } from '../../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../../test/fakeFetch';
import { renderApp } from '../../../../../test/renderApp';
import { declaration, ME, member, round, roomRoutes, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { actionLabel, outcomeLine } from '../roundView';
import { availableKinds } from './actionOptions';
import { canHandleDoor, lockItems } from './doorOptions';

const TABLE_ID = '00000000-0000-4000-8000-0000000000ee';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const GATE = '00000000-0000-4000-8000-0000000000c1';
const TOWER = '00000000-0000-4000-8000-0000000000c2';
const PADLOCK = '00000000-0000-4000-8000-0000000000a1';
const BREAD = '00000000-0000-4000-8000-0000000000a2';

const OPEN_DOOR = { from_place: GATE, to_place: TOWER, two_way: true, locked: false, barred: null, broken: false };
const ITEMS = [
  { entry_id: PADLOCK, name: '새 자물쇠', kind: 'gear', rarity: 'normal', lock: true },
  { entry_id: BREAD, name: '빵', kind: 'consumable', rarity: 'normal', lock: false },
];

function playing(held = true, route: Record<string, unknown> = OPEN_DOOR) {
  const items = held ? [{ entry_id: PADLOCK, name: '새 자물쇠', kind: 'gear', rarity: 'normal', count: 1 }] : [];
  return tableDetail(TABLE_ID, {
    status: 'playing',
    items: ITEMS,
    map: {
      places: [
        { entry_id: GATE, name: '수도원 문', items: [] },
        { entry_id: TOWER, name: '종탑', items: [] },
      ],
      routes: [route],
    },
    members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({ place_id: GATE, items }) })],
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

describe('자물쇠 바꾸기의 고를 거리', () => {
  it('자물쇠 물건을 지녔고, 자물쇠가 있는 문이 열려 있고 부서지지 않았을 때만', () => {
    expect(lockItems(playing(), playing().members[0]).map((item) => item.entry_id)).toEqual([PADLOCK]);
    expect(availableKinds(ctx(playing()))).toContain('replace');
    expect(availableKinds(ctx(playing(false)))).not.toContain('replace');
    const route = OPEN_DOOR as unknown as NonNullable<TableDetail['map']>['routes'][number];
    expect(canHandleDoor('replace', { ...route, locked: true }, GATE)).toBe(false);
    expect(canHandleDoor('replace', { ...route, broken: true }, GATE)).toBe(false);
    expect(canHandleDoor('replace', { ...route, locked: null, barred: false }, GATE)).toBe(false);
  });

  it('행동 한 줄과 결과에 바꾼 문과 못 한 까닭을 적는다', () => {
    const table = playing();
    expect(actionLabel({ kind: 'replace', place: TOWER, item: PADLOCK }, table)).toBe('자물쇠 바꾸기 · 종탑 쪽 자물쇠 ← 새 자물쇠');
    const door = { user_id: ME, character_name: '렌', from: { entry_id: GATE, name: '수도원 문' }, to: { entry_id: TOWER, name: '종탑' }, act: 'replace', device: null, check: null };
    expect(outcomeLine({ door: { ...door, done: true, reason: null } }, table.rules)).toBe('종탑 쪽 자물쇠: 새 자물쇠로 바꿨습니다');
    expect(outcomeLine({ door: { ...door, done: false, reason: 'used' } }, table.rules)).toBe('종탑 쪽 자물쇠: 바꾸지 못했습니다(이 테이블에서 이미 단 자물쇠입니다)');
  });
});

describe('자물쇠 바꾸기의 선언', () => {
  it('장소 칸의 문 단추로 행동을 채우고, 달 자물쇠를 골라 보낸다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /퀘스트·장소/ }));
    const doors = within(await status.findByRole('list', { name: '문' }));
    await userEvent.click(doors.getByRole('button', { name: '종탑 쪽 문 자물쇠 바꾸기' }));

    const form = within(screen.getByRole('form', { name: '선언' }));
    expect(form.getByLabelText('행동')).toHaveValue('replace');
    expect(form.getByLabelText('문')).toHaveValue(TOWER);
    expect(form.getByText('다룰 문과 달 자물쇠를 골라 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(form.getByLabelText('달 자물쇠'), PADLOCK);
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '새 자물쇠를 단다');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    await vi.waitFor(() => expect(declared(seen)[0]).toMatchObject({ action: { kind: 'replace', place: TOWER, item: PADLOCK } }));
  });
});
