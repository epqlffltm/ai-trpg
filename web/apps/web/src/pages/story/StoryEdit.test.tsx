// web/apps/web/src/pages/story/StoryEdit.test.tsx
// 장면(D2)의 고치기와 이어서. 내 말은 새 가지로 고쳐 보낸다(edit_of, 받는 동안 그 뒤를 감춤), 답은 조각마다 그 자리에서 고친다(PATCH, 조각 수 어긋남),
// 행동 말은 고치지 않는다, 끊긴 답은 이어 쓴다(첫 조각 앞의 글은 마지막 조각에). 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySavedMessage, StorySession, StoryState } from '../../api/story';
import { sse } from '../../test/chatFixtures';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';
import { canSaveSegments, canSendEdit } from './storyEdit';
import { applyStoryTurnMessage, EMPTY_STORY_TURN } from './storyTurnState';
import { storyTail, visibleStoryMessages } from './storyView';

const SESSION = '00000000-0000-4000-8000-00000000ab01';
const WORLD = '00000000-0000-4000-8000-00000000bb01';
const GEN = '00000000-0000-4000-8000-00000000eb01';
const M = (n: number) => `00000000-0000-4000-8000-0000000fb0${n}`;
const AT = '2026-10-27T03:00:00Z';
const STORY = '/api/v1/story';

const VIEW = storyView({ cast: [castOut('mina', '미나')], slots: [{ id: 'evening', name: '저녁', start_hour: 18 }], places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }] });

