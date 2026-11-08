// web/apps/web/src/components/HeartButton.test.tsx
// 관심(하트, #989). 소개의 단추로 두고 거두며(aria-pressed, 수), 로그인하지 않았으면 수와 로그인으로 가는 길만 보인다.
// 바꾸지 못하면 알린다. 내 관심 작품(/me/hearts)은 서버마다 따로 부르고 서비스마다 묶는다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { SCENARIO_ID } from '../test/scenarioFixtures';

const CREATOR = '00000000-0000-4000-8000-0000000000c9';
const DETAIL = {
  scenario_id: SCENARIO_ID,
  creator_id: CREATOR,
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
  heart_count: 1234,
  openings: [],
  character_modes: ['custom'],
  pregens: [],
  abilities: [],
  recommended_narration_model: null,
  references_allowed: true,
};
const WORLD = {
  id: '00000000-0000-4000-8000-00000000b801',
  creator_id: CREATOR,
  version: 1,
  name: '여름 학교',
  image_id: null,
  rating: 'all',
  genre: 'romance',
  tags: [],
  deadline_days: null,
  published_at: '2026-10-26T00:00:00Z',
  heart_count: 2,
};
const HEART = `/api/v1/game/listings/${SCENARIO_ID}/heart`;
const COMMON = {
  [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, { items: [], players: 0 }),
  [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
  'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] }),
  'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
};

function signedIn(routes: Record<string, () => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { count: 0 }),
    ...COMMON,
    ...routes,
  });
}

describe('관심', () => {
  it('누르면 두고 다시 누르면 거둔다', async () => {
    let state = { hearted: false, heart_count: 1234 };
    const { seen } = signedIn({
      [`GET ${HEART}`]: () => json(200, state),
      [`PUT ${HEART}`]: () => {
        state = { hearted: true, heart_count: 1235 };
        return json(200, state);
      },
      [`DELETE ${HEART}`]: () => {
        state = { hearted: false, heart_count: 1234 };
        return json(200, state);
      },
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    const button = await screen.findByRole('button', { name: /관심 1,234/ });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(button);
    expect(await screen.findByRole('button', { name: /관심 1,235/ })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: /관심 1,235/ }));
    expect(await screen.findByRole('button', { name: /관심 1,234/ })).toHaveAttribute('aria-pressed', 'false');
    expect(seen.filter((request) => request.url === HEART).map((request) => request.method)).toEqual(['GET', 'PUT', 'DELETE']);
  });

  it('바꾸지 못하면 그대로 두고 알린다', async () => {
    signedIn({
      [`GET ${HEART}`]: () => json(200, { hearted: false, heart_count: 1234 }),
      [`PUT ${HEART}`]: () => json(503, { detail: 'down' }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: /관심 1,234/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('바꾸지 못했습니다');
    expect(screen.getByRole('button', { name: /관심 1,234/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('로그인하지 않았으면 수와 로그인으로 가는 길만 보인다', async () => {
    const { seen } = installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }), ...COMMON });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByRole('link', { name: '로그인하고 관심 두기' })).toHaveAttribute('href', '/login');
    expect(screen.getByText(/♡ 1,234/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /관심/ })).not.toBeInTheDocument();
    expect(seen.some((request) => request.url === HEART)).toBe(false);
  });
});

describe('내 관심 작품', () => {
  it('서버마다 따로 부르고 서비스마다 묶는다', async () => {
    signedIn({
      'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
      'GET /api/v1/game/listings/hearted': () => json(200, { items: [DETAIL], total: 1 }),
      'GET /api/v1/asset/listings/characters/hearted': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds/hearted': () => json(200, { items: [WORLD], total: 1 }),
    });
    renderApp('/me/hearts');

    const scenarios = (await screen.findByRole('heading', { name: 'TRPG 시나리오 1개' })).closest('section') as HTMLElement;
    expect(within(scenarios).getByText('잿빛 수도원').closest('a')).toHaveAttribute('href', `/trpg/scenarios/${SCENARIO_ID}`);
    const worlds = (await screen.findByRole('heading', { name: 'story 세계관 1개' })).closest('section') as HTMLElement;
    expect(within(worlds).getByText('여름 학교')).toBeInTheDocument();
    const characters = (await screen.findByRole('heading', { name: 'chat 캐릭터 0개' })).closest('section') as HTMLElement;
    expect(within(characters).getByText('관심을 둔 캐릭터가 없습니다.')).toBeInTheDocument();
  });
});
