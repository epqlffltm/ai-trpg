// web/apps/web/src/pages/story/StoryWorldAchievements.test.tsx
// 세계관 소개(D1)의 업적(docs/architecture/achievements.md 의 "story"). 판의 차례로 이름, 받는 법, 달성률을 보인다.
// 숨긴 업적은 받기 전에 가리고, 받았으면 받은 때의 이름이 보인다. 로그인하지 않으면 달성률만 읽는다.
// 업적이 없으면 칸이 없고 story 서버에 묻지 않는다. 달성률을 읽지 못하면 다시 시도를 둔다. 순수한 함수(storyAchievementView.ts).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyAchievementItems } from './storyAchievementView';

const WORLD = '00000000-0000-4000-8000-00000000b902';
const AT = '2026-11-09T03:00:00Z';

const ACHIEVEMENTS = [
  { id: 'walk', hidden: false, name: '공원 산책', description: '공원에 갔다', image_id: null },
  { id: 'secret', hidden: true, name: null, description: null, image_id: null },
  { id: 'kept', hidden: true, name: null, description: null, image_id: null },
];
const DETAIL = {
  id: WORLD,
  version: 1,
  name: '여름 학교',
  image_id: null,
  rating: 'all',
  tags: [],
  deadline_days: null,
  published_at: AT,
  intro_html: '',
  after_ending: 'end',
  ending_count: 0,
  cast: [],
  achievements: ACHIEVEMENTS,
};
const RATES = { players: 8, items: [{ achievement_id: 'walk', earned_count: 2 }, { achievement_id: 'secret', earned_count: 1 }] };
const MINE = { items: [{ achievement_id: 'secret', name: '비밀의 방', description: '숨은 방을 찾았다', image_id: null, earned_at: AT, conversation_id: null }] };

function signedOut(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, DETAIL),
    'GET /api/v1/story/achievements/rates': () => json(200, RATES),
    ...routes,
  });
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, DETAIL),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/story/endings': () => json(200, { items: [] }),
    'GET /api/v1/story/achievements/rates': () => json(200, RATES),
    'GET /api/v1/story/achievements': () => json(200, MINE),
    ...routes,
  });
}

async function achievementList() {
  return within(await screen.findByRole('list', { name: '업적' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('세계관 소개의 업적', () => {
  it('로그인하지 않으면 업적과 달성률을 보이고 숨긴 업적은 가린다', async () => {
    const { seen } = signedOut();
    renderApp(`/story/worlds/${WORLD}`);

    const list = await achievementList();
    expect(await list.findByText('플레이한 8명 중 2명(25%)')).toBeInTheDocument();
    expect(list.getByText('공원 산책')).toBeInTheDocument();
    expect(list.getByText('공원에 갔다')).toBeInTheDocument();
    expect(list.getAllByText('숨긴 업적')).toHaveLength(2);
    expect(list.getAllByText('받으면 이름과 받는 법이 보입니다.')).toHaveLength(2);
    expect(screen.queryByText(/내가 받은 업적/)).toBeNull();
    expect(seen.some((request) => request.url.startsWith('/api/v1/story/achievements?'))).toBe(false);
  });

  it('로그인했으면 받은 수와 받은 날을 보이고, 받은 숨긴 업적은 받은 때의 이름이다', async () => {
    signedIn();
    renderApp(`/story/worlds/${WORLD}`);

    expect(await screen.findByText('내가 받은 업적 1 / 3개')).toBeInTheDocument();
    const list = await achievementList();
    expect(list.getByText('비밀의 방')).toBeInTheDocument();
    expect(list.getByText('숨은 방을 찾았다')).toBeInTheDocument();
    expect(list.getAllByText('숨긴 업적')).toHaveLength(1);
    const walk = list.getByText('공원 산책').closest('li') as HTMLElement;
    expect(walk).toHaveClass('achievement-item--locked');
    expect((list.getByText('비밀의 방').closest('li') as HTMLElement).className).toBe('achievement-item');
  });

  it('달성률을 읽지 못하면 다시 시도한다', async () => {
    let fail = true;
    signedOut({ 'GET /api/v1/story/achievements/rates': () => (fail ? json(503, { detail: 'down' }) : json(200, RATES)) });
    renderApp(`/story/worlds/${WORLD}`);

    const retry = await screen.findByRole('button', { name: '다시 시도' }, { timeout: 5000 });
    expect(screen.getByText(/달성률을 불러오지 못했습니다/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(retry);
    expect(await screen.findByText('플레이한 8명 중 2명(25%)')).toBeInTheDocument();
  });

  it('업적이 없는 세계관이면 칸이 없고 story 서버에 묻지 않는다', async () => {
    const { seen } = signedOut({ [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, { ...DETAIL, achievements: [] }) });
    renderApp(`/story/worlds/${WORLD}`);

    expect(await screen.findByRole('heading', { name: '여름 학교' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '업적' })).toBeNull();
    expect(seen.some((request) => request.url.startsWith('/api/v1/story/'))).toBe(false);
  });
});

describe('업적이 없는 세계관(로그인)', () => {
  it('로그인했어도 업적이 없으면 내 기록과 달성률을 묻지 않는다', async () => {
    const { seen } = signedIn({ [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, { ...DETAIL, achievements: [] }) });
    renderApp(`/story/worlds/${WORLD}`);

    expect(await screen.findByRole('heading', { name: '내 세션' })).toBeInTheDocument();
    expect(seen.some((request) => request.url.startsWith('/api/v1/story/achievements'))).toBe(false);
  });
});

describe('업적의 줄', () => {
  it('공개된 것, 받은 사람의 수, 내 기록을 판의 차례로 잇는다', () => {
    const items = storyAchievementItems(ACHIEVEMENTS, RATES, MINE);

    expect(items.map((item) => [item.id, item.name, item.earned_count, item.earned_at])).toEqual([
      ['walk', '공원 산책', 2, null],
      ['secret', '비밀의 방', 1, AT],
      ['kept', null, 0, null],
    ]);
    expect(storyAchievementItems(ACHIEVEMENTS, undefined, undefined).every((item) => item.earned_count === 0 && item.earned_at === null)).toBe(true);
  });
});
