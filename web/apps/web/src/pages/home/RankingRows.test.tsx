// web/apps/web/src/pages/home/RankingRows.test.tsx
// 첫 화면의 이번 주 인기 판(#985). 서버마다 랭킹을 따로 부르고(보는 사람의 설정을 싣는다), 섞어서 1위부터 번호와 수를 붙이고,
// 칩으로 종류를 거르고, 한 서버가 답하지 않으면 읽은 것만 보이고 다시 시도를 둔다. 표시를 만드는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { setListingPreferences } from '../../api/listingPreferences';
import { fetchCharacterRanking, fetchScenarioRanking, fetchWorldRanking } from '../../api/rankings';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { boardLines, lineSubtitle, rankNumber, type RankingKind, type RankingLine } from './rankingBoardView';
import { rankBadges } from './rankingView';

const SCENARIO = {
  scenario_id: 's-1',
  creator_id: 'c-1',
  title: '잿빛 수도원',
  tagline: '종이 울리지 않는 밤',
  description: '',
  genre: 'horror',
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
};
const CHARACTER = {
  id: '00000000-0000-4000-8000-00000000c101',
  version: 1,
  name: '세라',
  tags: ['도서관'],
  genre: 'romance',
  rating: 'all',
  image_id: null,
  published_at: '2026-10-26T00:00:00Z',
};
const WORLD = {
  id: '00000000-0000-4000-8000-00000000b801',
  version: 1,
  name: '여름 학교',
  image_id: null,
  rating: 'all',
  genre: 'romance',
  tags: ['학원'],
  deadline_days: 30,
  published_at: '2026-10-26T00:00:00Z',
};
const EMPTY = { items: [], total: 0 };

function homeRoutes(overrides: Record<string, () => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'GET /api/v1/game/listings': () => json(200, EMPTY),
    'GET /api/v1/asset/listings/characters': () => json(200, EMPTY),
    'GET /api/v1/asset/listings/worlds': () => json(200, EMPTY),
    'GET /api/v1/game/banners': () => json(200, { items: [] }),
    'GET /api/v1/asset/banners': () => json(200, { items: [] }),
    'GET /api/v1/game/rankings/scenarios': () =>
      json(200, { recent_days: 7, items: [{ rank: 1, starts: 12_345, listing: SCENARIO }] }),
    'GET /api/v1/asset/rankings/characters': () =>
      json(200, { recent_days: 7, refreshed_at: '2026-11-04T03:00:00Z', items: [{ rank: 1, starts: 3, character: CHARACTER }] }),
    'GET /api/v1/asset/rankings/worlds': () =>
      json(200, { recent_days: 7, refreshed_at: '2026-11-04T03:00:00Z', items: [{ rank: 1, starts: 2, world: WORLD }] }),
    ...overrides,
  });
}

async function section(title: string): Promise<HTMLElement> {
  return (await screen.findByRole('heading', { name: title })).closest('section') as HTMLElement;
}

function paramsOf(seen: SeenRequest[], path: string): URLSearchParams | undefined {
  const request = seen.find((item) => item.url.split('?')[0] === path);
  return request ? new URL(request.url, 'http://localhost').searchParams : undefined;
}

afterEach(() => {
  setListingPreferences({});
});

describe('이번 주 인기 판', () => {
  it('세 서버의 랭킹을 섞어 시작한 수가 많은 것부터 번호와 수를 붙인다', async () => {
    homeRoutes();
    renderApp('/');

    const board = await section('이번 주 인기');
    const scenario = (await within(board).findByText('잿빛 수도원')).closest('a') as HTMLElement;
    expect(scenario).toHaveAttribute('href', '/trpg/scenarios/s-1');
    expect(within(scenario).getByText('이번 주 12.3K회')).toBeInTheDocument();
    expect(within(scenario).getByText('TRPG · 호러')).toBeInTheDocument();
    const character = (await within(board).findByText('세라')).closest('a') as HTMLElement;
    expect(character).toHaveAttribute('href', `/chat/characters/${CHARACTER.id}`);
    const world = (await within(board).findByText('여름 학교')).closest('a') as HTMLElement;
    expect(within(world).getByText('이번 주 2회')).toBeInTheDocument();
    const names = within(board).getAllByRole('link').map((link) => link.textContent);
    expect(names.map((name) => name?.slice(0, 2))).toEqual(['01', '02', '03']);
  });

  it('칩으로 한 종류만 본다', async () => {
    homeRoutes();
    renderApp('/');

    const board = await section('이번 주 인기');
    await within(board).findByText('세라');
    await userEvent.click(within(board).getByRole('button', { name: '스토리' }));
    expect(within(board).getByText('여름 학교')).toBeInTheDocument();
    expect(within(board).queryByText('세라')).toBeNull();
  });

  it('아무것도 없으면 빈 글을 보인다', async () => {
    const none = () => json(200, { recent_days: 7, refreshed_at: null, items: [] });
    homeRoutes({ 'GET /api/v1/game/rankings/scenarios': none, 'GET /api/v1/asset/rankings/characters': none, 'GET /api/v1/asset/rankings/worlds': none });
    renderApp('/');

    expect(await within(await section('이번 주 인기')).findByText('이번 주에 시작한 것이 아직 없습니다.')).toBeInTheDocument();
  });

  it('보는 사람의 설정을 싣는다', async () => {
    setListingPreferences({ hide_adult: 'true', orientation: 'female' });
    const { seen } = homeRoutes();

    await Promise.all([fetchScenarioRanking(6), fetchCharacterRanking(6), fetchWorldRanking(6)]);

    for (const path of ['/api/v1/game/rankings/scenarios', '/api/v1/asset/rankings/characters', '/api/v1/asset/rankings/worlds']) {
      const params = paramsOf(seen, path);
      expect([params?.get('hide_adult'), params?.get('orientation'), params?.get('limit')]).toEqual(['true', 'female', '6']);
    }
  });

  it('한 서버가 답하지 않으면 읽은 것만 보이고 다시 시도를 둔다', async () => {
    homeRoutes({ 'GET /api/v1/game/rankings/scenarios': () => json(503, { detail: 'down' }) });
    renderApp('/');

    const board = await section('이번 주 인기');
    expect(await within(board).findByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(within(board).getByText('세라')).toBeInTheDocument();
  });
});

describe('boardLines', () => {
  const line = (key: string, kind: RankingKind, starts: number): RankingLine => ({ key, kind, to: '/', title: key, genre: null, starts });
  it('섞어서 많은 것부터, 고른 종류만, 열 줄까지', () => {
    const groups = [[line('a', 'trpg', 5)], [line('b', 'character', 9), line('c', 'character', 1)], [line('d', 'story', 7)]];
    expect(boardLines(groups, null).map((item) => item.key)).toEqual(['b', 'd', 'a', 'c']);
    expect(boardLines(groups, 'character').map((item) => item.key)).toEqual(['b', 'c']);
    expect(boardLines(groups, null, 2)).toHaveLength(2);
    expect(rankNumber(0)).toBe('01');
    expect(lineSubtitle({ kind: 'story', genre: 'romance' })).toBe('스토리 · 로맨스');
  });
});

describe('rankBadges', () => {
  it('순위와 짧게 쓴 수다', () => {
    expect(rankBadges(1, 12)).toEqual(['1위', '이번 주 12회']);
    expect(rankBadges(3, 1500)).toEqual(['3위', '이번 주 1.5K회']);
  });
});
