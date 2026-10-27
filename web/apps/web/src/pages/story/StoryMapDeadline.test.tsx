// web/apps/web/src/pages/story/StoryMapDeadline.test.tsx
// 지도(D3)에서 기한의 마지막 날을 넘기는 이동. 그 길에 "기한을 넘김"을 적고, "가기"를 누르면 창 안에서 한 번 더 묻는다.
// "그만두기"면 보내지 않고, "그래도 가기"면 이동을 보낸다. 넘기지 않는 이동은 바로 보낸다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { sse } from '../../test/chatFixtures';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';
import { crossesDeadline } from './storyMapView';

const SESSION = '00000000-0000-4000-8000-00000000ae11';
const WORLD = '00000000-0000-4000-8000-00000000be11';
const M = (n: number) => `00000000-0000-4000-8000-0000000fe0${n}`;
const AT = '2026-10-27T03:00:00Z';
const ACTIONS = `/api/v1/story/conversations/${SESSION}/actions`;

const VIEW = storyView({
  deadline_days: 3,
  slots: [
    { id: 'morning', name: '아침', start_hour: 8 },
    { id: 'night', name: '밤', start_hour: 21 },
  ],
  places: [
    { id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} },
    { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
    { id: 'hill', name: '언덕', description: '', image_id: null, backgrounds: {} },
  ],
  paths: [
    { a: 'school', b: 'park', minutes: 30 },
    { a: 'school', b: 'hill', minutes: 180 },
  ],
});

/** 3일째(마지막 날) 22시 */
function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 2 * 1440 + 22 * 60, day: 3, slot: 'night', place: 'school', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function session(): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: null, text: '밤이다.' }] })],
    state: state(),
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn() {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session()),
    [`POST ${ACTIONS}`]: () => new Response(sse(['failed', { code: 'stopped' }]), { headers: { 'Content-Type': 'text/event-stream' } }),
  });
}

function moves(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === ACTIONS).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('기한을 넘기는 이동', () => {
  it('기한을 넘기는 길은 한 번 더 묻고, 그만두면 보내지 않으며, 그래도 가면 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '지도' }));
    const map = within(screen.getByRole('dialog', { name: '지도' }));
    const places = within(map.getByRole('list', { name: '갈 수 있는 곳' }));
    expect(places.getByText(/기한을 넘김/)).toBeInTheDocument();

    await userEvent.click(places.getByRole('button', { name: '언덕(으)로 가기' }));
    expect(map.getByRole('alert')).toHaveTextContent('언덕(으)로 가면 기한의 마지막 날을 넘깁니다');
    await userEvent.click(map.getByRole('button', { name: '그만두기' }));
    expect(map.queryByRole('alert')).toBeNull();
    expect(moves(seen)).toEqual([]);

    await userEvent.click(places.getByRole('button', { name: '언덕(으)로 가기' }));
    await userEvent.click(map.getByRole('button', { name: '그래도 가기' }));
    await waitFor(() => expect(moves(seen)).toEqual([{ kind: 'move', place: 'hill' }]));
  });

  it('넘기지 않는 이동은 바로 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '지도' }));
    await userEvent.click(within(screen.getByRole('list', { name: '갈 수 있는 곳' })).getByRole('button', { name: '공원(으)로 가기' }));
    await waitFor(() => expect(moves(seen)).toEqual([{ kind: 'move', place: 'park' }]));
  });
});

describe('순수한 함수', () => {
  it('기한을 넘기는가', () => {
    expect(crossesDeadline(VIEW, state(), 30)).toBe(false);
    expect(crossesDeadline(VIEW, state(), 180)).toBe(true);
    expect(crossesDeadline(VIEW, state({ ending: 'spring' }), 180)).toBe(false);
    expect(crossesDeadline({ ...VIEW, deadline_days: null }, state(), 180)).toBe(false);
  });
});
