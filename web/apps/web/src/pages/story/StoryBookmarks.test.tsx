// web/apps/web/src/pages/story/StoryBookmarks.test.tsx
// 장면(D2)의 책갈피(#982). 말 아래의 단추로 달고, 행동 줄의 "책갈피" 창에서 그 자리로 간다.
// 지금 가지에 없는 말이면 가지를 바꾼다. 창의 몸은 chat 과 같다(ConversationBookmarks.test.tsx 가 자세히 본다).

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession } from '../../api/story';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';

const SESSION = '00000000-0000-4000-8000-00000000ae31';
const WORLD = '00000000-0000-4000-8000-00000000be31';
const PATH = `/api/v1/story/conversations/${SESSION}`;
const BOOKMARKS = `${PATH}/bookmarks`;
const AT = '2026-11-03T03:00:00Z';
const M = (n: number) => `00000000-0000-4000-8000-0000000fe3${n}`;

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra } as StoryMessage;
}

const FIRST = [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: 'mina', text: '안녕.' }], alternatives: [M(2), M(9)] })];
const OTHER = [message(1, 'user', { content: '안녕?' }), message(9, 'assistant', { segments: [{ speaker: 'mina', text: '다른 답이야.' }], alternatives: [M(2), M(9)] })];

function session(messages: StoryMessage[]): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy' },
    view: storyView({ cast: [castOut('mina', '미나')], slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }] }),
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages,
    state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn(marks: unknown[]) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${PATH}`]: () => json(200, session(FIRST)),
    [`GET ${BOOKMARKS}`]: () => json(200, marks),
    [`PUT ${BOOKMARKS}/${M(2)}`]: () => json(200, { message_id: M(2), note: null, role: 'assistant', excerpt: '안녕.', created_at: AT }),
    [`PUT ${PATH}/branch`]: () => json(200, session(OTHER)),
  });
}

function requests(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면의 책갈피', () => {
  it('말 아래의 단추로 단다', async () => {
    const { seen } = signedIn([]);
    renderApp(`/story/sessions/${SESSION}`);

    const answer = await screen.findByText('안녕.');
    await userEvent.click(within(answer.closest('li') as HTMLElement).getByRole('button', { name: '책갈피' }));

    await waitFor(() => expect(requests(seen, 'PUT', `${BOOKMARKS}/${M(2)}`)).toHaveLength(1));
  });

  it('다른 가지의 책갈피로 가면 그 가지가 보인다', async () => {
    const { seen } = signedIn([{ message_id: M(9), note: '좋았던 답', role: 'assistant', excerpt: '다른 답이야.', created_at: AT }]);
    renderApp(`/story/sessions/${SESSION}`);

    const actions = within(await screen.findByRole('toolbar', { name: '행동' }));
    await userEvent.click(actions.getByRole('button', { name: '책갈피' }));
    const dialog = within(await screen.findByRole('dialog', { name: '책갈피' }));
    expect(await dialog.findByText('메모: 좋았던 답')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '이 자리로' }));

    expect(await screen.findByText('다른 답이야.')).toBeInTheDocument();
    expect(requests(seen, 'PUT', `${PATH}/branch`)[0]?.body).toEqual({ message_id: M(9) });
  });
});
