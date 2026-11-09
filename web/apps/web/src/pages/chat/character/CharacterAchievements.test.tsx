// web/apps/web/src/pages/chat/character/CharacterAchievements.test.tsx
// 캐릭터 소개(C2)의 업적(docs/architecture/achievements.md 의 "chat"). 판의 차례로 이름, 받는 법, 달성률(대화한 사람 중)을 보인다.
// 숨긴 업적은 받기 전에 가리고, 받았으면 받은 때의 이름이 보인다. 로그인하지 않으면 달성률만 읽는다.
// 업적이 없으면 칸이 없고 chat 서버의 업적을 묻지 않는다. 달성률을 읽지 못하면 다시 시도를 둔다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { achievementRate } from '../../trpg/scenario/achievementView';

const LUNA = '00000000-0000-4000-8000-00000000c901';
const AT = '2026-11-09T03:00:00Z';
const ACHIEVEMENTS = [
  { id: 'cafe', hidden: false, name: '단골', description: '카페에 갔다', image_id: null },
  { id: 'secret', hidden: true, name: null, description: null, image_id: null },
  { id: 'kept', hidden: true, name: null, description: null, image_id: null },
];
const DOCUMENT = {
  name: '루나',
  age: '',
  gender: '',
  tags: [],
  rating: 'all',
  genre: 'romance',
  image_id: null,
  greeting: '',
  intro_html: '<p>카페 주인</p>',
  starts: [{ title: '비 오는 오후', situation: '비를 피해 들어온다.' }],
  affection: null,
  event_scenes: [],
  achievements: [],
};
const DETAIL = { id: LUNA, version: 2, published_at: AT, creator_id: null, heart_count: 0, start_count: 0, document: DOCUMENT, achievements: ACHIEVEMENTS };
const RATES = { players: 8, items: [{ achievement_id: 'cafe', earned_count: 2 }, { achievement_id: 'secret', earned_count: 1 }] };
const MINE = { items: [{ achievement_id: 'secret', name: '첫 고백', description: '고백을 받았다', image_id: null, earned_at: AT, conversation_id: null }] };

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedOut(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    [`GET /api/v1/asset/listings/characters/${LUNA}`]: () => json(200, DETAIL),
    'GET /api/v1/chat/achievements/rates': () => json(200, RATES),
    ...routes,
  });
}

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/asset/listings/characters/${LUNA}`]: () => json(200, DETAIL),
    'GET /api/v1/chat/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/chat/gallery': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/personas': () => json(200, []),
    'GET /api/v1/chat/achievements/rates': () => json(200, RATES),
    'GET /api/v1/chat/achievements': () => json(200, MINE),
    ...routes,
  });
}

async function achievementList() {
  return within(await screen.findByRole('list', { name: '업적' }));
}

const asksMine = (seen: SeenRequest[]) => seen.some((request) => request.url.startsWith('/api/v1/chat/achievements?'));
const asksAny = (seen: SeenRequest[]) => seen.some((request) => request.url.startsWith('/api/v1/chat/achievements'));

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캐릭터 소개의 업적', () => {
  it('로그인하지 않으면 업적과 대화한 사람 중의 달성률을 보이고 숨긴 업적은 가린다', async () => {
    const { seen } = signedOut();
    renderApp(`/chat/characters/${LUNA}`);

    const list = await achievementList();
    expect(await list.findByText('대화한 8명 중 2명(25%)')).toBeInTheDocument();
    expect(list.getByText('단골')).toBeInTheDocument();
    expect(list.getByText('카페에 갔다')).toBeInTheDocument();
    expect(list.getAllByText('숨긴 업적')).toHaveLength(2);
    expect(screen.queryByText(/내가 받은 업적/)).toBeNull();
    expect(asksMine(seen)).toBe(false);
    const rates = seen.find((request) => request.url.startsWith('/api/v1/chat/achievements/rates'));
    expect(rates?.url).toContain(`character_id=${LUNA}`);
  });

  it('로그인했으면 받은 수와 받은 날을 보이고, 받은 숨긴 업적은 받은 때의 이름이다', async () => {
    const { seen } = signedIn();
    renderApp(`/chat/characters/${LUNA}`);

    expect(await screen.findByText('내가 받은 업적 1 / 3개')).toBeInTheDocument();
    const list = await achievementList();
    expect(list.getByText('첫 고백')).toBeInTheDocument();
    expect(list.getByText('고백을 받았다')).toBeInTheDocument();
    expect(list.getAllByText('숨긴 업적')).toHaveLength(1);
    expect(list.getByText('단골').closest('li')).toHaveClass('achievement-item--locked');
    expect((list.getByText('첫 고백').closest('li') as HTMLElement).className).toBe('achievement-item');
    expect(seen.find((request) => request.url.startsWith('/api/v1/chat/achievements?'))?.url).toContain(`character_id=${LUNA}`);
  });

  it('달성률을 읽지 못하면 다시 시도한다', async () => {
    let fail = true;
    signedOut({ 'GET /api/v1/chat/achievements/rates': () => (fail ? json(503, { detail: 'down' }) : json(200, RATES)) });
    renderApp(`/chat/characters/${LUNA}`);

    const retry = await screen.findByRole('button', { name: '다시 시도' }, { timeout: 5000 });
    expect(screen.getByText(/달성률을 불러오지 못했습니다/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(retry);
    expect(await screen.findByText('대화한 8명 중 2명(25%)')).toBeInTheDocument();
  });

  it('내 기록을 읽지 못하면 그것만 다시 시도한다', async () => {
    let fail = true;
    signedIn({ 'GET /api/v1/chat/achievements': () => (fail ? json(503, { detail: 'down' }) : json(200, MINE)) });
    renderApp(`/chat/characters/${LUNA}`);

    const retry = await screen.findByRole('button', { name: '다시 시도' }, { timeout: 5000 });
    expect(screen.getByText(/내가 받은 업적을 불러오지 못했습니다/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(retry);
    expect(await screen.findByText('내가 받은 업적 1 / 3개')).toBeInTheDocument();
  });

  it('업적이 없는 캐릭터면 칸이 없고 chat 서버의 업적을 묻지 않는다', async () => {
    const { seen } = signedIn({ [`GET /api/v1/asset/listings/characters/${LUNA}`]: () => json(200, { ...DETAIL, achievements: [] }) });
    renderApp(`/chat/characters/${LUNA}`);

    expect(await screen.findByRole('heading', { name: '루나' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '소개' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '업적' })).toBeNull();
    expect(asksAny(seen)).toBe(false);
  });

  it('업적의 칸이 없는 옛 응답도 그린다', async () => {
    const { achievements: _dropped, ...older } = DETAIL;
    const { seen } = signedOut({ [`GET /api/v1/asset/listings/characters/${LUNA}`]: () => json(200, older) });
    renderApp(`/chat/characters/${LUNA}`);

    expect(await screen.findByRole('heading', { name: '루나' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '업적' })).toBeNull();
    expect(asksAny(seen)).toBe(false);
  });
});

describe('달성률의 글', () => {
  it('모수가 한 일을 바꿔 적는다. 기본은 플레이한이다', () => {
    expect(achievementRate(1, 200, '대화한')).toBe('대화한 200명 중 1명(1% 미만)');
    expect(achievementRate(0, 0, '대화한')).toBe('아직 대화한 사람이 없습니다');
    expect(achievementRate(3, 12)).toBe('플레이한 12명 중 3명(25%)');
  });
});
