// web/apps/web/src/components/FollowButton.test.tsx
// 제작자 팔로우(#989). "만든 사람" 줄의 단추로 팔로우하고 끊으며(aria-pressed, 팔로워 수), 1,000명을 넘으면 까닭을 알린다.
// 로그인하지 않았으면 수와 로그인으로 가는 길만, 나 자신이면 수만 보인다. 마이페이지의 팔로잉은 펼쳐야 읽고 20명씩 더 읽는다.

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
  heart_count: 0,
  openings: [],
  character_modes: ['custom'],
  pregens: [],
  abilities: [],
  recommended_narration_model: null,
  references_allowed: true,
};
const FOLLOW = `/api/v1/notification/me/follows/${CREATOR}`;
const FOLLOWERS = `/api/v1/notification/creators/${CREATOR}/followers`;
const HEART = `/api/v1/game/listings/${SCENARIO_ID}/heart`;
const COMMON = {
  [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
  'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] }),
  'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
};

/** 서명은 보지 않으므로 가운데 조각(sub)만 맞춘 토큰 */
function tokenFor(sub: string): string {
  const payload = btoa(JSON.stringify({ sub })).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `h.${payload}.s`;
}

function signedIn(routes: Record<string, () => Response>, accessToken = 'a1') {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken)),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { count: 0 }),
    [`GET ${HEART}`]: () => json(200, { hearted: false, heart_count: 0 }),
    ...COMMON,
    ...routes,
  });
}

describe('팔로우', () => {
  it('누르면 팔로우하고 다시 누르면 끊는다', async () => {
    let state = { following: false, follower_count: 1234 };
    const { seen } = signedIn({
      [`GET ${FOLLOW}`]: () => json(200, state),
      [`PUT ${FOLLOW}`]: () => {
        state = { following: true, follower_count: 1235 };
        return json(200, state);
      },
      [`DELETE ${FOLLOW}`]: () => {
        state = { following: false, follower_count: 1234 };
        return json(200, state);
      },
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    const button = await screen.findByRole('button', { name: '팔로우' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText(/팔로워 1,234/)).toBeInTheDocument();
    await userEvent.click(button);
    expect(await screen.findByRole('button', { name: '팔로잉' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/팔로워 1,235/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '팔로잉' }));
    expect(await screen.findByRole('button', { name: '팔로우' })).toHaveAttribute('aria-pressed', 'false');
    expect(seen.filter((request) => request.url === FOLLOW).map((request) => request.method)).toEqual(['GET', 'PUT', 'DELETE']);
  });

  it('1,000명을 넘으면 그대로 두고 까닭을 알린다', async () => {
    signedIn({
      [`GET ${FOLLOW}`]: () => json(200, { following: false, follower_count: 3 }),
      [`PUT ${FOLLOW}`]: () => json(409, { detail: { code: 'follow_limit' } }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '팔로우' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('1,000명까지');
    expect(screen.getByRole('button', { name: '팔로우' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('로그인하지 않았으면 수와 로그인으로 가는 길만 보인다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET ${FOLLOWERS}`]: () => json(200, { follower_count: 7 }),
      ...COMMON,
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByRole('link', { name: '로그인하고 팔로우' })).toHaveAttribute('href', '/login');
    expect(screen.getByText(/팔로워 7/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '팔로우' })).not.toBeInTheDocument();
    expect(seen.some((request) => request.url === FOLLOW)).toBe(false);
  });

  it('내 작품이면 수만 보이고 단추가 없다', async () => {
    const { seen } = signedIn({ [`GET ${FOLLOWERS}`]: () => json(200, { follower_count: 9 }) }, tokenFor(CREATOR));
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByText(/팔로워 9/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '팔로우' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '로그인하고 팔로우' })).not.toBeInTheDocument();
    expect(seen.some((request) => request.url === FOLLOW)).toBe(false);
  });
});

describe('마이페이지의 팔로잉', () => {
  it('펼쳐야 읽고, 이름을 잇고, 20명씩 더 읽는다', async () => {
    const first = Array.from({ length: 20 }, (_, index) => ({
      creator_id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
      followed_at: '2026-11-04T00:00:00Z',
    }));
    const offsets: (string | null)[] = [];
    const { seen } = signedIn({
      'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
      'GET /api/v1/auth/me/bio': () => json(200, { bio: '' }),
      'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 0, limit: 5 }),
      'GET /api/v1/notification/me/follows': () => {
        const request = seen.at(-1);
        const offset = new URL(request?.url ?? '', 'http://x').searchParams.get('offset');
        offsets.push(offset);
        return offset === '0'
          ? json(200, { items: first, total: 21 })
          : json(200, { items: [{ creator_id: CREATOR, followed_at: '2026-11-01T00:00:00Z' }], total: 21 });
      },
    });
    renderApp('/me?tab=settings');

    const section = (await screen.findByRole('heading', { name: '팔로잉' })).closest('section') as HTMLElement;
    expect(seen.some((request) => request.url.startsWith('/api/v1/notification/me/follows'))).toBe(false);
    await userEvent.click(within(section).getByRole('button', { name: '팔로잉 보기' }));
    expect(await within(section).findByText('21명')).toBeInTheDocument();
    await userEvent.click(within(section).getByRole('button', { name: '더 보기' }));
    expect(await within(section).findByRole('link', { name: '이야기꾼' })).toHaveAttribute('href', `/creators/${CREATOR}`);
    expect(within(section).queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument();
    expect(offsets).toEqual(['0', '20']);
  });
});
