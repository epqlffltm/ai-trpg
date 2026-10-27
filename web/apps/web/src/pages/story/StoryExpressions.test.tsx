// web/apps/web/src/pages/story/StoryExpressions.test.tsx
// 장면의 인물 줄의 표정(D2). 끝의 답에서 그 인물이 마지막으로 지은 표정의 스프라이트를 띄우고, 표정이 없거나 그림에 없으면 기본 표정이다.
// 받는 중이면 흘러오는 조각의 표정이다. segment 메시지의 표정을 읽는다. 순수한 함수.

import { screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';
import { expressionsOf, portraitOf } from './storyCastView';
import { applyStoryTurnMessage, EMPTY_STORY_TURN } from './storyTurnState';
import { sceneSegments } from './storyView';

const SESSION = '00000000-0000-4000-8000-00000000ad01';
const WORLD = '00000000-0000-4000-8000-00000000bd11';
const MINA = '00000000-0000-4000-8000-0000000000d1';
const SMILE = '00000000-0000-4000-8000-0000000000d2';
const JUN = '00000000-0000-4000-8000-0000000000d3';
const M = (n: number) => `00000000-0000-4000-8000-0000000fd0${n}`;
const AT = '2026-10-27T03:00:00Z';

const MINA_CAST = castOut('mina', '미나', {
  sprites: [
    { id: 's1', expression: '', image_id: MINA },
    { id: 's2', expression: '웃음', image_id: SMILE },
  ],
});
const VIEW = storyView({
  slots: [{ id: 'evening', name: '저녁', start_hour: 18 }],
  places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }],
  cast: [MINA_CAST, castOut('jun', '준', { sprites: [{ id: 's3', expression: '', image_id: JUN }] })],
});

function state(): StoryState {
  return { minutes: 18 * 60, day: 1, slot: 'evening', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: ['mina', 'jun'] };
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
    messages: [
      message(1, 'user', { content: '안녕?' }),
      message(2, 'assistant', {
        segments: [
          { speaker: 'mina', expression: null, text: '어?' },
          { speaker: 'jun', expression: '화남', text: '늦었잖아.' },
          { speaker: 'mina', expression: '웃음', text: '안녕!' },
        ],
      }),
    ],
    state: state(),
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면의 표정', () => {
  it('끝의 답에서 인물이 마지막으로 지은 표정의 그림을 띄우고, 그림에 없는 표정은 기본이다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
      [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session()),
      [`GET /api/v1/asset/images/${SMILE}`]: () => new Response('png', { status: 200 }),
      [`GET /api/v1/asset/images/${JUN}`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/story/sessions/${SESSION}`);

    await within(await screen.findByRole('region', { name: '장면의 인물' })).findByRole('button', { name: '미나' });
    await vi.waitFor(() => expect(seen.some((request) => request.url === `/api/v1/asset/images/${SMILE}`)).toBe(true));
    expect(seen.some((request) => request.url === `/api/v1/asset/images/${JUN}`)).toBe(true);
    expect(seen.some((request) => request.url === `/api/v1/asset/images/${MINA}`)).toBe(false);
  });
});

describe('순수한 함수', () => {
  it('조각의 표정, 인물마다 마지막 표정, 그림 고르기, 읽을 조각', () => {
    const turn = applyStoryTurnMessage(EMPTY_STORY_TURN, { event: 'segment', data: JSON.stringify({ speaker: 'mina', expression: '웃음' }) });
    expect(turn.segments).toEqual([{ speaker: 'mina', expression: '웃음', text: '' }]);
    expect(applyStoryTurnMessage(EMPTY_STORY_TURN, { event: 'segment', data: JSON.stringify({ speaker: null }) }).segments[0]?.expression).toBeNull();

    const faces = expressionsOf(session().messages[1]?.segments ?? []);
    expect(faces).toEqual({ mina: '웃음', jun: '화남' });
    expect(expressionsOf([{ speaker: null, expression: null }])).toEqual({});
    expect(portraitOf(MINA_CAST, '웃음')).toBe(SMILE);
    expect(portraitOf(MINA_CAST, '없는 표정')).toBe(MINA);
    expect(portraitOf(MINA_CAST)).toBe(MINA);

    const items = session().messages;
    expect(sceneSegments({ items, pending: null })).toHaveLength(3);
    expect(sceneSegments({ items, pending: [] })).toEqual([]);
    expect(sceneSegments({ items: items.slice(0, 1), pending: null })).toEqual([]);
  });
});
