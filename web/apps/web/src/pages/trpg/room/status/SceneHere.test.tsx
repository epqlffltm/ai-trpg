// web/apps/web/src/pages/trpg/room/status/SceneHere.test.tsx
// 퀘스트·지도(J)의 "여기 있는 인물과 몬스터"(#254 의 화면). 내가 선 곳의 몬스터와 인물, 자리가 없는 인물만 보이는지,
// 몸 상태와 부상, 지닌 것을 글로 보이는지, "치기"가 선언 입력을 타격 판정으로 채우는지, 죽은 것에는 단추가 없는지 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Ruleset, SceneCast } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, round, roomRoutes, sheet, tableDetail } from '../../../../test/tableFixtures';
import { sceneEntryNote, sceneHere } from './sceneView';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e4';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const RAT = '00000000-0000-4000-8000-0000000000a1';
const BAT = '00000000-0000-4000-8000-0000000000a2';
const GHOST = '00000000-0000-4000-8000-0000000000a3';
const GUARD = '00000000-0000-4000-8000-0000000000b1';
const COOK = '00000000-0000-4000-8000-0000000000b2';
const VOICE = '00000000-0000-4000-8000-0000000000b3';

const CAST = {
  round: 2,
  people: [
    { id: GUARD, name: '문지기', named: false, status: 'downed', injuries: ['broken_arm'], attitude: 'hostile', items: [], place_id: 'p1' },
    { id: COOK, name: '요리사', named: true, status: 'alive', injuries: [], attitude: 'friendly', items: [], place_id: 'p2' },
    { id: VOICE, name: '목소리', named: false, status: 'alive', injuries: [], attitude: 'neutral', items: [], place_id: null },
  ],
  monsters: [
    {
      id: RAT,
      name: '수로 쥐',
      place_id: 'p1',
      status: 'alive',
      condition: '다침',
      injuries: ['sprain'],
      items: [{ entry_id: 'i3', name: '녹슨 열쇠', rarity: 'normal', count: 1, equipped: false }],
    },
    { id: GHOST, name: '망령', place_id: 'p1', status: 'dead', condition: '죽음', injuries: [], items: [] },
    { id: BAT, name: '박쥐', place_id: 'p2', status: 'alive', condition: '멀쩡함', injuries: [], items: [] },
  ],
} as unknown as SceneCast;

function playing() {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({ place_id: 'p1' }) })],
    map: {
      places: [
        { entry_id: 'p1', name: '수도원 문', items: [] },
        { entry_id: 'p2', name: '부엌', items: [] },
      ],
      routes: [{ from_place: 'p1', to_place: 'p2', travel_minutes: 5, two_way: true }],
    },
  });
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, playing()),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      [`GET ${BASE}/rounds/current/people`]: () => json(200, CAST),
      ...routes,
    }),
  });
}

async function worldPanel() {
  const status = within(await screen.findByRole('region', { name: '상태' }));
  await userEvent.click(status.getByRole('button', { name: /퀘스트·지도/ }));
  return status;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('여기 있는 인물과 몬스터', () => {
  it('내가 선 곳의 것과 자리가 없는 인물만, 몸 상태와 부상과 지닌 것을 붙여 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await worldPanel();
    const list = within(await status.findByRole('list', { name: '여기 있는 인물과 몬스터' }));

    const lines = list.getAllByRole('listitem').map((item) => item.textContent?.replace(/\s+/g, ' ').trim());
    expect(lines).toEqual([
      '문지기 · 쓰러짐 · 부러진 팔 치기',
      '목소리 치기',
      '수로 쥐 (몬스터) · 다침 · 삔 발목 · 지닌 것: 녹슨 열쇠 치기',
      '망령 (몬스터) · 죽음',
    ]);
    // 다른 곳의 것(요리사, 박쥐)은 보이지 않는다
    expect(list.queryByText(/요리사|박쥐/)).toBeNull();
  });

  it('"치기"를 누르면 선언 입력이 그 몬스터를 치는 판정으로 채워진다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await worldPanel();
    await userEvent.click(await status.findByRole('button', { name: '수로 쥐 치기' }));

    const form = within(await screen.findByRole('form', { name: '선언' }));
    expect(form.getByLabelText('행동')).toHaveValue('check');
    expect(form.getByLabelText('대상')).toHaveValue(`monster:${RAT}`);
  });

  it('장면에 아무도 없으면 칸을 보이지 않는다', async () => {
    open({ [`GET ${BASE}/rounds/current/people`]: () => json(200, { round: 2, people: [], monsters: [] }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await worldPanel();
    expect(await status.findByText(/지금 있는 곳: 수도원 문/)).toBeInTheDocument();
    expect(status.queryByRole('list', { name: '여기 있는 인물과 몬스터' })).toBeNull();
  });
});

describe('sceneHere', () => {
  const rules = { injuries: [{ key: 'sprain', name: '삔 발목', healing: 'rounds', aimable: false }] } as unknown as Ruleset;

  it('맵에 서 있지 않으면 자리가 없는 인물만 남는다', () => {
    expect(sceneHere(CAST, null, rules).map((entry) => entry.name)).toEqual(['목소리']);
    expect(sceneHere(undefined, 'p1', rules)).toEqual([]);
  });

  it('붙일 말이 없으면 덧붙임이 없고, 여러 개는 개수를 붙인다', () => {
    const [voice] = sceneHere(CAST, null, rules);
    expect(voice && sceneEntryNote(voice)).toBeNull();
    const many = { ...CAST, people: [], monsters: [{ ...CAST.monsters[0], injuries: [], items: [{ ...CAST.monsters[0]?.items?.[0], count: 3 }] }] } as SceneCast;
    const [rat] = sceneHere(many, 'p1', rules);
    expect(rat && sceneEntryNote(rat)).toBe('다침 · 지닌 것: 녹슨 열쇠 ×3');
    // 규칙에 없는 부상의 이름표는 그대로 보인다
    const odd = { ...CAST, people: [], monsters: [{ ...CAST.monsters[0], items: [], injuries: ['burn'] }] } as SceneCast;
    expect(sceneHere(odd, 'p1', rules)[0]?.state).toEqual(['다침', 'burn']);
  });
});
