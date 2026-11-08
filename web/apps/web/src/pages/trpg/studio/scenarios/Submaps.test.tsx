// web/apps/web/src/pages/trpg/studio/scenarios/Submaps.test.tsx
// 하위 맵(#284). 지도 탭의 장소 창에서 "어느 장소 안에 있나"를 고르면 하위 맵 목록을 통째로 보내고, 자기 안의 장소는 고를 거리에 없고,
// 장소의 한 줄에 품은 장소와 품은 곳의 수가 보인다. 테이블 방에서는 위치를 품은 장소부터 적고 들고 나는 길에 이름을 단다.
// 입력과 보기의 순수한 함수도 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { TableMap } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { placePath, wayStep } from '../../room/status/statusView';
import { containerOf, deepest, insideOf, submapsProblem, withContainer } from './submapsForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const TOWN = '00000000-0000-4000-8000-00000000c001';
const INN = '00000000-0000-4000-8000-00000000c002';
const FLOOR = '00000000-0000-4000-8000-00000000c003';

function entry(id: string, name: string) {
  return { id, name, kind: 'place', keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function route(from: string, to: string) {
  return { from_place: from, to_place: to, two_way: true, visibility: 'open', find: null, travel_minutes: null, cross: null, lock: null, bar: null, force: null, repair: null };
}

function signedIn() {
  let current = scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    start_place: TOWN,
    routes: [route(TOWN, INN), route(INN, FLOOR)],
    submaps: [{ place_id: TOWN, places: [INN] }],
  });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () => json(200, [entry(TOWN, '마을'), entry(INN, '여관'), entry(FLOOR, '2층')]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  });
}

function patches(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as Record<string, unknown>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('지도 탭의 하위 맵', () => {
  it('장소의 한 줄에 품은 장소와 품은 곳의 수가 있고, 창에서 품은 장소를 고르면 하위 맵을 통째로 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const list = within(await within(await screen.findByRole('tabpanel', { name: '지도' })).findByRole('list', { name: '장소' }));
    expect(await list.findByText('시작 · 길 1 · 품은 곳 1')).toBeInTheDocument();
    expect(list.getByText('마을 안 · 길 2')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '2층 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '어느 장소 안에 있나' }), INN);
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.submaps).toEqual([
      { place_id: TOWN, places: [INN] },
      { place_id: INN, places: [FLOOR] },
    ]);
  });

  it('자기 자신과 자기 안의 장소는 품은 장소로 고를 수 없다', async () => {
    signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const list = within(await within(await screen.findByRole('tabpanel', { name: '지도' })).findByRole('list', { name: '장소' }));
    await userEvent.click(await list.findByRole('button', { name: '마을 고치기' }));
    const select = within(await screen.findByRole('dialog')).getByRole('combobox', { name: '어느 장소 안에 있나' });

    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual(['바깥 맵', '2층']);
  });
});

describe('하위 맵의 입력', () => {
  const submaps = [
    { place_id: 'town', places: ['inn'] },
    { place_id: 'inn', places: ['floor'] },
  ];

  it('품은 장소를 바꾸면 옛 하위 맵에서 빼고, 비면 지우고, 새로 품으면 끝에 더한다', () => {
    expect(containerOf(submaps, 'floor')).toBe('inn');
    expect(containerOf(submaps, 'town')).toBe('');
    expect(withContainer(submaps, 'floor', '')).toEqual([{ place_id: 'town', places: ['inn'] }]);
    expect(withContainer(submaps, 'floor', 'town')).toEqual([{ place_id: 'town', places: ['inn', 'floor'] }]);
    expect(withContainer([], 'cellar', 'town')).toEqual([{ place_id: 'town', places: ['cellar'] }]);
  });

  it('자기 안의 장소(겹친 것까지), 깊이, 서버가 받지 않는 모양의 까닭', () => {
    expect([...insideOf(submaps, 'town')].sort()).toEqual(['floor', 'inn']);
    expect(deepest(submaps)).toBe(2);
    expect(deepest([{ place_id: 'a', places: ['b'] }, { place_id: 'b', places: ['a'] }])).toBe(Infinity);
    const four = withContainer(submaps, 'cellar', 'floor');
    expect(deepest(withContainer(four, 'vault', 'cellar'))).toBe(4);
    expect(submapsProblem(withContainer(four, 'vault', 'cellar'))).toContain('3 겹까지');
    expect(submapsProblem(four)).toBeNull();
  });
});

describe('테이블 방의 하위 맵', () => {
  const map = {
    places: [
      { entry_id: 'town', name: '마을', items: [], inside: null },
      { entry_id: 'inn', name: '여관', items: [], inside: 'town' },
      { entry_id: 'floor', name: '2층', items: [], inside: 'inn' },
      { entry_id: 'tower', name: '탑', items: [], inside: null },
    ],
    routes: [],
  } as unknown as TableMap;

  it('위치는 품은 장소부터 적고, 들고 나는 길에 이름이 있다', () => {
    expect(placePath(map, 'floor')).toBe('마을 > 여관 > 2층');
    expect(placePath(map, 'tower')).toBe('탑');
    expect(placePath(map, 'nowhere')).toBeNull();
    expect(wayStep(map, 'inn', 'floor')).toBe('in');
    expect(wayStep(map, 'inn', 'town')).toBe('out');
    expect(wayStep(map, 'town', 'tower')).toBeNull();
  });
});
