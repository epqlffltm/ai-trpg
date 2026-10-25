// web/apps/web/src/pages/chat/conversation/ConversationWorld.test.tsx
// 대화(C3)의 행동과 고치기. 소지품(쓰기, 한마디를 덧붙인 건네기), 상대의 차림, 지도(갈 수 있는 곳과 시간, 이동, 갈 수 없는 곳의 거절),
// 시간 보내기, 내 말 고쳐 보내기(새 가지), 상대의 말 고치기(그 자리, 고침 표시), 기록 받기의 횟수 제한. 창의 글과 대사창을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { ConversationDetail } from '../../../api/types';
import { detail, GEN, ID, M, message, MESSAGES, PATH, posts, saved, signedIn, sse } from '../../../test/chatFixtures';
import { json } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { describeTurnProblem } from './turnProblem';
import { EMPTY_TURN } from './turnState';
import { visibleMessages } from './visibleMessages';
import { destinations, inventoryRows, minutesLabel, outfitNames, visitedNames } from './worldView';

const ACTIONS = `${PATH}/actions`;

const DOCUMENT = {
  name: '루나',
  places: [
    { id: 'cafe', name: '카페', description: '', image_id: null },
    { id: 'park', name: '공원', description: '', image_id: null },
    { id: 'roof', name: '옥상', description: '', image_id: null },
    { id: 'pier', name: '부두', description: '', image_id: null },
  ],
  paths: [
    { a: 'cafe', b: 'park', minutes: 15 },
    { a: 'roof', b: 'cafe', minutes: 5 },
    { a: 'park', b: 'pier', minutes: 30 },
  ],
  items: [
    { id: 'tea', name: '홍차', description: '따뜻한 홍차', kind: 'food', image_id: null, consumable: true, giftable: true },
    { id: 'scarf', name: '목도리', description: '', kind: 'clothing', image_id: null, consumable: false, giftable: true },
  ],
  event_scenes: [],
};

/** 행동의 반응을 받은 뒤 다시 읽으면 붙은 말들이 보이는 대화 */
function growing(): { conversation: () => ConversationDetail; add: (...contents: [string, string][]) => void } {
  let added: ConversationDetail['messages'] = [];
  return {
    conversation: () => ({ ...world(), messages: [...MESSAGES, ...added] }),
    add: (...contents) => {
      added = [...added, ...contents.map(([role, content], index) => message(4 + added.length + index, role, content))];
    },
  };
}

function world(): ConversationDetail {
  const base = detail();
  return {
    ...base,
    character: { ...base.character, document: DOCUMENT } as unknown as ConversationDetail['character'],
    state: { ...base.state, place: 'cafe', visited: ['cafe', 'park'], inventory: [{ item: 'tea', count: 2 }, { item: 'scarf', count: 1 }], outfit: ['scarf'] },
  };
}

