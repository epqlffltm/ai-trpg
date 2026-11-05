// web/apps/web/src/pages/story/StoryTools.test.tsx
// 장면(D2)의 왼쪽 열 창(Stitch 22번)과 좁은 화면의 아래 단추 줄. 창의 차례와 처음 펼친 창, 행동 줄이 왼쪽 열에 있는 것,
// 단추 줄이 같은 창을 펼쳐 시트로 여는 것, 지도·이동을 두는 때를 본다. 숨기고 띄우는 것은 CSS 라 상태만 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { sse } from '../../test/chatFixtures';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';
import { storyHasMap, storyTools } from './StoryTools';

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

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면의 왼쪽 열', () => {
  it('지도·이동, 소지품·건네기, 기록, 기억의 차례이고 지도·이동이 펼쳐져 있다. 행동 줄은 창 아래에 있다', async () => {
    signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    const column = within(await screen.findByRole('region', { name: '창' }));
    const toggles = column.getAllByRole('button').filter((button) => button.hasAttribute('aria-expanded'));
    expect(toggles.map((button) => button.textContent)).toEqual(['지도·이동', '소지품·건네기', '기록', '기억']);
    expect(column.getByRole('button', { name: '지도·이동' })).toHaveAttribute('aria-expanded', 'true');
    expect(column.getByText('지금 있는 곳: 학교')).toBeInTheDocument();

    const actions = screen.getByRole('toolbar', { name: '행동' });
    expect(within(actions).getByRole('button', { name: '시간 보내기' })).toBeInTheDocument();
    expect(actions.closest('.chat-room__tools')).not.toBeNull();
  });

  it('아래 단추 줄은 같은 창을 펼쳐 시트로 열고, 다시 누르면 닫는다', async () => {
    signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    const bar = within(await screen.findByRole('navigation', { name: '장면의 단추 줄' }));
    await userEvent.click(bar.getByRole('button', { name: '기록' }));

    expect(screen.getByRole('main')).toHaveAttribute('data-sheet', 'tools');
    const column = within(screen.getByRole('region', { name: '창' }));
    expect(column.getByRole('button', { name: '기록' })).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(bar.getByRole('button', { name: '기록' }));
    expect(screen.getByRole('main')).not.toHaveAttribute('data-sheet');
  });
});

describe('창의 순수한 함수', () => {
  it('지도·이동은 시간이 흐르는 판이고 끝나지 않았을 때만 둔다', () => {
    expect(storyTools(true)).toEqual(['map', 'items', 'records', 'notes']);
    expect(storyTools(false)).toEqual(['items', 'records', 'notes']);
    expect(storyHasMap(VIEW, state(), false)).toBe(true);
    expect(storyHasMap(VIEW, state(), true)).toBe(false);
  });
});
