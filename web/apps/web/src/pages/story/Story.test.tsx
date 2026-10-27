// web/apps/web/src/pages/story/Story.test.tsx
// story(D) 의 첫 조각. 내 이야기(/story): 내 세션, 게시한 내 세계관으로 새로 시작, 시작의 거절.
// 장면(D2): 머리의 날짜·시간대·장소·기한, 장면의 인물, 말 조각마다의 이름표(서술은 없음), 말 보내기의 흐름(조각이 흘러 들어옴, 끝나면 다시 읽음),
// 모델이 없으면 보내지 않고 고르기를 엶, 크레딧 부족, 다시 생성과 대안, 끝난 세션. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySavedMessage, StorySession, StoryState } from '../../api/story';
import { sse } from '../../test/chatFixtures';
import { castOut, storyView } from '../../test/storyFixtures';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { describeStartProblem, describeStoryTurnProblem } from './storyTurnProblem';
import { applyStoryTurnMessage, EMPTY_STORY_TURN } from './storyTurnState';
import { sceneOf, storyTail, visibleStoryMessages } from './storyView';
import { castName, daysLeft, isEnded, speakerName, stateLine } from './storyWorld';
import { ApiError } from '../../api/errors';

const STORY = '/api/v1/story';
const SESSION = '00000000-0000-4000-8000-00000000a501';
const WORLD = '00000000-0000-4000-8000-00000000b501';
const GEN = '00000000-0000-4000-8000-00000000e501';
const M = (n: number) => `00000000-0000-4000-8000-0000000f50${n}`;
const AT = '2026-10-26T03:00:00Z';

const VIEW = storyView({
  deadline_days: 100,
  slots: [
    { id: 'morning', name: '아침', start_hour: 7 },
    { id: 'evening', name: '저녁', start_hour: 18 },
  ],
  places: [
    { id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} },
    { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
  ],
  cast: [castOut('mina', '미나'), castOut('jun', '준')],
  endings: [{ id: 'spring', name: '봄의 약속', hint: '', image_id: null, seen: true, unlock: true }],
});

function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 0, day: 3, slot: 'evening', place: 'school', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: ['mina'], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function saved(n: number, role: string, extra: Partial<StorySavedMessage> = {}): StorySavedMessage {
  return { id: M(n), parent_id: M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, ...extra };
}

const MESSAGES = [
  message(1, 'user', { content: '안녕?' }),
  message(2, 'assistant', {
    segments: [
      { speaker: null, text: '노을이 졌다.' },
      { speaker: 'mina', text: '기다렸어.' },
    ],
  }),
];