function state(): StoryState {
  return { minutes: 0, day: 1, slot: 'evening', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: ['mina'] };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function saved(n: number, role: string, extra: Partial<StorySavedMessage> = {}): StorySavedMessage {
  return { id: M(n), parent_id: M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, ...extra };
}

const ANSWER = message(2, 'assistant', {
  segments: [
    { speaker: null, text: '노을이 졌다.' },
    { speaker: 'mina', text: '기다렸어.' },
  ],
});

function session(messages: StoryMessage[]): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy', document: {} },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages,
    state: state(),
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn(current: () => StorySession, routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${STORY}/conversations`]: () => json(200, { items: [], total: 0 }),
    [`GET ${STORY}/conversations/${SESSION}`]: () => json(200, current()),
    ...routes,
  });
}

function stream(...frames: [string, unknown][]) {
  return new Response(sse(...frames), { headers: { 'Content-Type': 'text/event-stream' } });
}

function bodies(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('고치기와 이어서', () => {
  it('내 말을 고쳐 새 가지로 보낸다', async () => {
    let edited = false;
    const { seen } = signedIn(
      () =>
        edited
          ? session([message(3, 'user', { content: '반가워!', parent_id: null, alternatives: [M(1), M(3)] }), message(4, 'assistant', { parent_id: M(3), segments: [{ speaker: 'mina', text: '나도.' }] })])
          : session([message(1, 'user', { content: '안녕?' }), ANSWER]),
      {
      [`POST ${STORY}/conversations/${SESSION}/messages`]: () => {
        edited = true;
        return stream(
          ['turn', { generation_id: GEN, user_message: saved(3, 'user', { content: '반가워!', parent_id: null }), cast: ['mina'], state: state() }],
          ['segment', { speaker: 'mina' }],
          ['delta', { text: '나도.' }],
          ['done', { message: saved(4, 'assistant', { segments: [{ speaker: 'mina', text: '나도.' }] }) }],
        );
      },
      },
    );
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '내 말 고치기' }));
    const editor = screen.getByLabelText('고쳐 보낼 말');
    expect(screen.getByRole('button', { name: '고쳐 보내기' })).toBeDisabled();
    await userEvent.clear(editor);
    await userEvent.type(editor, '반가워!');
    await userEvent.click(screen.getByRole('button', { name: '고쳐 보내기' }));
    expect(await screen.findByText('나도.')).toBeInTheDocument();
    expect(await screen.findByText('2/2')).toBeInTheDocument();
    expect(screen.queryByText('안녕?')).toBeNull();
    expect(bodies(seen, 'POST', `${STORY}/conversations/${SESSION}/messages`)).toEqual([{ content: '반가워!', edit_of: M(1) }]);
  });

  it('답은 조각마다 그 자리에서 고치고, 조각 수가 어긋나면 다시 읽으라고 알린다. 행동 말에는 고치기가 없다', async () => {
    let patches = 0;
    const { seen } = signedIn(() => session([message(1, 'action', { content: '[행동] 공원으로 갔다.' }), ANSWER]), {
      [`PATCH ${STORY}/messages/${M(2)}`]: (request) => {
        patches += 1;
        if (patches === 2) return json(422, { detail: 'x', code: 'segments_mismatch' });
        const texts = (request.body as { segments: string[] }).segments;
        return json(200, saved(2, 'assistant', { parent_id: M(1), edited: true, segments: [{ speaker: null, text: texts[0] as string }, { speaker: 'mina', text: texts[1] as string }] }));
      },
    });
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('[행동] 공원으로 갔다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '내 말 고치기' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '이 답 고치기' }));
    const mina = screen.getByLabelText('미나');
    expect(screen.getByLabelText('서술')).toHaveValue('노을이 졌다.');
    await userEvent.clear(mina);
    await userEvent.type(mina, '오래 기다렸어.');
    await userEvent.click(screen.getByRole('button', { name: '고치기' }));
    expect(await screen.findByText('오래 기다렸어.')).toBeInTheDocument();
    expect(screen.getByText('고침')).toBeInTheDocument();
    expect(bodies(seen, 'PATCH', `${STORY}/messages/${M(2)}`)).toEqual([{ segments: ['노을이 졌다.', '오래 기다렸어.'] }]);

    await userEvent.click(screen.getByRole('button', { name: '이 답 고치기' }));
    await userEvent.type(screen.getByLabelText('미나'), '!');
    await userEvent.click(screen.getByRole('button', { name: '고치기' }));
    expect(await screen.findByText('조각의 수가 바뀌었습니다. 화면을 새로 읽은 뒤 다시 고쳐 주세요.')).toBeInTheDocument();
  });

  it('끊긴 답을 이어 쓴다. 첫 조각 앞의 글은 마지막 조각에 붙는다', async () => {
    let after = false;
    const partial = message(2, 'assistant', { status: 'partial', segments: [{ speaker: 'mina', text: '그러니까' }] });
    const { seen } = signedIn(
      () =>
        session([
          message(1, 'user', { content: '왜?' }),
          after ? message(2, 'assistant', { segments: [{ speaker: 'mina', text: '그러니까 비밀이야.' }, { speaker: null, text: '바람이 분다.' }] }) : partial,
        ]),
      {
        [`POST ${STORY}/messages/${M(2)}/continue`]: () => {
          after = true;
          return stream(
            ['turn', { generation_id: GEN, user_message: saved(1, 'user', { content: '왜?', parent_id: null }), cast: ['mina'], state: state(), continues: M(2) }],
            ['delta', { text: ' 비밀이야.' }],
            ['segment', { speaker: null }],
            ['delta', { text: '바람이 분다.' }],
            ['done', { message: saved(2, 'assistant', { segments: [{ speaker: 'mina', text: '그러니까 비밀이야.' }, { speaker: null, text: '바람이 분다.' }] }) }],
          );
        },
      },
    );
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('끊긴 답')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '이어서' }));
    expect(await screen.findByText('그러니까 비밀이야.')).toBeInTheDocument();
    expect(screen.getByText('바람이 분다.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('끊긴 답')).toBeNull());
    expect(seen.filter((request) => request.method === 'POST' && request.url === `${STORY}/messages/${M(2)}/continue`)).toHaveLength(1);
    expect(within(screen.getByRole('list', { name: '말' })).getAllByRole('listitem')).toHaveLength(2);
  });
});

describe('순수한 함수', () => {
  it('고치기의 검사', () => {
    expect(canSendEdit('안녕', '안녕')).toBe(false);
    expect(canSendEdit('안녕', '  ')).toBe(false);
    expect(canSendEdit('안녕', '반가워')).toBe(true);
    const segments = [{ speaker: null, text: '가' }, { speaker: 'mina', text: '나' }];
    expect(canSaveSegments(segments, ['가', '나'])).toBe(false);
    expect(canSaveSegments(segments, ['가', '다'])).toBe(true);
    expect(canSaveSegments(segments, ['가', ' '])).toBe(false);
    expect(canSaveSegments(segments, ['가', '다\n라'])).toBe(false);
    expect(canSaveSegments(segments, ['가'])).toBe(false);
  });

  it('이어 쓰기와 고쳐 보내기의 보일 말, 끝의 일', () => {
    let turn = applyStoryTurnMessage(EMPTY_STORY_TURN, { event: 'turn', data: JSON.stringify({ generation_id: GEN, user_message: saved(1, 'user', { parent_id: null }), cast: [], state: state(), continues: M(2) }) });
    turn = applyStoryTurnMessage(turn, { event: 'delta', data: JSON.stringify({ text: '더' }) });
    expect(turn.lead).toBe('더');
    turn = applyStoryTurnMessage(turn, { event: 'segment', data: JSON.stringify({ speaker: 'mina' }) });
    turn = applyStoryTurnMessage(turn, { event: 'delta', data: JSON.stringify({ text: '응' }) });
    const messages = [message(1, 'user'), message(2, 'assistant', { status: 'partial', segments: [{ speaker: null, text: '앞' }] })];
    const visible = visibleStoryMessages(messages, turn);
    expect(visible.streamingId).toBe(M(2));
    expect(visible.items[1]?.segments).toEqual([
      { speaker: null, text: '앞더' },
      { speaker: 'mina', expression: null, text: '응' },
    ]);

    const edit = { ...EMPTY_STORY_TURN, userMessage: saved(5, 'user', { parent_id: null }) };
    expect(visibleStoryMessages([message(1, 'user'), message(2, 'assistant')], edit).items.map((item) => item.id)).toEqual([M(5)]);
    const deeper = { ...EMPTY_STORY_TURN, userMessage: saved(5, 'user', { parent_id: M(2) }) };
    expect(visibleStoryMessages([message(1, 'user'), message(2, 'assistant'), message(3, 'user'), message(4, 'assistant')], deeper).items.map((item) => item.id)).toEqual([M(1), M(2), M(5)]);

    expect(storyTail(messages)).toEqual({ answer: null, regenerate: M(2), continueFrom: M(2) });
  });
});
