// web/apps/web/src/pages/story/StorySnapshots.test.tsx
// 장면(D2)의 장면 그림(#983). 조각이 있는 답 아래의 "장면 그림"으로 그리기를 시작하고, 그린 그림을 말 아래에 띄운다.
// 내 말에는 단추가 없다. 그리는 모습과 글은 chat 과 같다(ConversationSnapshots.test.tsx 가 자세히 본다).

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { Snapshot } from '../../api/snapshots';
import type { StoryMessage, StorySession } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';

const SESSION = '00000000-0000-4000-8000-00000000ae83';
const WORLD = '00000000-0000-4000-8000-00000000be83';
const PATH = `/api/v1/story/conversations/${SESSION}`;
const IMAGE = '00000000-0000-4000-8000-00000000c983';
const AT = '2026-11-04T03:00:00Z';
const M = (n: number) => `00000000-0000-4000-8000-0000000fe8${n}`;
const DRAW = `/api/v1/story/messages/${M(2)}/snapshot`;

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra } as StoryMessage;
}

function session(): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy' },
    view: storyView({ cast: [castOut('mina', '미나')], slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }] }),
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: 'mina', text: '안녕.' }] })],
    state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn() {
  let list: Snapshot[] = [];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${PATH}`]: () => json(200, session()),
    [`GET ${PATH}/bookmarks`]: () => json(200, []),
    [`GET ${PATH}/snapshots`]: () => json(200, list),
    [`POST ${DRAW}`]: () => {
      // 이 시험은 그리기를 기다리지 않는다. 받자마자 다 그린 것으로 둔다
      list = [{ id: M(9), message_id: M(2), status: 'ready', image_id: IMAGE, code: null, created_at: AT } as Snapshot];
      return json(202, { ...list[0], status: 'drawing', image_id: null });
    },
    [`GET /api/v1/asset/images/${IMAGE}`]: () => new Response('png', { status: 200 }),
  });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면의 장면 그림', () => {
  it('답 아래의 단추로 그리고, 그린 그림을 말 아래에 띄운다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    const answer = within((await screen.findByText('안녕.')).closest('li') as HTMLElement);
    await userEvent.click(answer.getByRole('button', { name: '장면 그림' }));

    await waitFor(() => expect(answer.getByAltText('장면 그림')).toHaveAttribute('src', 'blob:image'));
    expect(seen.filter((request) => request.method === 'POST' && request.url === DRAW)).toHaveLength(1);
  });

  it('내 말에는 단추가 없다', async () => {
    signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    const mine = within((await screen.findByText('안녕?')).closest('li') as HTMLElement);

    expect(mine.queryByRole('button', { name: '장면 그림' })).not.toBeInTheDocument();
  });
});