function session(extra: Partial<StorySession> = {}): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 2, name: '여름 학교', image_id: null, rating: 'all', document: {} },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: MESSAGES,
    state: state(),
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StorySession;
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}, current: () => StorySession = () => session()) {
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

function posts(seen: SeenRequest[], url: string): SeenRequest[] {
  return seen.filter((request) => request.method !== 'GET' && request.url === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('내 이야기', () => {
  it('내 세션을 보이고, 게시한 내 세계관으로 새로 시작하면 장면으로 간다', async () => {
    const { seen } = signedIn({
      [`GET ${STORY}/conversations`]: () =>
        json(200, { items: [{ id: SESSION, title: '여름 학교', world: { id: WORLD, version: 2, name: '여름 학교', image_id: null, rating: 'all' }, model: null, created_at: AT, updated_at: AT }], total: 1 }),
      'GET /api/v1/asset/worlds': () =>
        json(200, {
          items: [
            { id: WORLD, name: '여름 학교', latest_version: 2, rating: 'all', updated_at: AT, visibility: 'private' },
            { id: '00000000-0000-4000-8000-00000000b502', name: '초안만', latest_version: null, rating: 'all', updated_at: AT, visibility: 'private' },
          ],
          total: 2,
        }),
      [`POST ${STORY}/conversations`]: () => json(201, session({ messages: [] })),
    });
    renderApp('/story');

    const sessions = within(await screen.findByRole('list', { name: '내 세션' }));
    expect(await sessions.findByRole('link', { name: '여름 학교' })).toHaveAttribute('href', `/story/sessions/${SESSION}`);
    const worlds = within(await screen.findByRole('list', { name: '시작할 세계관' }));
    expect(await worlds.findByText('여름 학교')).toBeInTheDocument();
    expect(worlds.queryByText('초안만')).toBeNull();

    await userEvent.click(worlds.getByRole('button', { name: '여름 학교 새로 시작' }));
    expect(await screen.findByText('첫 말을 걸어 이야기를 시작하세요.')).toBeInTheDocument();
    expect(posts(seen, `${STORY}/conversations`).map((request) => request.body)).toEqual([{ world_id: WORLD }]);
  });

  it('성인 등급을 쓸 수 없으면 까닭을 알린다', async () => {
    signedIn({
      'GET /api/v1/asset/worlds': () => json(200, { items: [{ id: WORLD, name: '밤의 학교', latest_version: 1, rating: 'adult', updated_at: AT, visibility: 'private' }], total: 1 }),
      [`POST ${STORY}/conversations`]: () => json(403, { detail: 'x', code: 'adult_content_required' }),
    });
    renderApp('/story');

    expect(await screen.findByText('아직 시작한 이야기가 없습니다.')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: '밤의 학교 새로 시작' }));
    expect(await screen.findByText('성인 등급의 세계관입니다. 본인인증으로 성인임을 확인한 뒤에 시작합니다.')).toBeInTheDocument();
  });
});

describe('장면', () => {
  it('머리에 날짜·시간대·장소·기한, 장면의 인물, 말 조각마다 이름표를 보인다', async () => {
    signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByRole('heading', { name: '여름 학교' })).toBeInTheDocument();
    expect(screen.getByText('3일째 · 저녁 · 학교 · D-97')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '장면의 인물' })).getByText('미나')).toBeInTheDocument();
    const log = within(screen.getByRole('list', { name: '말' }));
    expect(log.getByText('안녕?')).toBeInTheDocument();
    expect(log.getByText('나')).toBeInTheDocument();
    expect(log.getByText('노을이 졌다.')).toBeInTheDocument();
    expect(log.getByText('미나')).toBeInTheDocument();
    expect(log.getByText('기다렸어.')).toBeInTheDocument();
  });

  it('말을 보내면 조각이 이름표와 함께 흘러 들어오고, 끝나면 저장한 세션을 다시 읽는다', async () => {
    let after = false;
    const { seen } = signedIn(
      {
        [`POST ${STORY}/conversations/${SESSION}/messages`]: () => {
          after = true;
          return stream(
            ['turn', { generation_id: GEN, user_message: saved(3, 'user', { content: '같이 갈래?' }), cast: ['mina', 'jun'], state: state({ cast: ['mina', 'jun'] }) }],
            ['segment', { speaker: 'jun' }],
            ['delta', { text: '나도 ' }],
            ['delta', { text: '갈게.' }],
            ['done', { message: saved(4, 'assistant', { segments: [{ speaker: 'jun', text: '나도 갈게.' }] }) }],
          );
        },
      },
      () =>
        after
          ? session({ messages: [...MESSAGES, message(3, 'user', { content: '같이 갈래?' }), message(4, 'assistant', { segments: [{ speaker: 'jun', text: '나도 갈게.' }] })], state: state({ cast: ['mina', 'jun'] }) })
          : session(),
    );
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.type(await screen.findByLabelText('보낼 말'), '같이 갈래?');
    await userEvent.click(screen.getByRole('button', { name: '보내기' }));
    expect(await screen.findByText('나도 갈게.')).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole('region', { name: '장면의 인물' })).getByText('준')).toBeInTheDocument());
    expect(posts(seen, `${STORY}/conversations/${SESSION}/messages`).map((request) => request.body)).toEqual([{ content: '같이 갈래?' }]);
    await waitFor(() => expect(seen.filter((request) => request.url === `${STORY}/conversations/${SESSION}`).length).toBeGreaterThan(1));
  });

  it('모델이 없으면 보내지 않고 고르기를 열어 고른다', async () => {
    let model: StorySession['model'] = null;
    const { seen } = signedIn(
      {
        [`GET ${STORY}/models`]: () =>
          json(200, { free: false, items: [{ slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', allows_adult: true, retires_on: null, credits: '40', tier: null, promo: false, next: null }] }),
        [`PUT ${STORY}/conversations/${SESSION}/model`]: () => {
          model = { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true };
          return json(200, model);
        },
      },
      () => session({ model }),
    );
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.type(await screen.findByLabelText('보낼 말'), '안녕');
    await userEvent.click(screen.getByRole('button', { name: '보내기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '모델 고르기' }));
    await userEvent.click(await dialog.findByLabelText('Luna'));
    await userEvent.click(dialog.getByRole('button', { name: '이 모델로 하기' }));
    expect(await screen.findByText('모델: Luna')).toBeInTheDocument();
    expect(screen.getByLabelText('보낼 말')).toHaveValue('안녕');
    expect(posts(seen, `${STORY}/conversations/${SESSION}/messages`)).toHaveLength(0);
    expect(posts(seen, `${STORY}/conversations/${SESSION}/model`).map((request) => request.body)).toEqual([{ model: 'luna' }]);
  });

  it('크레딧이 모자라면 충전으로 가는 길을 붙인다', async () => {
    signedIn({ [`POST ${STORY}/conversations/${SESSION}/messages`]: () => json(402, { detail: 'x', code: 'credit_short', message_id: M(3) }) });
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.type(await screen.findByLabelText('보낼 말'), '안녕');
    await userEvent.click(screen.getByRole('button', { name: '보내기' }));
    expect(await screen.findByText(/크레딧이 모자랍니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '충전하기' })).toBeInTheDocument();
  });

  it('끝의 답은 다시 생성하고, 대안을 넘긴다', async () => {
    const withAlternatives = [MESSAGES[0] as StoryMessage, message(2, 'assistant', { segments: [{ speaker: 'mina', text: '두 번째' }], alternatives: [M(9), M(2)] })];
    const { seen } = signedIn({
      [`GET ${STORY}/conversations/${SESSION}`]: () => json(200, session({ messages: withAlternatives })),
      [`POST ${STORY}/messages/${M(2)}/regenerate`]: () => stream(['failed', { code: 'empty' }]),
      [`PUT ${STORY}/conversations/${SESSION}/branch`]: () => json(200, session()),
    });
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('2/2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 생성' }));
    expect(await screen.findByText(/모델이 빈 답을 냈습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '앞의 대안' }));
    expect(posts(seen, `${STORY}/conversations/${SESSION}/branch`).map((request) => request.body)).toEqual([{ message_id: M(9) }]);
  });

  it('엔딩을 봤고 후일담이 없으면 말 쓰기를 숨기고 엔딩의 이름을 보인다', async () => {
    signedIn({}, () => session({ state: state({ ending: 'spring' }) }));
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('3일째 · 저녁 · 학교 · 엔딩: 봄의 약속')).toBeInTheDocument();
    expect(screen.getByText(/이야기가 끝났습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText('보낼 말')).toBeNull();
    expect(screen.getByRole('button', { name: '기록' })).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  it('세계관 칸에서 이름과 머리의 줄', () => {
    expect(castName(VIEW, 'mina')).toBe('미나');
    expect(castName(VIEW, 'ghost')).toBe('???');
    expect(castName(storyView({ cast: [castOut('veil', null)] }), 'veil')).toBe('???');
    expect(speakerName(VIEW, null)).toBeNull();
    expect(daysLeft(100, 100)).toBe(0);
    expect(daysLeft(null, 3)).toBeNull();
    expect(stateLine({ ...VIEW, deadline_days: null }, state({ slot: 'morning', place: 'park' }))).toBe('3일째 · 아침 · 공원');
    expect(isEnded({ after_ending: 'epilogue' }, state({ ending: 'spring' }))).toBe(false);
    expect(isEnded(VIEW, state({ ending: 'spring' }))).toBe(true);
  });

  it('흘러 들어오는 조각을 쌓는다', () => {
    let turn = applyStoryTurnMessage(EMPTY_STORY_TURN, { event: 'turn', data: JSON.stringify({ generation_id: GEN, user_message: saved(3, 'user'), cast: ['mina'], state: state() }) });
    turn = applyStoryTurnMessage(turn, { event: 'delta', data: JSON.stringify({ text: '바람이 분다.' }) });
    turn = applyStoryTurnMessage(turn, { event: 'segment', data: JSON.stringify({ speaker: 'mina' }) });
    turn = applyStoryTurnMessage(turn, { event: 'delta', data: JSON.stringify({ text: '추워.' }) });
    turn = applyStoryTurnMessage(turn, { event: 'delta', data: '깨진 글' });
    expect(turn.generationId).toBe(GEN);
    expect(turn.segments).toEqual([
      { speaker: null, text: '바람이 분다.' },
      { speaker: 'mina', expression: null, text: '추워.' },
    ]);
    const ended = applyStoryTurnMessage(turn, { event: 'failed', data: JSON.stringify({ code: 'stopped' }) });
    expect(ended.end).toEqual({ kind: 'failed', code: 'stopped' });
    expect(applyStoryTurnMessage(ended, { event: 'delta', data: JSON.stringify({ text: '뒤' }) })).toBe(ended);
  });

  it('보일 말, 끝의 일, 장면', () => {
    const turn = { ...EMPTY_STORY_TURN, userMessage: saved(1, 'user'), cast: ['jun'], state: state({ cast: ['jun'] }) };
    expect(visibleStoryMessages(MESSAGES, turn).items).toHaveLength(1);
    expect(visibleStoryMessages(MESSAGES, { ...turn, userMessage: saved(3, 'user') }).items).toHaveLength(3);
    expect(storyTail(MESSAGES)).toEqual({ answer: null, regenerate: M(2), continueFrom: null });
    expect(storyTail([MESSAGES[0] as StoryMessage])).toEqual({ answer: M(1), regenerate: null, continueFrom: null });
    expect(sceneOf(state(), turn).cast).toEqual(['jun']);
    expect(sceneOf(state(), null).cast).toEqual(['mina']);
  });

  it('거절의 문장', () => {
    expect(describeStoryTurnProblem(new ApiError({ status: 409, detail: 'x', code: 'session_ended' })).text).toBe('끝난 이야기입니다. 엔딩을 봤고 이 세계관은 후일담이 없습니다.');
    expect(describeStoryTurnProblem(new ApiError({ status: 409, detail: 'x', code: 'model_required' })).chooseModel).toBe(true);
    expect(describeStartProblem(new ApiError({ status: 503, detail: 'x', code: 'asset_unavailable', retryAfter: 5 }))).toBe('세계관을 가져오지 못했습니다. 5초 뒤에 다시 눌러 주세요.');
    expect(describeStartProblem(new ApiError({ status: 404, detail: 'x', code: 'world_not_found' }))).toBe('시작할 수 없는 세계관입니다. 게시한 판이 없거나 볼 수 없습니다.');
  });
});
