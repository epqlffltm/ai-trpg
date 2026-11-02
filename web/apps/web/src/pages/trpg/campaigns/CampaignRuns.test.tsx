// web/apps/web/src/pages/trpg/campaigns/CampaignRuns.test.tsx
// 캠페인의 플레이(#481 B). 테이블 방: 편 표시와 넘겨받은 캐릭터, 편이 끝나면 방장은 같은 정원으로 다음 편을 열고 그리 가며,
// 다른 사람은 기다리다 들어간다(이미 앉았으면 그리 간다). 캠페인이 아닌 테이블에는 보이지 않는다.
// 로비 옆의 내 캠페인. 만들기의 플레이 시작(게시한 판이 있어야). 다음에 할 일과 글의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { CampaignCarry, CampaignRun } from '../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, OTHER, roomRoutes, tableDetail } from '../../../test/tableFixtures';
import { waitsForNext } from './runQueries';
import { carryLine, episodeLabel, nextStep } from './runView';

const RUNS = '/api/v1/game/campaign-runs';
const RUN_ID = '00000000-0000-4000-8000-0000000000f1';
const FIRST = '00000000-0000-4000-8000-0000000000b1';
const SECOND = '00000000-0000-4000-8000-0000000000b2';
const CAMPAIGN_ID = '00000000-0000-4000-8000-0000000000d1';
const AT = '2026-11-02T00:00:00Z';

const CARRY: CampaignCarry = {
  character_name: '기사',
  character_description: '',
  pregen: false,
  abilities: { str: 13 },
  max_hp: 15,
  xp: 150,
  points: 1,
  skills: [],
  resistances: [],
  money: 40,
  items: [{ entry_id: '00000000-0000-4000-8000-0000000000c1', count: 2 }],
};

function run(tables: [string | null, string | null], extra: Partial<CampaignRun> = {}): CampaignRun {
  return {
    id: RUN_ID,
    campaign_id: CAMPAIGN_ID,
    title: '추격전',
    version: 1,
    host_id: ME,
    status: 'playing',
    position: tables[1] ? 1 : 0,
    episodes: [
      { position: 0, title: '고성', scenario_id: 'a', version: 1, table_id: tables[0] },
      { position: 1, title: '지하 묘지', scenario_id: 'b', version: 1, table_id: tables[1] },
    ],
    quest_results: [],
    my_carry: null,
    created_at: AT,
    ended_at: null,
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function open(routes: Routes) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/game/tables': () => json(200, { items: [], total: 0 }),
    ...roomRoutes(SECOND, { [`GET /api/v1/game/tables/${SECOND}`]: () => json(200, tableDetail(SECOND, { title: '2편 모임' })) }),
    ...roomRoutes(FIRST),
    ...routes,
  });
}

function ended(id: string, extra: Record<string, unknown> = {}) {
  return () => json(200, tableDetail(id, { status: 'ended', capacity: 2, started_at: AT, ended_at: AT, ...extra }));
}

function sent(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('테이블 방의 캠페인', () => {
  it('모집 중에는 편과 넘겨받은 캐릭터를 보인다', async () => {
    open({
      [`GET /api/v1/game/tables/${SECOND}`]: () => json(200, tableDetail(SECOND)),
      [`GET ${RUNS}/of-table/${SECOND}`]: () => json(200, run([FIRST, SECOND], { my_carry: CARRY })),
    });
    renderApp(`/trpg/tables/${SECOND}`);

    const panel = within(await screen.findByRole('region', { name: '캠페인 「추격전」' }));
    expect(panel.getByText('2편: 지하 묘지 (2/2)')).toBeInTheDocument();
    expect(panel.getByText(/넘겨받은 캐릭터: 기사 · 경험치 150/)).toBeInTheDocument();
  });

  it('편이 끝나면 방장은 같은 정원으로 다음 편을 열고 그 테이블로 간다', async () => {
    const { seen } = open({
      [`GET /api/v1/game/tables/${FIRST}`]: ended(FIRST),
      [`GET ${RUNS}/of-table/${FIRST}`]: () => json(200, run([FIRST, null])),
      [`POST ${RUNS}/${RUN_ID}/next`]: () => json(201, run([FIRST, SECOND])),
    });
    renderApp(`/trpg/tables/${FIRST}`);

    const panel = within(await screen.findByRole('region', { name: '캠페인 「추격전」' }));
    expect(panel.getByText('1편: 고성 (1/2)')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '다음 편 열기' }));

    expect(await screen.findByRole('heading', { name: '2편 모임', level: 1 })).toBeInTheDocument();
    expect(sent(seen, 'POST', `${RUNS}/${RUN_ID}/next`)[0]?.body).toEqual({ capacity: 2 });
  });

  it('방장이 아니면 기다렸다가, 다음 편이 열리면 들어간다. 이미 앉아 있으면 그리 간다', async () => {
    const { seen } = open({
      [`GET /api/v1/game/tables/${FIRST}`]: ended(FIRST, { host_id: OTHER }),
      [`GET ${RUNS}/of-table/${FIRST}`]: () => json(200, run([FIRST, SECOND], { host_id: OTHER })),
      [`POST ${RUNS}/${RUN_ID}/join`]: () => json(409, { detail: '이미 앉아 있습니다.', reason: 'already_seated' }),
    });
    renderApp(`/trpg/tables/${FIRST}`);

    const panel = within(await screen.findByRole('region', { name: '캠페인 「추격전」' }));
    expect(panel.queryByRole('button', { name: '다음 편 열기' })).toBeNull();
    await userEvent.click(panel.getByRole('button', { name: '다음 편에 들어가기' }));

    expect(await screen.findByRole('heading', { name: '2편 모임', level: 1 })).toBeInTheDocument();
    expect(sent(seen, 'POST', `${RUNS}/${RUN_ID}/join`)).toHaveLength(1);
  });

  it('캠페인의 테이블이 아니면 보이지 않는다', async () => {
    open({ [`GET ${RUNS}/of-table/${FIRST}`]: () => json(200, null) });
    renderApp(`/trpg/tables/${FIRST}`);

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    await vi.waitFor(() => expect(screen.queryByText(/캠페인 「/)).toBeNull());
  });
});

