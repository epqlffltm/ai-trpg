// web/apps/web/src/pages/home/Explore.test.tsx
// 탐색 화면 셋의 위(Stitch 12·16·17번). 그 서비스의 배너만(다른 서버의 배너는 부르지 않는다), 최신순이고 거르지 않았으면 이번 주 인기 줄,
// 그 아래 "전체 …"의 격자. TRPG 는 위쪽 오른편에 테이블 로비와 지나간 테이블. 인기순이거나 걸렀으면 인기 줄을 두지 않는다.

import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

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
const CHARACTER = { id: '00000000-0000-4000-8000-00000000c101', version: 1, name: '세라', tags: ['도서관'], genre: 'romance', rating: 'all', image_id: null, published_at: '2026-10-26T00:00:00Z' };
const WORLD = { id: '00000000-0000-4000-8000-00000000b801', version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'romance', tags: ['학원'], deadline_days: 30, published_at: '2026-10-26T00:00:00Z' };

function routes() {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }),
    'GET /api/v1/asset/listings/characters': () => json(200, { items: [CHARACTER], total: 1 }),
    'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
    'GET /api/v1/game/banners': () => json(200, { items: [{ id: 'g-1', listing: SCENARIO }] }),
    'GET /api/v1/asset/banners': () =>
      json(200, {
        items: [
          { id: 'a-1', kind: 'character', world: null, character: CHARACTER },
          { id: 'a-2', kind: 'world', character: null, world: WORLD },
        ],
      }),
    'GET /api/v1/game/rankings/scenarios': () => json(200, { recent_days: 7, items: [{ rank: 1, starts: 3, listing: SCENARIO }] }),
    'GET /api/v1/asset/rankings/characters': () => json(200, { recent_days: 7, refreshed_at: '2026-11-04T03:00:00Z', items: [{ rank: 1, starts: 3, character: CHARACTER }] }),
    'GET /api/v1/asset/rankings/worlds': () => json(200, { recent_days: 7, refreshed_at: '2026-11-04T03:00:00Z', items: [{ rank: 1, starts: 2, world: WORLD }] }),
  });
}

function called(seen: SeenRequest[], path: string): boolean {
  return seen.some((request) => request.url.split('?')[0] === path);
}

describe('탐색 화면의 위', () => {
  it('TRPG: TRPG 배너만, 이번 주 인기 줄, 전체 시나리오, 테이블 로비와 지나간 테이블', async () => {
    const { seen } = routes();
    renderApp('/trpg');

    const banner = await screen.findByRole('region', { name: '홍보' });
    expect(await within(banner).findByText('잿빛 수도원')).toBeInTheDocument();
    expect(within(banner).queryByText('1 / 2')).toBeNull();
    expect(called(seen, '/api/v1/asset/banners')).toBe(false);
    expect(await screen.findByRole('heading', { name: '이번 주 인기 시나리오' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '전체 시나리오' })).toBeInTheDocument();
    const links = within(screen.getByRole('navigation', { name: '테이블' }));
    expect(links.getByRole('link', { name: '테이블 로비' })).toHaveAttribute('href', '/trpg/lobby');
    expect(links.getByRole('link', { name: '지나간 테이블' })).toHaveAttribute('href', '/trpg/tables/past');
  });

  it('TRPG: 걸렀거나 인기순이면 인기 줄을 두지 않는다', async () => {
    const { seen } = routes();
    renderApp('/trpg?genre=horror');

    expect(await screen.findByRole('heading', { name: '전체 시나리오' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '이번 주 인기 시나리오' })).toBeNull();
    expect(called(seen, '/api/v1/game/rankings/scenarios')).toBe(false);
  });

  it('chat: chat 배너만, 이번 주 인기 캐릭터, 전체 캐릭터', async () => {
    const { seen } = routes();
    renderApp('/chat');

    const banner = await screen.findByRole('region', { name: '홍보' });
    expect(await within(banner).findByText('세라')).toBeInTheDocument();
    expect(within(banner).queryByText('여름 학교')).toBeNull();
    expect(called(seen, '/api/v1/game/banners')).toBe(false);
    expect(await screen.findByRole('heading', { name: '이번 주 인기 캐릭터' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '전체 캐릭터' })).toBeInTheDocument();
  });

  it('story: story 배너만, 이번 주 인기 세계관, 전체 세계관. 인기순이면 인기 줄을 두지 않는다', async () => {
    routes();
    const { unmount } = renderApp('/story');

    const banner = await screen.findByRole('region', { name: '홍보' });
    expect(await within(banner).findByText('여름 학교')).toBeInTheDocument();
    expect(within(banner).queryByText('세라')).toBeNull();
    expect(await screen.findByRole('heading', { name: '이번 주 인기 세계관' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '전체 세계관' })).toBeInTheDocument();
    unmount();

    renderApp('/story?sort=popular');
    expect(await screen.findByRole('heading', { name: '전체 세계관' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '이번 주 인기 세계관' })).toBeNull();
  });
});
