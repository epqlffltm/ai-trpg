// web/apps/web/src/pages/story/StoryActions.test.tsx
// 장면(D2)의 행동. 시간 보내기(반응을 받고 다시 읽음), 지도에서 이동, 인물 메뉴의 건네기와 고백(한 번 더 묻기),
// 선택지, 기한의 마지막 날(한 번 더 묻기), 할 수 없는 행동(422), 엔딩 화면(엔딩 수, 새로 시작, 끝난 세션). 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { sse } from '../../test/chatFixtures';
import { castOut, storyView } from '../../test/storyFixtures';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { canConfess, canPassTime, destinations, freshEnding, heldItems, isLastDay, pendingChoices } from './storyActions';

const STORY = '/api/v1/story';
const SESSION = '00000000-0000-4000-8000-00000000a601';
const NEXT = '00000000-0000-4000-8000-00000000a602';
const WORLD = '00000000-0000-4000-8000-00000000b601';
const GEN = '00000000-0000-4000-8000-00000000e601';
const M = (n: number) => `00000000-0000-4000-8000-0000000f60${n}`;
const AT = '2026-10-26T03:00:00Z';

const VIEW = storyView({
  deadline_days: 30,
  slots: [{ id: 'evening', name: '저녁', start_hour: 18 }],
  places: [
    { id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} },
    { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
    { id: 'shop', name: '가게', description: '', image_id: null, backgrounds: {} },
  ],
  paths: [
    { a: 'school', b: 'park', minutes: 20 },
    { a: 'shop', b: 'school', minutes: 10 },
    { a: 'park', b: 'shop', minutes: 15 },
  ],
  items: [
    { id: 'flower', name: '꽃', description: '노란 꽃', image_id: null, consumable: false },
    { id: 'letter', name: '편지', description: '', image_id: null, consumable: false },
  ],
  cast: [castOut('mina', '미나', { confessable: true }), castOut('jun', '준')],
  events: [{ id: 'rain', name: '소나기', image_id: null, cast: [], choices: [{ id: 'share', text: '우산을 함께 쓴다' }, { id: 'run', text: '뛰어간다' }] }],
  endings: [{ id: 'spring', name: '봄의 약속', hint: '', image_id: null, seen: true, unlock: true }],
});

function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 0, day: 3, slot: 'evening', place: 'school', items: { flower: 2 }, affection: {}, companions: [], choosing: null, ending: null, cast: ['mina', 'jun'], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

const MESSAGES = [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: 'mina', text: '안녕.' }] })];

function session(extra: Partial<StorySession> = {}): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', document: {} },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: MESSAGES,
    state: state(),
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StorySession;
}

const ACTIONS = `${STORY}/conversations/${SESSION}/actions`;

