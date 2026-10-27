// web/apps/web/src/pages/home/HomePage.test.tsx
// 첫 화면(A1): 줄마다 따로 실패하고, 로그인 전에는 이어하기를 부르지 않으며 토큰을 싣지 않는다. story 이어하기는 진행 한 줄을 보인다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const SCENARIO = {
  scenario_id: 's-1',
  creator_id: 'c-1',
  title: '잿빛 수도원',
  tagline: '종이 울리지 않는 밤',
  description: '',
  genres: ['호러'],
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
};
const TABLE = {
  id: 't-1',
  scenario_id: 's-1',
  title: '목요일 모임',
  status: 'playing',
  rating: 'all',
  capacity: 4,
  member_count: 3,
};

function section(title: string): HTMLElement {
  const heading = screen.getByRole('heading', { name: title });
  return heading.closest('section') as HTMLElement;
}

describe('HomePage', () => {
  it('로그인 전에는 공개 목록만 부르고 Authorization 을 보내지 않는다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () =>
        json(200, { items: [{ id: '00000000-0000-4000-8000-00000000b801', version: 1, name: '여름 학교', image_id: null, rating: 'all', tags: ['학원'], deadline_days: 30, published_at: '2026-10-26T00:00:00Z' }], total: 1 }),
    });
    renderApp('/');

    expect(await screen.findByText('잿빛 수도원')).toBeInTheDocument();
    const world = (await within(section('새로 공개된 세계관')).findByText('여름 학교')).closest('a') as HTMLElement;
    expect(world).toHaveAttribute('href', '/story/worlds/00000000-0000-4000-8000-00000000b801');
    expect(within(world).getByText('30일')).toBeInTheDocument();
    expect(screen.queryByText('TRPG 이어하기')).not.toBeInTheDocument();
    expect(seen.every((request) => !request.headers.has('Authorization'))).toBe(true);
  });

  it('한 서버가 답하지 않으면 그 줄만 다시 시도를 보이고 나머지는 그대로다', async () => {
    let charactersFail = true;
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }),
      'GET /api/v1/game/tables': () => json(200, { items: [TABLE], total: 1 }),
      'GET /api/v1/chat/conversations': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/story/conversations': () =>
        json(200, {
          items: [
            {
              id: '00000000-0000-4000-8000-00000000aa71',
              title: '여름 학교의 봄',
              world: { id: '00000000-0000-4000-8000-00000000b801', version: 1, name: '여름 학교', image_id: null, rating: 'all' },
              model: null,
              created_at: '2026-10-26T00:00:00Z',
              updated_at: '2026-10-26T00:00:00Z',
              progress: { day: 18, slot: 'evening', deadline_days: 30, ending: null, ending_name: null, epilogue: false },
            },
          ],
          total: 1,
        }),
      'GET /api/v1/asset/listings/characters': () =>
        charactersFail ? json(503, { detail: '잠시' }) : json(200, { items: [], total: 0 }),
    });
    renderApp('/');

    const characters = await screen.findByRole('heading', { name: '새로 공개된 캐릭터' });
    const retry = await within(characters.closest('section') as HTMLElement).findByRole('button', { name: '다시 시도' });
    expect(await within(section('TRPG 이어하기')).findByText('목요일 모임')).toBeInTheDocument();
    expect(within(section('TRPG 이어하기')).getByText('3/4명')).toBeInTheDocument();
    const story = (await within(section('story 이어하기')).findByText('여름 학교의 봄')).closest('a') as HTMLElement;
    expect(story).toHaveAttribute('href', '/story/sessions/00000000-0000-4000-8000-00000000aa71');
    expect(within(story).getByText('18일째 · D-12')).toBeInTheDocument();
    expect(within(section('새로 공개된 시나리오')).getByText('잿빛 수도원')).toBeInTheDocument();

    charactersFail = false;
    await userEvent.click(retry);
    expect(await within(section('새로 공개된 캐릭터')).findByText('아직 공개된 캐릭터가 없습니다.')).toBeInTheDocument();
  });
});
