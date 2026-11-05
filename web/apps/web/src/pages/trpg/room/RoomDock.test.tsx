// web/apps/web/src/pages/trpg/room/RoomDock.test.tsx
// 좁은 화면의 아래 단추 줄(Stitch 20번의 모바일). 창 넷의 단추가 왼쪽 열과 같은 창을 펼치는 것, 다시 누르면 시트를 닫는 것,
// 대화창이 닫혀 있는 동안 남이 쓴 채팅을 채팅 단추에 세고 열면 지우는 것, 모집 중에는 없는 것, 순수한 함수를 본다.
// 숨기고 띄우는 것은 CSS 라 여기서는 상태(aria-expanded, data-sheet)만 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../../test/tableFixtures';
import { nextUnreadChat } from './useRoomDock';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e5';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  members: [
    member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet({}) }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet({}) }),
  ],
});

function chat(sequence: number, userId: string, content: string) {
  return { sequence, user_id: userId, character_name: null, content, created_at: '2026-11-05T01:00:00Z' };
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, { [`GET ${BASE}`]: () => json(200, PLAYING), ...routes }),
  });
}

async function dock() {
  return within(await screen.findByRole('navigation', { name: '테이블 방의 단추 줄' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('아래 단추 줄', () => {
  it('창 단추는 왼쪽 열과 같은 창을 펼쳐 시트로 열고, 다시 누르면 시트를 닫는다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const bar = await dock();
    expect(bar.getAllByRole('button').map((button) => button.textContent)).toEqual(['상태·장비', '소지품·돈', '퀘스트·지도', '일행·기록', '채팅']);
    await userEvent.click(bar.getByRole('button', { name: '소지품·돈' }));

    expect(bar.getByRole('button', { name: '소지품·돈' })).toHaveAttribute('aria-expanded', 'true');
    const status = within(screen.getByRole('region', { name: '상태' }));
    expect(status.getByRole('button', { name: /소지품·돈/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('main')).toHaveAttribute('data-sheet', 'tools');

    await userEvent.click(bar.getByRole('button', { name: '소지품·돈' }));
    expect(bar.getByRole('button', { name: '소지품·돈' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('main')).not.toHaveAttribute('data-sheet');
  });

  it('대화창이 닫혀 있는 동안 남이 쓴 채팅을 세고, 채팅을 열면 지운다', async () => {
    open({
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [sse('chat_message', chat(1, OTHER, '왔어?'), '3-1-0'), sse('chat_message', chat(2, ME, '응'), '3-2-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const bar = await dock();
    const button = await bar.findByRole('button', { name: '채팅, 새 말 1개' });
    await userEvent.click(button);

    expect(bar.getByRole('button', { name: '채팅' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('main')).toHaveAttribute('data-sheet', 'chat');
  });

  it('모집 중에는 단추 줄이 없다', async () => {
    open({ [`GET ${BASE}`]: () => json(200, tableDetail(TABLE_ID)) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: '테이블 방의 단추 줄' })).toBeNull();
  });
});

describe('nextUnreadChat', () => {
  it('보고 있지 않을 때 남이 쓴 것만 센다', () => {
    expect(nextUnreadChat(0, chat(1, OTHER, 'a'), ME, false)).toBe(1);
    expect(nextUnreadChat(1, chat(2, ME, 'b'), ME, false)).toBe(1);
    expect(nextUnreadChat(1, chat(3, OTHER, 'c'), ME, true)).toBe(1);
    expect(nextUnreadChat(0, chat(4, OTHER, 'd'), undefined, false)).toBe(0);
  });
});
