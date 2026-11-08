// web/apps/web/src/pages/trpg/room/stage/TableStage.test.tsx
// 테이블 방의 그림 창(#1163). 가장 많이 선 장소의 배경 위에 그곳의 인물을 세우고, 이번 닫힘의 사건이나 이룬 퀘스트가 있으면
// 컷신을 띄우는지, 그림이 하나도 없으면 그리지 않는지 본다. 장소, 인물, 컷신을 고르는 순수한 함수도 본다.

import { screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { SceneCast, TableDetail, TableEvent, TableMap } from '../../../../api/types';
import { installFakeFetch, json, tokens } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { event, ME, member, OTHER, round, roomRoutes, sheet, tableDetail } from '../../../../test/tableFixtures';
import { stageCutscene, stagePeople, stagePlace } from './tableStageView';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e5';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const GATE_BG = '00000000-0000-4000-8000-0000000000c1';
const GUARD_IMG = '00000000-0000-4000-8000-0000000000c2';
const FIRE_IMG = '00000000-0000-4000-8000-0000000000c3';
const THIRD = '00000000-0000-4000-8000-0000000000e3';

const MAP = {
  places: [
    { entry_id: 'p1', name: '성문', items: [], image_id: GATE_BG },
    { entry_id: 'p2', name: '부엌', items: [], image_id: null },
  ],
  routes: [],
} as unknown as TableMap;

const CAST = {
  round: 2,
  people: [
    { id: 'n1', name: '문지기', status: 'alive', injuries: [], items: [], place_id: 'p1', image_id: GUARD_IMG },
    { id: 'n2', name: '요리사', status: 'alive', injuries: [], items: [], place_id: 'p2', image_id: GUARD_IMG },
    { id: 'n3', name: '목소리', status: 'alive', injuries: [], items: [], place_id: null, image_id: null },
  ],
  monsters: [],
} as unknown as SceneCast;

function at(placeId: string | null, extra: Record<string, unknown> = {}) {
  return member(extra.user_id as string, { character: { name: '렌', description: '' }, sheet: sheet({ place_id: placeId }), ...extra });
}

function members(...list: ReturnType<typeof member>[]): TableDetail['members'] {
  return list as unknown as TableDetail['members'];
}

function events(list: ReturnType<typeof event>[]): TableEvent[] {
  return list as unknown as TableEvent[];
}

function open(eventItems: ReturnType<typeof event>[] = []) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, tableDetail(TABLE_ID, { status: 'playing', map: MAP, members: [at('p1', { user_id: ME, is_host: true })] })),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      [`GET ${BASE}/rounds/current/people`]: () => json(200, CAST),
      [`GET ${BASE}/events`]: () => json(200, { items: eventItems, last_sequence: eventItems.length }),
      [`GET ${BASE}/portraits/${GATE_BG}/image`]: () => new Response('png', { status: 200 }),
      [`GET ${BASE}/portraits/${GUARD_IMG}/image`]: () => new Response('png', { status: 200 }),
      [`GET ${BASE}/portraits/${FIRE_IMG}/image`]: () => new Response('png', { status: 200 }),
    }),
  });
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:picture'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('테이블 방의 그림 창', () => {
  it('선 장소의 배경 위에 그곳의 그림이 있는 인물을 세운다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const stage = within(await screen.findByRole('figure', { name: '그림 창' }));
    expect(await stage.findByRole('img', { name: '성문' })).toHaveAttribute('src', 'blob:picture');
    const people = within(stage.getByRole('region', { name: '장면의 인물' }));
    expect(await people.findByRole('img', { name: '문지기' })).toBeInTheDocument();
    // 다른 곳의 인물과 그림이 없는 인물은 세우지 않는다
    expect(people.queryByText('요리사')).toBeNull();
    expect(people.queryByText('목소리')).toBeNull();
  });

  it('이번 닫힘에 일어난 사건의 그림이 있으면 배경 대신 컷신을 띄운다', async () => {
    open([
      event(1, 'round_opened', { number: 1 }, { action_group_id: 'g0' }),
      event(2, 'happening_occurred', { round: 1, entry_id: 'e1', name: '종탑의 불', moves: [], image_id: FIRE_IMG }, { action_group_id: 'g1' }),
      event(3, 'round_closed', { number: 1 }, { action_group_id: 'g1' }),
      event(4, 'round_opened', { number: 2 }, { action_group_id: 'g1' }),
    ]);
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const stage = within(await screen.findByRole('figure', { name: '그림 창' }));
    expect(await stage.findByRole('img', { name: '종탑의 불' })).toBeInTheDocument();
    expect(stage.getByText('종탑의 불')).toBeInTheDocument();
    expect(stage.queryByRole('region', { name: '장면의 인물' })).toBeNull();
  });

  it('그림을 붙이지 않은 판이면 그림 창이 없다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
      ...roomRoutes(TABLE_ID, {
        [`GET ${BASE}`]: () => json(200, tableDetail(TABLE_ID, { status: 'playing', members: [at(null, { user_id: ME, is_host: true })] })),
        [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
        [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('region', { name: '라운드' })).toBeInTheDocument();
    expect(screen.queryByRole('figure', { name: '그림 창' })).toBeNull();
  });
});

