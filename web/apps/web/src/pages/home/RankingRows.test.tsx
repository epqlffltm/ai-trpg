// web/apps/web/src/pages/home/RankingRows.test.tsx
// 첫 화면의 이번 주 인기(#985). 서버마다 랭킹을 따로 부르고(보는 사람의 설정을 싣는다), 1위부터 순위와 수를 붙이고,
// 한 서버가 답하지 않으면 그 줄만 다시 시도를 보인다. 표시를 만드는 순수한 함수.

import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { setListingPreferences } from '../../api/listingPreferences';
import { fetchCharacterRanking, fetchScenarioRanking, fetchWorldRanking } from '../../api/rankings';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
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

describe('이번 주 인기', () => {
  it('서버마다 랭킹을 부르고 1위부터 순위와 수를 붙인다', async () => {
    homeRoutes();
    renderApp('/');

    const scenario = (await screen.findByText('잿빛 수도원')).closest('a') as HTMLElement;
    expect(within(scenario).getByText('1위')).toBeInTheDocument();
    expect(within(scenario).getByText('이번 주 12.3K회')).toBeInTheDocument();
    const character = (await within(await section('이번 주 인기 캐릭터')).findByText('세라')).closest('a') as HTMLElement;
    expect(character).toHaveAttribute('href', `/chat/characters/${CHARACTER.id}`);
    expect(within(character).getByText('이번 주 3회')).toBeInTheDocument();
    const world = (await within(await section('이번 주 인기 세계관')).findByText('여름 학교')).closest('a') as HTMLElement;
    expect(within(world).getByText('이번 주 2회')).toBeInTheDocument();
  });

  it('아무것도 없으면 그 줄은 빈 글을 보인다', async () => {
    homeRoutes({ 'GET /api/v1/asset/rankings/worlds': () => json(200, { recent_days: 7, refreshed_at: null, items: [] }) });
    renderApp('/');

    expect(await within(await section('이번 주 인기 세계관')).findByText('이번 주에 시작한 이야기가 아직 없습니다.')).toBeInTheDocument();
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

  it('한 서버가 답하지 않으면 그 줄만 다시 시도를 보인다', async () => {
    homeRoutes({ 'GET /api/v1/game/rankings/scenarios': () => json(503, { detail: 'down' }) });
    renderApp('/');

    expect(await within(await section('이번 주 인기 시나리오')).findByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(await within(await section('이번 주 인기 캐릭터')).findByText('세라')).toBeInTheDocument();
  });
});

describe('rankBadges', () => {
  it('순위와 짧게 쓴 수다', () => {
    expect(rankBadges(1, 12)).toEqual(['1위', '이번 주 12회']);
    expect(rankBadges(3, 1500)).toEqual(['3위', '이번 주 1.5K회']);
  });
});