function reacting(user: unknown, action: unknown = null) {
  return () =>
    new Response(sse(['turn', { generation_id: GEN, user_message: user, continues: null, action }], ['delta', { text: '고마워요.' }], ['done', { message: saved(7, 'assistant', '고마워요.') }]), {
      headers: { 'Content-Type': 'text/event-stream' },
    });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('대화의 행동', () => {
  it('소지품에서 물건을 쓰고, 한마디를 덧붙여 건넨다. 행동 말과 한마디, 반응이 대사창에 붙는다', async () => {
    const talk = growing();
    let answer = () => {
      talk.add(['action', '홍차를 마셨다.'], ['assistant', '고마워요.']);
      return reacting(saved(4, 'action', '홍차를 마셨다.'))();
    };
    const { seen } = signedIn({ [`POST ${ACTIONS}`]: () => answer() }, talk.conversation);
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '소지품(2)' }));
    const dialog = within(await screen.findByRole('dialog', { name: '소지품' }));
    expect(dialog.getByText('따뜻한 홍차')).toBeInTheDocument();
    expect(dialog.getByText('2개 · 쓰면 없어짐')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '홍차 쓰기' }));
    expect(await screen.findByText('홍차를 마셨다.')).toBeInTheDocument();
    expect(await screen.findByText('고마워요.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();

    answer = () => {
      talk.add(['action', '목도리를 건넸다.'], ['user', '추우니까 둘러요.'], ['assistant', '따뜻해요.']);
      return reacting({ ...saved(7, 'user', '추우니까 둘러요.'), parent_id: M(6) }, { ...saved(6, 'action', '목도리를 건넸다.'), parent_id: M(5) })();
    };
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '소지품(2)' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: '소지품(2)' }));
    const again = within(await screen.findByRole('dialog', { name: '소지품' }));
    await userEvent.click(again.getByRole('button', { name: '목도리 건네기' }));
    await userEvent.type(again.getByRole('textbox', { name: '목도리을(를) 건네며 할 말(비우면 건네기만)' }), '추우니까 둘러요.');
    await userEvent.click(again.getByRole('button', { name: '건네기' }));
    expect(await screen.findByText('목도리를 건넸다.')).toBeInTheDocument();
    expect(screen.getByText('추우니까 둘러요.')).toBeInTheDocument();
    expect(posts(seen, ACTIONS).map((request) => request.body)).toEqual([
      { kind: 'use', item: 'tea' },
      { kind: 'give', item: 'scarf', words: '추우니까 둘러요.' },
    ]);
  });

  it('지도에서 바로 이어진 곳만 시간과 함께 보이고, 가면 이동을 보낸다. 갈 수 없으면 거절의 까닭을 알린다', async () => {
    const { seen } = signedIn({ [`POST ${ACTIONS}`]: () => json(422, { detail: 'x', code: 'not_connected' }) }, world);
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '지도' }));
    const dialog = within(await screen.findByRole('dialog', { name: '지도' }));
    expect(dialog.getByText('지금 있는 곳: 카페')).toBeInTheDocument();
    const ways = within(dialog.getByRole('list', { name: '갈 수 있는 곳' }));
    expect(ways.getAllByRole('button').map((button) => button.textContent)).toEqual(['옥상에 가기', '공원에 가기']);
    expect(ways.getByText('5분 · 처음')).toBeInTheDocument();
    expect(dialog.queryByText(/부두/)).toBeNull();
    await userEvent.click(ways.getByRole('button', { name: '공원에 가기' }));

    expect(await screen.findByText(/지금 있는 곳에서 바로 갈 수 없는 곳입니다/)).toBeInTheDocument();
    expect(posts(seen, ACTIONS).map((request) => request.body)).toEqual([{ kind: 'move', place: 'park' }]);
  });

  it('시간 보내기를 보내고, 상대의 차림을 본다', async () => {
    const talk = growing();
    const { seen } = signedIn(
      {
        [`POST ${ACTIONS}`]: () => {
          talk.add(['action', '시간을 보냈다. 저녁이 되었다.'], ['assistant', '벌써 저녁이네요.']);
          return reacting(saved(4, 'action', '시간을 보냈다. 저녁이 되었다.'))();
        },
      },
      talk.conversation,
    );
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '차림' }));
    expect(within(await screen.findByRole('dialog', { name: '루나의 차림' })).getByText('목도리')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '닫기' }));
    await userEvent.click(screen.getByRole('button', { name: '시간 보내기' }));
    expect(await screen.findByText('시간을 보냈다. 저녁이 되었다.')).toBeInTheDocument();
    expect(posts(seen, ACTIONS).map((request) => request.body)).toEqual([{ kind: 'wait' }]);
  });
});

