// web/apps/web/src/components/shortcuts/Shortcuts.test.tsx
// 단축어(#981). 내 단축어 화면(마이페이지에서 가기, 더해 저장하면 보낸 목록, 서버의 422), 캐릭터와 세계관의 단축어 탭의 저장 본문.
// 순수한 함수: 이름의 모양(빈칸, /, 길이, 겹침), 설명과 본문의 길이, 상한, 앞으로 옮기기, 보낼 때 다듬기.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import {
  addShortcut,
  moveShortcutUp,
  SHORTCUT_BODY_MAX,
  SHORTCUTS_MAX,
  shortcutsHints,
  toShortcuts,
  type ShortcutDraft,
} from './shortcutsForm';

const MINE = '/api/v1/asset/shortcuts';
const CHARACTERS = '/api/v1/asset/characters';
const WORLDS = '/api/v1/asset/worlds';
const CHARACTER = '00000000-0000-4000-8000-0000000000e1';
const WORLD = '00000000-0000-4000-8000-0000000000fa';
const AT = '2026-11-04T00:00:00Z';

type Routes = Record<string, (request: SeenRequest) => Response>;

function base(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    ...routes,
  });
}

function character() {
  return {
    id: CHARACTER,
    name: '세라',
    age: '',
    gender: '',
    genre: 'romance',
    tags: [],
    rating: 'all',
    visibility: 'private',
    intro_html: '',
    greeting: '',
    speech_examples: '',
    starts: [],
    places: [],
    paths: [],
    start_place: null,
    items: [],
    start_items: [],
    affection: null,
    sprites: [],
    event_scenes: [],
    lorebooks: [],
    shortcuts: [{ name: '일기', description: '', body: '오늘 하루를 일기로 적는다.' }],
    image_id: null,
    hidden_at: null,
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
  };
}

function world() {
  return {
    id: WORLD,
    name: '여름 학교',
    intro_html: '',
    genre: 'romance',
    tags: [],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [{ id: 'morning', name: '아침', start_hour: 7 }],
    start_slot: 'morning',
    deadline_days: null,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro'] },
    places: [],
    paths: [],
    start_place: null,
    items: [],
    start_items: [],
    cast: [],
    events: [],
    endings: [],
    chapters: [],
    shortcuts: [],
    lorebooks: [],
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
  };
}

