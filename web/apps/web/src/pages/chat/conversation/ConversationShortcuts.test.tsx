// web/apps/web/src/pages/chat/conversation/ConversationShortcuts.test.tsx
// 입력칸의 단축어 고르기(#981). "/"를 치면 처음 목록을 읽고, 적은 만큼으로 거르고, 고르면 "/이름 "이 되어 입력칸으로 돌아간다.
// 화살표로 옮기고 Enter 로 고르며(보내지 않는다) Esc 로 닫는다. 보통의 말에는 목록을 읽지 않는다. 목록을 읽지 못해도 입력은 그대로다.
// story 의 장면도 같은 입력칸을 쓴다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ConversationShortcut } from '../../../api/conversationShortcuts';
import { REFRESH_PATH } from '../../../api/refresh';
import type { StorySession } from '../../../api/story';
import { ID, PATH, posts, signedIn } from '../../../test/chatFixtures';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { castOut, storyView } from '../../../test/storyFixtures';
import { movedPick, pickedDraft, pickLabel, PICKS_SHOWN, picksFor, typedName } from './shortcutPicks';

const SHORTCUTS: ConversationShortcut[] = [
  { name: '일기', description: '오늘의 일기', source: 'work' },
  { name: '회상', description: '', source: 'work' },
  { name: '일과', description: '', source: 'mine' },
];

function reads(seen: SeenRequest[], url: string): SeenRequest[] {
  return seen.filter((request) => request.method === 'GET' && request.url === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('입력칸의 단축어', () => {
  it('"/"를 치면 목록을 읽고 적은 만큼 거르며, 고르면 "/이름 "이 된다', async () => {
    const { seen } = signedIn({ [`GET ${PATH}/shortcuts`]: () => json(200, SHORTCUTS) });
    renderApp(`/chat/conversations/${ID}`);

    const input = await screen.findByLabelText('보낼 말');
    await userEvent.type(input, '안녕');
    expect(reads(seen, `${PATH}/shortcuts`)).toHaveLength(0);
    await userEvent.clear(input);
    await userEvent.type(input, '/');

    const list = within(await screen.findByRole('list', { name: '단축어' }));
    expect(list.getAllByRole('button').map((button) => button.textContent)).toEqual(['/일기 · 오늘의 일기', '/회상', '/일과 (내 단축어)']);
    await userEvent.type(input, '일');
    await waitFor(() => expect(list.getAllByRole('button')).toHaveLength(2));
    await userEvent.click(list.getByRole('button', { name: '/일기 · 오늘의 일기' }));

    expect(input).toHaveValue('/일기 ');
    expect(input).toHaveFocus();
    expect(screen.queryByRole('list', { name: '단축어' })).not.toBeInTheDocument();
    expect(reads(seen, `${PATH}/shortcuts`)).toHaveLength(1);
  });

  it('화살표로 옮기고 Enter 로 고르며 보내지 않는다. Esc 로 닫고 글을 고치면 다시 보인다', async () => {
    const { seen } = signedIn({ [`GET ${PATH}/shortcuts`]: () => json(200, SHORTCUTS) });
    renderApp(`/chat/conversations/${ID}`);

    const input = await screen.findByLabelText('보낼 말');
    await userEvent.type(input, '/');
    const list = within(await screen.findByRole('list', { name: '단축어' }));
    expect(list.getByRole('button', { name: '/일기 · 오늘의 일기' })).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('{ArrowUp}');
    expect(list.getByRole('button', { name: '/일과 (내 단축어)' })).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('{ArrowDown}{ArrowDown}');
    expect(list.getByRole('button', { name: '/회상' })).toHaveAttribute('aria-current', 'true');
    await userEvent.keyboard('{Enter}');

    expect(input).toHaveValue('/회상 ');
    expect(posts(seen, `${PATH}/messages`)).toHaveLength(0);

    await userEvent.clear(input);
    await userEvent.type(input, '/일');
    expect(await screen.findByRole('list', { name: '단축어' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('list', { name: '단축어' })).not.toBeInTheDocument();
    await userEvent.type(input, '기');
    expect(await screen.findByRole('list', { name: '단축어' })).toBeInTheDocument();
  });

  it('목록을 읽지 못해도 적은 그대로 둔다', async () => {
    signedIn({ [`GET ${PATH}/shortcuts`]: () => json(503, { detail: 'x' }) });
    renderApp(`/chat/conversations/${ID}`);

    const input = await screen.findByLabelText('보낼 말');
    await userEvent.type(input, '/일기');

    expect(input).toHaveValue('/일기');
    expect(screen.queryByRole('list', { name: '단축어' })).not.toBeInTheDocument();
  });

  it('story 의 장면에서도 세션의 단축어를 고른다', async () => {
    const session = '00000000-0000-4000-8000-00000000ae41';
    const path = `/api/v1/story/conversations/${session}`;
    const at = '2026-11-04T03:00:00Z';
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
      [`GET ${path}`]: () =>
        json(200, {
          id: session,
          title: '여름 학교',
          world: { id: '00000000-0000-4000-8000-00000000be41', version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy' },
          view: storyView({ cast: [castOut('mina', '미나')], slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }] }),
          model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
          messages: [],
          state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
          created_at: at,
          updated_at: at,
        } as StorySession),
      [`GET ${path}/bookmarks`]: () => json(200, []),
      [`GET ${path}/shortcuts`]: () => json(200, [{ name: '회상', description: '어릴 적', source: 'work' }]),
    });
    renderApp(`/story/sessions/${session}`);

    const input = await screen.findByLabelText('보낼 말');
    await userEvent.type(input, '/');
    await userEvent.click(await screen.findByRole('button', { name: '/회상 · 어릴 적' }));

    expect(input).toHaveValue('/회상 ');
  });
});

describe('단축어 고르기의 계산', () => {
  it('"/"로 시작하고 빈칸 전일 때만 이름을 적는 중이다', () => {
    expect(typedName('/')).toBe('');
    expect(typedName('/일')).toBe('일');
    expect(typedName('/일기 ')).toBeNull();
    expect(typedName('일기')).toBeNull();
    expect(typedName(' /일기')).toBeNull();
    expect(typedName('/일/기')).toBeNull();
  });

  it('적은 만큼으로 시작하는 것을 앞에서부터 보인다', () => {
    const many = Array.from({ length: PICKS_SHOWN + 3 }, (_, index): ConversationShortcut => ({ name: `a${index}`, description: '', source: 'mine' }));

    expect(picksFor('/일', SHORTCUTS).map((shortcut) => shortcut.name)).toEqual(['일기', '일과']);
    expect(picksFor('/a', many)).toHaveLength(PICKS_SHOWN);
    expect(picksFor('안녕', SHORTCUTS)).toEqual([]);
    expect(pickedDraft(SHORTCUTS[1] as ConversationShortcut)).toBe('/회상 ');
    expect([movedPick(0, 3, 1), movedPick(2, 3, 1), movedPick(0, 3, -1), movedPick(0, 0, 1)]).toEqual([1, 0, 2, 0]);
    expect(pickLabel({ name: '독백', description: '  ', source: 'mine' })).toBe('/독백 (내 단축어)');
  });
});