describe('말 고치기', () => {
  it('내 말은 새 가지로 고쳐 보내고, 상대의 말은 그 자리에서 고친다', async () => {
    const { seen } = signedIn({
      [`POST ${PATH}/messages`]: reacting({ ...saved(8, 'user', '안녕하세요'), parent_id: M(1) }),
      [`PATCH /api/v1/chat/messages/${M(3)}`]: () => json(200, { ...saved(3, 'assistant', '비가 그쳤네요.'), parent_id: M(2), edited: true }),
    });
    renderApp(`/chat/conversations/${ID}`);

    const log = within(await screen.findByRole('list', { name: '말' }));
    await userEvent.click(log.getAllByRole('button', { name: '루나의 말 고치기' })[1] as HTMLElement);
    const box = log.getByRole('textbox', { name: '고칠 글' });
    await userEvent.clear(box);
    await userEvent.type(box, '비가 그쳤네요.');
    await userEvent.click(log.getByRole('button', { name: '고치기' }));
    expect(await log.findByText('비가 그쳤네요.')).toBeInTheDocument();
    expect(log.getByText('고침')).toBeInTheDocument();
    expect(posts(seen, `/api/v1/chat/messages/${M(3)}`).map((request) => request.body)).toEqual([{ content: '비가 그쳤네요.' }]);

    await userEvent.click(log.getByRole('button', { name: '나의 말 고치기' }));
    const mine = log.getByRole('textbox', { name: '고쳐 보낼 말' });
    await userEvent.clear(mine);
    await userEvent.type(mine, '안녕하세요');
    await userEvent.click(log.getByRole('button', { name: '고쳐 보내기' }));
    await vi.waitFor(() => expect(posts(seen, `${PATH}/messages`).map((request) => request.body)).toEqual([{ content: '안녕하세요', edit_of: M(2) }]));
    await vi.waitFor(() => expect(log.queryByRole('textbox', { name: '고쳐 보낼 말' })).toBeNull());
  });

  it('기록 받기가 횟수를 넘으면 기다릴 초를 알린다', async () => {
    const { seen } = signedIn({ [`GET ${PATH}/transcript`]: () => json(429, { detail: 'x' }, { 'Retry-After': '40' }) });
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '기록 받기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '기록 받기' }));
    await userEvent.click(dialog.getByRole('button', { name: '글(.txt)' }));
    expect(await dialog.findByText(/40초 뒤에 다시 받아 주세요/)).toBeInTheDocument();
    expect(seen.some((request) => request.url === `${PATH}/transcript?format=txt`)).toBe(true);
  });
});

describe('행동과 고치기의 순수한 함수', () => {
  it('창의 글', () => {
    const state = world().state;
    expect(inventoryRows(state.inventory, DOCUMENT as never).map((row) => [row.name, row.count, row.consumable, row.clothing])).toEqual([
      ['홍차', 2, true, false],
      ['목도리', 1, false, true],
    ]);
    expect(inventoryRows([{ item: 'gone', count: 1 }], DOCUMENT as never)[0]?.name).toBe('gone');
    expect(outfitNames(['scarf', 'x'], DOCUMENT as never)).toEqual(['목도리', 'x']);
    expect(destinations(DOCUMENT as never, { place: 'park', visited: ['park'] }).map((way) => [way.id, way.minutes, way.visited])).toEqual([
      ['cafe', 15, false],
      ['pier', 30, false],
    ]);
    expect(destinations(DOCUMENT as never, { place: null, visited: [] })).toEqual([]);
    expect(visitedNames(DOCUMENT as never, { place: 'cafe', visited: ['cafe', 'park'] })).toEqual(['공원']);
    expect(minutesLabel(15)).toBe('15분');
    expect(minutesLabel(120)).toBe('2시간');
    expect(minutesLabel(95)).toBe('1시간 35분');
  });

  it('행동과 고친 말의 대사창, 거절의 글', () => {
    const action = { ...EMPTY_TURN, userMessage: { ...saved(5, 'user', '받아요'), parent_id: M(4) }, action: { ...saved(4, 'action', '건넸다.'), parent_id: M(3) }, text: '와' };
    expect(visibleMessages(MESSAGES, action).items.map((item) => item.message.content)).toEqual(['어서 와요.', '안녕', '비가 오네요.', '건넸다.', '받아요']);
    const edited = { ...EMPTY_TURN, userMessage: { ...saved(8, 'user', '안녕하세요'), parent_id: M(1) } };
    expect(visibleMessages(MESSAGES, edited).items.map((item) => item.message.id)).toEqual([M(1), M(8)]);
    expect(visibleMessages([message(1, 'assistant', '어서 와요.')], null).items).toHaveLength(1);
    expect(describeTurnProblem(new ApiError({ status: 422, detail: 'x', code: 'not_held' }))).toMatchObject({ text: '가지고 있지 않은 물건입니다.', reload: true });
  });
});