describe('내 캠페인과 플레이 시작', () => {
  it('로비 옆에 내 캠페인과 지금 편을 보이고, 지금 편의 테이블로 간다', async () => {
    open({
      'GET /api/v1/game/tables/lobby': () => json(200, { items: [], total: 0 }),
      [`GET ${RUNS}`]: () =>
        json(200, {
          items: [
            {
              id: RUN_ID,
              campaign_id: CAMPAIGN_ID,
              title: '추격전',
              host_id: ME,
              status: 'playing',
              position: 1,
              episode_count: 2,
              episode_title: '지하 묘지',
              table_id: SECOND,
              created_at: AT,
              ended_at: null,
            },
          ],
          total: 1,
        }),
    });
    renderApp('/trpg/lobby');

    const list = within(await screen.findByRole('list', { name: '내 캠페인' }));
    expect(list.getByRole('link', { name: '추격전' })).toHaveAttribute('href', `/trpg/tables/${SECOND}`);
    expect(list.getByText('2편: 지하 묘지 (2/2)')).toBeInTheDocument();
  });

  it('게시한 판이 있으면 고른 정원으로 플레이를 시작하고 첫 편의 테이블로 간다', async () => {
    const CAMPAIGNS = '/api/v1/game/campaigns';
    const { seen } = open({
      'GET /api/v1/game/scenarios': () => json(200, { items: [], total: 0 }),
      [`GET ${CAMPAIGNS}/${CAMPAIGN_ID}`]: () =>
        json(200, {
          id: CAMPAIGN_ID,
          title: '추격전',
          description: '',
          visibility: 'private',
          rating: 'all',
          episode_count: 0,
          episodes: [],
          created_at: AT,
          updated_at: AT,
        }),
      [`GET ${CAMPAIGNS}/${CAMPAIGN_ID}/publish-check`]: () => json(200, { ready: true, problems: [], warnings: [] }),
      [`GET ${CAMPAIGNS}/${CAMPAIGN_ID}/versions`]: () => json(200, [{ id: 'v2', number: 2, note: '', created_at: AT }]),
      [`POST ${RUNS}`]: () => json(201, run([FIRST, null])),
    });
    renderApp(`/trpg/studio/campaigns/${CAMPAIGN_ID}`);

    const section = within(await screen.findByRole('region', { name: '플레이 시작' }));
    expect(await section.findByText(/마지막으로 게시한 2판으로/)).toBeInTheDocument();
    await userEvent.click(section.getByRole('button', { name: '2명' }));
    await userEvent.click(section.getByRole('button', { name: '플레이 시작' }));

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(sent(seen, 'POST', RUNS)[0]?.body).toEqual({ campaign_id: CAMPAIGN_ID, table: { capacity: 2 } });
  });
});

describe('캠페인의 플레이의 순수한 함수', () => {
  it('다음에 할 일: 끝나지 않았으면 없고, 방장은 열고, 다른 사람은 기다리고, 열렸으면 들어가고, 마지막이면 마친다', () => {
    expect(nextStep(run([FIRST, null]), FIRST, false, ME)).toBeNull();
    expect(nextStep(run([FIRST, null]), FIRST, true, ME)).toEqual({ kind: 'open' });
    expect(nextStep(run([FIRST, null]), FIRST, true, OTHER)).toEqual({ kind: 'wait' });
    expect(nextStep(run([FIRST, SECOND]), FIRST, true, OTHER)).toEqual({ kind: 'enter', tableId: SECOND });
    expect(nextStep(run([FIRST, SECOND]), SECOND, true, ME)).toEqual({ kind: 'finished' });
    expect(nextStep(run([FIRST, SECOND]), 'elsewhere', true, ME)).toBeNull();
  });

  it('다음 편이 열리기를 기다릴 때만 다시 읽는다', () => {
    expect(waitsForNext(run([FIRST, null]), FIRST, true)).toBe(true);
    expect(waitsForNext(run([FIRST, null]), FIRST, false)).toBe(false);
    expect(waitsForNext(run([FIRST, SECOND]), FIRST, true)).toBe(false);
    expect(waitsForNext(run([FIRST, SECOND]), SECOND, true)).toBe(false);
    expect(waitsForNext(null, FIRST, true)).toBe(false);
  });

  it('편과 넘긴 캐릭터의 글', () => {
    expect(episodeLabel(0, '고성', 3)).toBe('1편: 고성 (1/3)');
    expect(carryLine(CARRY)).toBe('기사 · 경험치 150 · 최대 HP 15 · 돈 40 · 쓸 점수 1 · 소지품 1가지');
    expect(carryLine({ ...CARRY, points: 0, items: [] })).toBe('기사 · 경험치 150 · 최대 HP 15 · 돈 40 · 소지품 없음');
  });
});
