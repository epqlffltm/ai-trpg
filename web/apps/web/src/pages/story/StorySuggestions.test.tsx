// web/apps/web/src/pages/story/StorySuggestions.test.tsx
// 다음 답 추천(D2, C3 과 같다). 가지의 끝이 다 쓴 답이면 그 답의 추천 셋을 입력칸 위에 보이고, 누르면 입력칸을 채운다(보내는 것은 사람이다).
// 이벤트의 선택지를 기다리는 동안은 숨긴다. 순수한 함수.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';
import { storySuggestions } from './storyView';

const SESSION = '00000000-0000-4000-8000-00000000ac01';
const WORLD = '00000000-0000-4000-8000-00000000bc01';
const M = (n: number) => `00000000-0000-4000-8000-0000000fc0${n}`;
const AT = '2026-10-27T03:00:00Z';
const SUGGESTIONS = ['우산을 펼친다', '같이 뛰자고 한다', '가만히 본다'];

const VIEW = storyView({
  slots: [{ id: 'evening', name: '저녁', start_hour: 18 }],
  places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }],
  events: [{ id: 'rain', name: '소나기', image_id: null, cast: [], choices: [{ id: 'share', text: '우산을 함께 쓴다' }] }],
});

function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 18 * 60, day: 1, slot: 'evening', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function session(extra: Partial<StorySession> = {}): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: null, text: '비가 온다.' }], suggestions: SUGGESTIONS })],
    state: state(),
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StorySession;
}

function signedIn(current: StorySession) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, current),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('다음 답 추천', () => {
  it('끝의 답의 추천 셋을 보이고, 누르면 입력칸을 채운다', async () => {
    const { seen } = signedIn(session());
    renderApp(`/story/sessions/${SESSION}`);

    const list = await screen.findByRole('list', { name: '다음 답 추천' });
    expect(list.querySelectorAll('li')).toHaveLength(3);
    await userEvent.click(screen.getByRole('button', { name: '같이 뛰자고 한다' }));
    expect(screen.getByLabelText('보낼 말')).toHaveValue('같이 뛰자고 한다');
    expect(seen.some((request) => request.method === 'POST' && request.url.includes('/messages'))).toBe(false);
  });

  it('이벤트의 선택지를 기다리는 동안은 숨긴다', async () => {
    signedIn(session({ state: state({ choosing: 'rain' }) }));
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByRole('button', { name: '우산을 함께 쓴다' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '다음 답 추천' })).toBeNull();
  });
});

describe('순수한 함수', () => {
  it('끝이 답일 때만, 선택지를 기다리지 않을 때만', () => {
    expect(storySuggestions([{ role: 'assistant', suggestions: SUGGESTIONS }], false)).toEqual(SUGGESTIONS);
    expect(storySuggestions([{ role: 'assistant', suggestions: SUGGESTIONS }], true)).toEqual([]);
    expect(storySuggestions([{ role: 'assistant', suggestions: SUGGESTIONS }, { role: 'user' }], false)).toEqual([]);
    expect(storySuggestions([{ role: 'assistant' }], false)).toEqual([]);
    expect(storySuggestions([], false)).toEqual([]);
  });
});