/** 받은 것을 기억하는 가짜(PATCH 는 칸을 덮고, PUT 은 목록을 바꾼다) */
function remembering(path: string, method: 'PATCH' | 'PUT', initial: Record<string, unknown>): Routes {
  let current = initial;
  return {
    [`GET ${path}`]: () => json(200, current),
    [`${method} ${path}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  };
}

function bodies(seen: SeenRequest[], method: string, path: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === path).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('내 단축어', () => {
  it('마이페이지에서 가서 하나를 더해 저장하면 목록을 통째로 보낸다', async () => {
    const { seen } = base(remembering(MINE, 'PUT', { items: [{ name: '독백', description: '혼잣말', body: '혼잣말을 한다.' }] }));
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: '내 단축어' }));
    const form = within(await screen.findByRole('form', { name: '내 단축어' }));
    expect(await form.findByDisplayValue('독백')).toBeInTheDocument();
    await userEvent.click(form.getByRole('button', { name: '단축어 더하기' }));
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(form.getByLabelText('단축어 2의 이름'), '회상');
    await userEvent.type(form.getByLabelText('단축어 2의 본문'), ' 어릴 적을 떠올린다. ');
    await userEvent.click(form.getByRole('button', { name: '단축어 2 앞으로' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(bodies(seen, 'PUT', MINE)).toEqual([
      {
        items: [
          { name: '회상', description: '', body: '어릴 적을 떠올린다.' },
          { name: '독백', description: '혼잣말', body: '혼잣말을 한다.' },
        ],
      },
    ]);
  });

  it('같은 이름은 저장하지 않고, 서버가 막으면 까닭을 알린다', async () => {
    base({
      [`GET ${MINE}`]: () => json(200, { items: [{ name: '독백', description: '', body: '혼잣말.' }] }),
      [`PUT ${MINE}`]: () => json(422, { detail: [{ loc: ['body', 'items'], msg: 'x', type: 'value_error' }] }),
    });
    renderApp('/me/shortcuts');

    const form = within(await screen.findByRole('form', { name: '내 단축어' }));
    await userEvent.click(await form.findByRole('button', { name: '단축어 더하기' }));
    await userEvent.type(form.getByLabelText('단축어 2의 이름'), '독백');
    await userEvent.type(form.getByLabelText('단축어 2의 본문'), '또.');
    expect(form.getByText('같은 이름의 단축어가 있습니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();

    await userEvent.clear(form.getByLabelText('단축어 2의 이름'));
    await userEvent.type(form.getByLabelText('단축어 2의 이름'), '속말');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText(/서버가 받지 않는 단축어가 있습니다/)).toBeInTheDocument();
  });
});

describe('제작자 단축어', () => {
  it('캐릭터의 단축어 탭에서 고쳐 저장하면 그 칸만 보낸다', async () => {
    const { seen } = base({
      ...remembering(`${CHARACTERS}/${CHARACTER}`, 'PATCH', character()),
      [`GET ${CHARACTERS}`]: () => json(200, { items: [], total: 0 }),
      [`GET ${CHARACTERS}/${CHARACTER}/publish-check`]: () => json(200, { ready: true, problems: [], removed: [] }),
      [`GET ${CHARACTERS}/${CHARACTER}/versions`]: () => json(200, []),
    });
    renderApp(`/chat/studio/characters/${CHARACTER}?tab=shortcuts`);

    const form = within(await screen.findByRole('form', { name: '단축어' }));
    await userEvent.type(form.getByLabelText('단축어 1의 설명'), '오늘의 일기');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(bodies(seen, 'PATCH', `${CHARACTERS}/${CHARACTER}`)).toHaveLength(1));
    expect(bodies(seen, 'PATCH', `${CHARACTERS}/${CHARACTER}`)[0]).toEqual({
      shortcuts: [{ name: '일기', description: '오늘의 일기', body: '오늘 하루를 일기로 적는다.' }],
    });
  });

  it('세계관의 단축어 탭에서 더해 저장하면 그 칸만 보낸다', async () => {
    const { seen } = base({
      ...remembering(`${WORLDS}/${WORLD}`, 'PATCH', world()),
      [`GET ${WORLDS}/${WORLD}/publish-check`]: () => json(200, { ready: true, problems: [], warnings: [], removed: [] }),
      [`GET ${WORLDS}/${WORLD}/versions`]: () => json(200, []),
      'GET /api/v1/asset/characters': () => json(200, { items: [], total: 0 }),
    });
    renderApp(`/story/studio/worlds/${WORLD}?tab=shortcuts`);

    const form = within(await screen.findByRole('form', { name: '단축어' }));
    await userEvent.click(form.getByRole('button', { name: '단축어 더하기' }));
    await userEvent.type(form.getByLabelText('단축어 1의 이름'), '회상');
    await userEvent.type(form.getByLabelText('단축어 1의 본문'), '어릴 적 여름을 떠올린다.');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(bodies(seen, 'PATCH', `${WORLDS}/${WORLD}`)).toHaveLength(1));
    expect(bodies(seen, 'PATCH', `${WORLDS}/${WORLD}`)[0]).toEqual({
      shortcuts: [{ name: '회상', description: '', body: '어릴 적 여름을 떠올린다.' }],
    });
  });
});

describe('단축어의 입력', () => {
  const one = (changes: Partial<ShortcutDraft> = {}): ShortcutDraft => ({ name: '일기', description: '', body: '본문.', ...changes });

  it('이름의 모양과 길이, 겹침을 막는다', () => {
    const hints = shortcutsHints([
      one({ name: '' }),
      one({ name: '두 단어' }),
      one({ name: 'a/b' }),
      one({ name: 'abcdefghijk' }),
      one(),
      one({ name: ' 일기 ' }),
    ]);

    expect(hints[0]?.name).toBe('이름을 적어 주세요.');
    expect(hints[1]?.name).toBe('이름에는 빈칸과 / 를 쓸 수 없습니다.');
    expect(hints[2]?.name).toBe('이름에는 빈칸과 / 를 쓸 수 없습니다.');
    expect(hints[3]?.name).toBe('이름은 10자까지입니다.');
    expect(hints[4]).toBeUndefined();
    expect(hints[5]?.name).toBe('같은 이름의 단축어가 있습니다.');
  });

  it('설명은 30자, 본문은 비울 수 없고 400자까지다', () => {
    const hints = shortcutsHints([one({ name: 'a', description: 'x'.repeat(31) }), one({ name: 'b', body: '  ' }), one({ name: 'c', body: 'x'.repeat(SHORTCUT_BODY_MAX + 1) })]);

    expect(hints[0]?.description).toBe('설명은 30자까지입니다.');
    expect(hints[1]?.body).toBe('본문을 적어 주세요.');
    expect(hints[2]?.body).toBe('본문은 400자까지입니다.');
  });

  it('20개까지 더하고, 앞으로 옮기고, 보낼 때 다듬는다', () => {
    const full = Array.from({ length: SHORTCUTS_MAX }, (_, index) => one({ name: `n${index}` }));

    expect(addShortcut(full)).toBe(full);
    expect(moveShortcutUp([one({ name: 'a' }), one({ name: 'b' })], 1).map((item) => item.name)).toEqual(['b', 'a']);
    expect(toShortcuts([{ name: ' 일기 ', description: ' 설명 ', body: ' 본문 ' }])).toEqual([{ name: '일기', description: '설명', body: '본문' }]);
  });
});
