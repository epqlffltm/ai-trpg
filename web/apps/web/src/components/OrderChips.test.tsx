// web/apps/web/src/components/OrderChips.test.tsx
// 공개 목록의 차례(#985)와 카드의 수(#985, #989). 시나리오·캐릭터·세계관의 목록에서 인기순을 고르면 주소와 요청에 sort=popular 가
// 실리고, 카드에 시작한 수와 관심의 수가 붙는다(0 이면 붙지 않는다).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';

const SCENARIO = {
  scenario_id: 's-1',
  creator_id: '00000000-0000-4000-8000-0000000000c9',
  title: '잿빛 수도원',
  tagline: '',
  description: '',
  genre: 'horror',
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
  heart_count: 12,
  start_count: 12_345,
};
const CHARACTER = {
  id: '00000000-0000-4000-8000-00000000c101',
  creator_id: '00000000-0000-4000-8000-0000000000c9',
  version: 1,
  name: '세라',
  tags: [],
  genre: 'romance',
  rating: 'all',
  image_id: null,
  published_at: '2026-10-26T00:00:00Z',
  heart_count: 0,
  start_count: 1500,
};
const WORLD = {
  id: '00000000-0000-4000-8000-00000000b801',
  creator_id: '00000000-0000-4000-8000-0000000000c9',
  version: 1,
  name: '여름 학교',
  image_id: null,
  rating: 'all',
  genre: 'romance',
  tags: [],
  deadline_days: null,
  published_at: '2026-10-26T00:00:00Z',
  heart_count: 3,
  start_count: 0,
};

function sorts(seen: SeenRequest[], path: string): (string | null)[] {
  return seen
    .filter((request) => request.url.split('?')[0] === path)
    .map((request) => new URL(request.url, 'http://localhost').searchParams.get('sort'));
}

function signedOut(routes: Record<string, () => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
    ...routes,
  });
}

describe('차례와 카드의 수', () => {
  it('시나리오: 인기순을 고르면 sort=popular 로 다시 부르고, 카드에 연 테이블과 관심의 수를 붙인다', async () => {
    const { seen } = signedOut({ 'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }) });
    renderApp('/trpg');

    const card = (await screen.findByText('잿빛 수도원')).closest('a') as HTMLElement;
    expect(within(card).getByText('테이블 12.3K')).toBeInTheDocument();
    expect(within(card).getByText('♥ 12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '최신순' })).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(screen.getByRole('button', { name: '인기순' }));

    expect(await screen.findByRole('button', { name: '인기순' })).toHaveAttribute('aria-pressed', 'true');
    await screen.findByText('잿빛 수도원');
    expect(sorts(seen, '/api/v1/game/listings')).toEqual([null, 'popular']);
  });

  it('캐릭터: 주소의 sort=popular 로 열고, 관심이 0 이면 그 수는 붙이지 않는다', async () => {
    const { seen } = signedOut({ 'GET /api/v1/asset/listings/characters': () => json(200, { items: [CHARACTER], total: 1 }) });
    renderApp('/chat?sort=popular');

    const card = (await screen.findByText('세라')).closest('a') as HTMLElement;
    expect(within(card).getByText('대화 1.5K')).toBeInTheDocument();
    expect(within(card).queryByText(/♥/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '인기순' })).toHaveAttribute('aria-pressed', 'true');
    expect(sorts(seen, '/api/v1/asset/listings/characters')).toEqual(['popular']);
  });

  it('세계관: 인기순을 골랐다가 최신순으로 돌아간다', async () => {
    const { seen } = signedOut({ 'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }) });
    renderApp('/story');

    const card = (await screen.findByText('여름 학교')).closest('a') as HTMLElement;
    expect(within(card).getByText('♥ 3')).toBeInTheDocument();
    expect(within(card).queryByText(/이야기/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '인기순' }));
    await screen.findByRole('button', { name: '인기순', pressed: true });
    await userEvent.click(screen.getByRole('button', { name: '최신순' }));
    await screen.findByRole('button', { name: '최신순', pressed: true });

    expect(sorts(seen, '/api/v1/asset/listings/worlds')).toEqual([null, 'popular', null]);
  });
});
