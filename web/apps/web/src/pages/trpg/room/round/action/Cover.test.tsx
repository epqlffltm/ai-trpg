// web/apps/web/src/pages/trpg/room/round/action/Cover.test.tsx
// 엄폐하기(#276 의 커버 세이브)를 화면으로 본다. 세이브 방식이고 선 곳에 커버가 있을 때만 고를 수 있고,
// 장소 칸에 커버와 "엄폐" 단추가 있으며, 결과에 숨은 곳과 커버, 맞은 공격의 커버 세이브가 보인다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TableDetail } from '../../../../../api/types';
import { REFRESH_PATH } from '../../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../../test/fakeFetch';
import { renderApp } from '../../../../../test/renderApp';
import { declaration, ME, member, RULES, round, roomRoutes, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { placeCover } from '../../status/statusView';
import { blowLine, outcomeLine } from '../roundView';
import { availableKinds, coverHere } from './actionOptions';

const TABLE_ID = '00000000-0000-4000-8000-0000000000ec';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const GATE = '00000000-0000-4000-8000-0000000000d1';
const DRAIN = '00000000-0000-4000-8000-0000000000d2';
const SAVE = { mode: 'save', save_target: 15, pierce_base: 10 };
const MAP = {
  places: [
    { entry_id: GATE, name: '수로 입구', items: [], cover: 7 },
    { entry_id: DRAIN, name: '배수로', items: [], cover: 0 },
  ],
  routes: [{ from_place: GATE, to_place: DRAIN, two_way: true, travel_minutes: null }],
};

function playing(armor: unknown = SAVE, place: string = GATE) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    rules: { ...RULES, armor },
    map: MAP,
    members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({ place_id: place }) })],
  }) as unknown as TableDetail;
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
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
      ...routes,
    }),
  });
}

function ctx(table: TableDetail) {
  return { table, me: table.members[0] as TableDetail['members'][number], cast: null };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('엄폐하기', () => {
  it('세이브 방식이고 선 곳에 커버가 있을 때만 고를 수 있다', () => {
    expect(coverHere(ctx(playing()))).toBe(7);
    expect(availableKinds(ctx(playing()))).toContain('cover');
    expect(coverHere(ctx(playing({ mode: 'ac', save_target: null, pierce_base: 10 })))).toBe(0);
    expect(availableKinds(ctx(playing(SAVE, DRAIN)))).not.toContain('cover');
    expect(placeCover(playing(), null)).toBe(0);
  });

  it('결과에 숨은 곳과 커버, 맞은 공격의 커버 세이브가 보인다', () => {
    const table = playing();
    const covered = { cover: { place: { entry_id: GATE, name: '수로 입구' }, value: 7 } };
    expect(outcomeLine(covered, table.rules)).toBe('엄폐: 수로 입구 · 커버 7');
    expect(outcomeLine({ cover: { place: null, value: 0 } }, table.rules)).toBe('숨을 곳이 없어 엄폐하지 못했습니다.');
    const save = { kind: 'cover', value: 7, roll: 10, target: 15, saved: true };
    const blow = { weapon: null, location: 'body', location_name: '몸', aimed: false, defense: 5, mode: 'save', pierce: null, save };
    expect(blowLine(blow)).toBe('몸 · 방어 5 · 커버 세이브 10 + 7 → 막음');
  });

  it('장소 칸의 엄폐 단추로 행동을 채우고, 선언하면 {kind: cover} 를 보낸다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.click(status.getByRole('tab', { name: /퀘스트·장소/ }));
    expect(await status.findByText(/숨을 곳: 커버 7/)).toBeInTheDocument();
    await userEvent.click(status.getByRole('button', { name: /엄폐/ }));

    const form = within(screen.getByRole('form', { name: '선언' }));
    expect(form.getByLabelText('행동')).toHaveValue('cover');
    expect(form.getByText(/지금 있는 곳의 커버\(7\)로 커버 세이브를 받습니다/)).toBeInTheDocument();
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '무너진 담 뒤로 숨는다');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    await vi.waitFor(() => {
      const sent = seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/rounds/current/declaration`);
      expect(sent[0]?.body).toMatchObject({ action: { kind: 'cover' } });
    });
  });
});
