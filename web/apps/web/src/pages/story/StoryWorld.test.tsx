// web/apps/web/src/pages/story/StoryWorld.test.tsx
// 공개 세계관(D1). 로그인하지 않아도 story 첫 화면에서 공개 세계관을 보고 소개로 간다. 소개는 거른 소개, 인물(실루엣은 ???), 엔딩 수,
// 로그인으로 가는 길. 로그인했으면 이 세계관의 내 세션과 본 엔딩 수, 새로 시작. 볼 수 없는 세계관. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';
import { castLabel, endingLine, worldTags } from './storyWorldView';

const WORLD = '00000000-0000-4000-8000-00000000b901';
const SESSION = '00000000-0000-4000-8000-00000000a901';
const AT = '2026-10-26T03:00:00Z';

const SUMMARY = { id: WORLD, version: 2, name: '여름 학교', image_id: null, rating: 'all', tags: ['학원'], deadline_days: 30, published_at: AT };
const DETAIL = {
  ...SUMMARY,
  intro_html: '<p>바닷가의 작은 학교.</p>',
  after_ending: 'epilogue',
  ending_count: 3,
  cast: [
    { id: 'mina', reveal: 'shown', name: '미나', image_id: null },
    { id: 'ghost', reveal: 'silhouette', name: null, image_id: null },
  ],
};

function signedOut(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'GET /api/v1/asset/listings/worlds': () => json(200, { items: [SUMMARY], total: 1 }),
    [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, DETAIL),
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
    'GET /api/v1/story/conversations': () =>
      json(200, { items: [{ id: SESSION, title: '여름 학교', world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' }, model: null, created_at: AT, updated_at: AT }], total: 1 }),
    'GET /api/v1/story/endings': () => json(200, { items: [{ ending_id: 'spring', first_seen_at: AT, conversation_id: SESSION }] }),
    ...routes,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('공개 세계관', () => {
  it('로그인하지 않아도 공개 세계관을 보고 소개로 가며, 시작은 로그인으로 보낸다', async () => {
    const { seen } = signedOut();
    renderApp('/story');

    const card = (await within(await screen.findByRole('list', { name: '공개 세계관' })).findByText('여름 학교')).closest('a') as HTMLElement;
    expect(within(card).getByText('30일')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '내 세션' })).toBeNull();
    await userEvent.click(card);

    expect(await screen.findByRole('heading', { name: '여름 학교' })).toBeInTheDocument();
    expect(screen.getByText('바닷가의 작은 학교.')).toBeInTheDocument();
    expect(screen.getByText('엔딩 3개')).toBeInTheDocument();
    const cast = within(screen.getByRole('list', { name: '인물' }));
    expect(cast.getByText('미나')).toBeInTheDocument();
    expect(cast.getByText('???')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '시작하기' })).getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
    expect(seen.every((request) => !request.headers.has('Authorization'))).toBe(true);
    expect(seen.some((request) => request.url.startsWith('/api/v1/story/'))).toBe(false);
  });

  it('로그인했으면 이 세계관의 내 세션과 본 엔딩 수를 보이고 새로 시작한다', async () => {
    const { seen } = signedIn({
      'POST /api/v1/story/conversations': () => json(201, { id: SESSION, title: '여름 학교', world: { ...SUMMARY, document: {} }, view: storyView(), model: null, messages: [], state: { minutes: 0, day: 1, slot: 'morning', place: 'school', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] }, created_at: AT, updated_at: AT }),
    });
    renderApp(`/story/worlds/${WORLD}`);

    expect(await screen.findByText('엔딩 1/3')).toBeInTheDocument();
    const sessions = within(screen.getByRole('list', { name: '이 세계관의 내 세션' }));
    expect(await sessions.findByRole('link', { name: /1판/ })).toHaveAttribute('href', `/story/sessions/${SESSION}`);
    expect(seen.some((request) => request.url === `/api/v1/story/conversations?limit=20&offset=0&world_id=${WORLD}`)).toBe(true);

    await userEvent.click(screen.getByRole('button', { name: '새로 시작' }));
    expect(await screen.findByText('첫 말을 걸어 이야기를 시작하세요.')).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'POST' && request.url === '/api/v1/story/conversations').map((request) => request.body)).toEqual([{ world_id: WORLD }]);
  });

  it('볼 수 없는 세계관이면 까닭을 가르지 않는다', async () => {
    signedOut({ [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(404, { detail: '찾을 수 없습니다.' }) });
    renderApp(`/story/worlds/${WORLD}`);
    expect(await screen.findByText('볼 수 없는 세계관입니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '다른 세계관 찾기' })).toHaveAttribute('href', '/story');
  });

  it('순수한 함수', () => {
    expect(worldTags({ rating: 'adult', genre: 'romance', deadline_days: 100, tags: ['학원', '학원'] })).toEqual(['성인', '로맨스', '100일', '학원']);
    expect(worldTags({ rating: 'all', genre: 'slice_of_life', deadline_days: null, tags: [] })).toEqual(['일상']);
    expect(castLabel({ name: null, reveal: 'silhouette' })).toBe('???');
    expect(castLabel({ name: '미나', reveal: 'shown' })).toBe('미나');
    expect(endingLine(0, 2)).toBeNull();
    expect(endingLine(3, null)).toBe('엔딩 3개');
    expect(endingLine(3, 5)).toBe('엔딩 3/3');
  });
});
