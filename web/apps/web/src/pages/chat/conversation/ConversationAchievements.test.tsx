// web/apps/web/src/pages/chat/conversation/ConversationAchievements.test.tsx
// 대화(C3)의 "업적을 얻었습니다" 알림(docs/architecture/achievements.md 의 "chat"). 답의 done 에 실린 처음 받은 업적을
// 대사창 아래에 띄우고, 닫기를 누르면 그것만 감춘다. 받았으면 소개의 업적(내 기록과 달성률)을 다시 읽게 한다.
// 업적이 없는 답은 알림도 다시 읽기도 없다. done 의 모양이 틀린 업적은 버린다(turnState 의 순수한 함수).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi, type MockInstance } from 'vitest';
import { detail, GEN, ID, MESSAGES, message, PATH, saved, signedIn, sse } from '../../../test/chatFixtures';
import { renderApp } from '../../../test/renderApp';
import { applyTurnMessage, EMPTY_TURN } from './turnState';

const PICTURE = '00000000-0000-4000-8000-00000000e901';
const REGULAR = { id: 'regular', name: '단골', description: '카페에 세 번 갔다', image_id: PICTURE };
const SECRET = { id: 'secret', name: '첫 고백', description: '', image_id: null };

const ACHIEVEMENTS_KEY = JSON.stringify(['chat', 'achievements']);

/** 다시 읽게 한 열쇠들(JSON) */
function invalidated(spy: MockInstance<QueryClient['invalidateQueries']>): string[] {
  return spy.mock.calls.map(([filters]) => JSON.stringify(filters?.queryKey));
}

function answering(achievements: unknown[]) {
  let after = false;
  const fake = signedIn(
    {
      [`POST ${PATH}/messages`]: () => {
        after = true;
        return new Response(
          sse(['turn', { generation_id: GEN, user_message: saved(4, 'user', '또 왔어요'), continues: null, action: null }], ['delta', { text: '반가워요.' }], ['done', { message: saved(5, 'assistant', '반가워요.'), achievements }]),
          { headers: { 'Content-Type': 'text/event-stream' } },
        );
      },
      [`GET /api/v1/asset/images/${PICTURE}`]: () => new Response('png', { status: 200 }),
    },
    () => (after ? detail({ messages: [...MESSAGES, message(4, 'user', '또 왔어요'), message(5, 'assistant', '반가워요.')] }) : detail()),
  );
  return fake;
}

async function send() {
  renderApp(`/chat/conversations/${ID}`);
  const box = await screen.findByRole('textbox', { name: '보낼 말' });
  await userEvent.type(box, '또 왔어요{Enter}');
  expect(await screen.findByText('반가워요.')).toBeInTheDocument();
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('대화의 업적 알림', () => {
  it('답으로 처음 받은 업적을 그림과 받는 법과 함께 띄우고, 닫으면 그것만 감춘다', async () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:achievement'), revokeObjectURL: vi.fn() });
    answering([REGULAR, SECRET]);
    await send();

    const list = within(await screen.findByRole('list', { name: '얻은 업적' }));
    expect(list.getByText('업적을 얻었습니다: 단골')).toBeInTheDocument();
    expect(list.getByText('카페에 세 번 갔다')).toBeInTheDocument();
    expect(await list.findByRole('img', { name: '단골의 그림' })).toHaveAttribute('src', 'blob:achievement');
    expect(list.getByText('업적을 얻었습니다: 첫 고백')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '단골 알림 닫기' }));
    expect(screen.queryByText('업적을 얻었습니다: 단골')).toBeNull();
    expect(screen.getByText('업적을 얻었습니다: 첫 고백')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '첫 고백 알림 닫기' }));
    expect(screen.queryByRole('list', { name: '얻은 업적' })).toBeNull();
  });

  it('업적이 없는 답이면 알림도 다시 읽기도 없다', async () => {
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
    answering([]);
    await send();

    await vi.waitFor(() => expect(screen.queryByRole('textbox', { name: '보낼 말' })).toHaveValue(''));
    expect(screen.queryByRole('list', { name: '얻은 업적' })).toBeNull();
    await vi.waitFor(() => expect(invalidated(spy)).toContain(JSON.stringify(['chat', 'conversations'])));
    expect(invalidated(spy)).not.toContain(ACHIEVEMENTS_KEY);
    expect(invalidated(spy)).not.toContain(JSON.stringify(['me', 'work-achievements', 'chat']));
  });

  it('받았으면 그 캐릭터의 내 업적과 달성률을 다시 읽는다', async () => {
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
    answering([REGULAR]);
    await send();

    await vi.waitFor(() => expect(invalidated(spy)).toContain(ACHIEVEMENTS_KEY));
    // 마이페이지의 작품 업적도 다시 읽게 한다
    expect(invalidated(spy)).toContain(JSON.stringify(['me', 'work-achievements', 'chat']));
  });
});

describe('done 의 업적', () => {
  it('모양이 맞는 것만 싣고, 없으면 빈 목록이다', () => {
    const turn = applyTurnMessage(EMPTY_TURN, { event: 'turn', data: JSON.stringify({ generation_id: GEN, user_message: saved(4, 'user', '안녕'), continues: null }) });
    const done = applyTurnMessage(turn, {
      event: 'done',
      data: JSON.stringify({ message: saved(5, 'assistant', '응'), achievements: [REGULAR, { id: 'broken' }, { ...SECRET, image_id: 3 }, 'x', null] }),
    });
    expect(done.achievements).toEqual([REGULAR]);
    const bare = applyTurnMessage(turn, { event: 'done', data: JSON.stringify({ message: saved(5, 'assistant', '응') }) });
    expect(bare.achievements).toEqual([]);
    expect(EMPTY_TURN.achievements).toEqual([]);
  });
});