function reaction() {
  return new Response(
    sse(
      ['turn', { generation_id: GEN, user_message: { ...message(3, 'action', { content: '[행동] 시간이 흘렀다.' }), alternatives: undefined }, cast: ['mina'], state: state({ cast: ['mina'] }) }],
      ['segment', { speaker: 'mina' }],
      ['delta', { text: '벌써 밤이네.' }],
      ['done', { message: message(4, 'assistant', { segments: [{ speaker: 'mina', text: '벌써 밤이네.' }] }) }],
    ),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}, current: () => StorySession = () => session()) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${STORY}/conversations`]: () => json(200, { items: [], total: 0 }),
    [`GET ${STORY}/conversations/${SESSION}`]: () => json(200, current()),
    [`POST ${ACTIONS}`]: () => reaction(),
    ...routes,
  });
}

function actions(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === ACTIONS).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면의 행동', () => {
  it('시간을 보내면 반응을 받고, 끝나면 세션을 다시 읽는다', async () => {
    let after = false;
    const { seen } = signedIn({
      [`POST ${ACTIONS}`]: () => {
        after = true;
        return reaction();
      },
    }, () => (after ? session({ messages: [...MESSAGES, message(3, 'action', { content: '[행동] 시간이 흘렀다.' }), message(4, 'assistant', { segments: [{ speaker: 'mina', text: '벌써 밤이네.' }] })] }) : session()));
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '시간 보내기' }));
    expect(await screen.findByText('벌써 밤이네.')).toBeInTheDocument();
    expect(await screen.findByText('[행동] 시간이 흘렀다.')).toBeInTheDocument();
    expect(actions(seen)).toEqual([{ kind: 'pass_time' }]);
    await waitFor(() => expect(seen.filter((request) => request.url === `${STORY}/conversations/${SESSION}`).length).toBeGreaterThan(1));
  });

  it('지도에서 길로 이어진 곳과 걸리는 분을 보고 옮긴다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '지도' }));
    const map = within(screen.getByRole('dialog', { name: '지도' }));
    expect(map.getByText('지금 있는 곳: 학교')).toBeInTheDocument();
    const places = within(map.getByRole('list', { name: '갈 수 있는 곳' }));
    expect(places.getByText('공원')).toBeInTheDocument();
    expect(places.getByText('10분')).toBeInTheDocument();
    await userEvent.click(places.getByRole('button', { name: '가게(으)로 가기' }));
    await waitFor(() => expect(actions(seen)).toEqual([{ kind: 'move', place: 'shop' }]));
  });

  it('인물 메뉴에서 물건을 건네고, 한 번 더 물은 뒤 고백한다. 고백이 없는 인물에는 고백이 없다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    const cast = within(await screen.findByRole('region', { name: '장면의 인물' }));
    await userEvent.click(cast.getByRole('button', { name: '준' }));
    let menu = within(screen.getByRole('dialog', { name: '준' }));
    expect(menu.queryByRole('button', { name: '고백' })).toBeNull();
    await userEvent.click(menu.getByRole('button', { name: '닫기' }));

    await userEvent.click(cast.getByRole('button', { name: '미나' }));
    menu = within(screen.getByRole('dialog', { name: '미나' }));
    expect(menu.getByRole('button', { name: '건네기' })).toBeDisabled();
    await userEvent.click(menu.getByLabelText('꽃 × 2'));
    await userEvent.click(menu.getByRole('button', { name: '건네기' }));
    await waitFor(() => expect(actions(seen)).toEqual([{ kind: 'give', cast: 'mina', item: 'flower' }]));
    await waitFor(() => expect(screen.getByRole('button', { name: '시간 보내기' })).toBeEnabled());

    await userEvent.click(cast.getByRole('button', { name: '미나' }));
    menu = within(screen.getByRole('dialog', { name: '미나' }));
    await userEvent.click(menu.getByRole('button', { name: '고백' }));
    expect(menu.getByText(/미나에게 고백합니다/)).toBeInTheDocument();
    await userEvent.click(menu.getByRole('button', { name: '고백하기' }));
    await waitFor(() => expect(actions(seen)[1]).toEqual({ kind: 'confess', cast: 'mina' }));
  });

  it('열린 이벤트의 선택지를 고른다', async () => {
    const { seen } = signedIn({}, () => session({ state: state({ choosing: 'rain' }) }));
    renderApp(`/story/sessions/${SESSION}`);

    const choices = within(await screen.findByRole('region', { name: '선택지' }));
    expect(choices.getByText('소나기')).toBeInTheDocument();
    await userEvent.click(choices.getByRole('button', { name: '우산을 함께 쓴다' }));
    await waitFor(() => expect(actions(seen)).toEqual([{ kind: 'choose', choice: 'share' }]));
  });

  it('기한의 마지막 날은 한 번 더 물은 뒤 하루를 마친다', async () => {
    const { seen } = signedIn({}, () => session({ state: state({ day: 30 }) }));
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '하루 마치기' }));
    const dialog = within(screen.getByRole('dialog', { name: '마지막 날을 마칩니다' }));
    expect(actions(seen)).toEqual([]);
    await userEvent.click(dialog.getByRole('button', { name: '하루 마치기' }));
    await waitFor(() => expect(actions(seen)).toEqual([{ kind: 'end_day' }]));
  });

  it('할 수 없는 행동이면 까닭을 알린다', async () => {
    signedIn({ [`POST ${ACTIONS}`]: () => json(422, { detail: '그렇게 할 수 없습니다.', code: 'cooling_down' }) });
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await within(await screen.findByRole('region', { name: '장면의 인물' })).findByRole('button', { name: '미나' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: '미나' })).getByRole('button', { name: '고백' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: '미나' })).getByRole('button', { name: '고백하기' }));
    expect(await screen.findByText('아직 다시 고백할 수 없습니다. 며칠 지난 뒤에 해 보세요.')).toBeInTheDocument();
  });

  it('엔딩을 보면 엔딩 화면을 띄우고, 새로 시작하면 새 세션으로 간다. 끝난 세션은 행동을 숨긴다', async () => {
    const ended = session({
      messages: [...MESSAGES, message(3, 'action', { content: '[행동] 미나에게 고백했다.', ending_id: 'spring' }), message(4, 'assistant', { segments: [{ speaker: 'mina', text: '나도 좋아.' }] })],
      state: state({ ending: 'spring' }),
    });
    const { seen } = signedIn(
      {
        [`GET ${STORY}/endings`]: () => json(200, { items: [{ ending_id: 'spring', first_seen_at: AT, conversation_id: SESSION }] }),
        [`POST ${STORY}/conversations`]: () => json(201, session({ id: NEXT, messages: [] })),
        [`GET ${STORY}/conversations/${NEXT}`]: () => json(200, session({ id: NEXT, messages: [] })),
      },
      () => ended,
    );
    renderApp(`/story/sessions/${SESSION}`);

    const card = within(await screen.findByRole('region', { name: '엔딩' }));
    expect(card.getByRole('heading', { name: '봄의 약속' })).toBeInTheDocument();
    expect(await card.findByText('엔딩 1/1')).toBeInTheDocument();
    expect(screen.queryByRole('toolbar', { name: '행동' })).toBeNull();
    expect(screen.queryByLabelText('보낼 말')).toBeNull();

    await userEvent.click(card.getByRole('button', { name: '새로 시작' }));
    expect(await screen.findByText('첫 말을 걸어 이야기를 시작하세요.')).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'POST' && request.url === `${STORY}/conversations`).map((request) => request.body)).toEqual([{ world_id: WORLD }]);
  });
});

describe('순수한 함수', () => {
  it('지도, 소지품, 선택지, 고백, 마지막 날, 엔딩', () => {
    expect(destinations(VIEW, 'school')).toEqual([
      { id: 'park', name: '공원', minutes: 20 },
      { id: 'shop', name: '가게', minutes: 10 },
    ]);
    expect(destinations(storyView(), 'school')).toEqual([]);
    expect(heldItems(VIEW, { flower: 1, letter: 0, ghost: 2 })).toEqual([
      { id: 'flower', name: '꽃', count: 1, description: '노란 꽃' },
      { id: 'ghost', name: 'ghost', count: 2, description: '' },
    ]);
    expect(pendingChoices(VIEW, 'rain')?.choices.map((choice) => choice.id)).toEqual(['share', 'run']);
    expect(pendingChoices(VIEW, null)).toBeNull();
    expect(pendingChoices(VIEW, 'ghost')).toBeNull();
    expect(canConfess(VIEW, state(), 'mina')).toBe(true);
    expect(canConfess(VIEW, state(), 'jun')).toBe(false);
    expect(canConfess(VIEW, state({ ending: 'spring' }), 'mina')).toBe(false);
    expect(isLastDay(VIEW, state({ day: 30 }))).toBe(true);
    expect(isLastDay(VIEW, state({ day: 29 }))).toBe(false);
    expect(canPassTime(VIEW, state({ ending: 'spring' }))).toBe(false);
    expect(canPassTime({ after_ending: 'epilogue' }, state({ ending: 'spring' }))).toBe(true);
    expect(freshEnding([message(1, 'action', { ending_id: 'spring' }), message(2, 'assistant')])).toEqual({ messageId: M(1), endingId: 'spring' });
    expect(freshEnding(MESSAGES)).toBeNull();
  });
});