describe('그림 창이 고르는 것', () => {
  it('장소: 가장 많이 선 곳, 같으면 방장의 곳, 방장이 그 안에 없으면 맵의 차례가 앞인 곳', () => {
    expect(stagePlace(MAP, members(at('p2', { user_id: ME, is_host: true }), at('p1', { user_id: OTHER }), at('p1', { user_id: THIRD })))?.id).toBe('p1');
    expect(stagePlace(MAP, members(at('p1', { user_id: ME }), at('p2', { user_id: OTHER, is_host: true })))?.id).toBe('p2');
    expect(stagePlace(MAP, members(at('p2', { user_id: ME }), at('p1', { user_id: OTHER }), at(null, { user_id: THIRD, is_host: true })))?.id).toBe('p1');
    expect(stagePlace(MAP, members(at(null, { user_id: ME })))).toBeNull();
    expect(stagePlace(null, members(at('p1', { user_id: ME })))).toBeNull();
  });

  it('인물: 그림이 있고 죽지 않았으며 그 장소에 있거나 자리가 없는 인물', () => {
    const dead = { ...CAST, people: [{ ...CAST.people[0], status: 'dead' }] } as unknown as SceneCast;
    expect(stagePeople(CAST, 'p1').map((person) => person.name)).toEqual(['문지기']);
    expect(stagePeople(CAST, 'p2').map((person) => person.name)).toEqual(['요리사']);
    expect(stagePeople(dead, 'p1')).toEqual([]);
    expect(stagePeople(undefined, 'p1')).toEqual([]);
  });

  it('컷신: 마지막 닫힘의 묶음부터 본다. 이룬 퀘스트도 컷신이고, 다음 닫힘이 오면 지난 것은 사라진다', () => {
    const fire = event(2, 'happening_occurred', { name: '종탑의 불', image_id: FIRE_IMG }, { action_group_id: 'g1' });
    const closeOne = event(3, 'round_closed', { number: 1 }, { action_group_id: 'g1' });
    expect(stageCutscene(events([fire, closeOne]))).toEqual({ title: '종탑의 불', imageId: FIRE_IMG });

    const closeTwo = event(5, 'round_closed', { number: 2 }, { action_group_id: 'g2' });
    expect(stageCutscene(events([fire, closeOne, closeTwo]))).toBeNull();

    const won = event(4, 'quest_changed', { name: '도둑 잡기', status: 'succeeded', image_id: GUARD_IMG }, { action_group_id: 'g2' });
    const failed = event(4, 'quest_changed', { name: '도둑 잡기', status: 'failed', image_id: GUARD_IMG }, { action_group_id: 'g2' });
    expect(stageCutscene(events([fire, closeOne, won, closeTwo]))).toEqual({ title: '도둑 잡기', imageId: GUARD_IMG });
    expect(stageCutscene(events([fire, closeOne, failed, closeTwo]))).toBeNull();
    // 그림을 붙이지 않은 사건(image_id null)은 컷신이 아니다
    expect(stageCutscene(events([event(1, 'happening_occurred', { name: '비', image_id: null })]))).toBeNull();
  });

  it('컷신: 되돌린 라운드의 사건은 띄우지 않는다', () => {
    const fire = event(2, 'happening_occurred', { name: '종탑의 불', image_id: FIRE_IMG }, { action_group_id: 'g1' });
    const close = event(3, 'round_closed', { number: 1 }, { action_group_id: 'g1' });
    const reverted = event(4, 'round_reverted', { group: 'g1' }, { action_group_id: 'g9' });
    expect(stageCutscene(events([fire, close, reverted]))).toBeNull();
  });
});
