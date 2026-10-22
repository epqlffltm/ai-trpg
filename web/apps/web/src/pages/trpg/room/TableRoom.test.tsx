// web/apps/web/src/pages/trpg/room/TableRoom.test.tsx
// 테이블 방(B6)의 대기실과 스트림. 붙는 번호, 스트림의 채팅과 입력 중, 쓰기, 이벤트가 오면 다시 읽기,
// 다시 붙을 때의 Last-Event-ID, 토큰 만료, 시작, 나가기, 앉아 있지 않게 됨을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { getSession } from '../../../api/session';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, sse, sseResponse, tableDetail } from '../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000b1';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function chat(sequence: number, userId = OTHER, content = `글 ${sequence}`) {
  return { sequence, user_id: userId, character_name: null, content, created_at: '2026-10-22T00:00:00Z' };
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}, refresh = () => json(200, tokens('a1'))) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: refresh,
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/game/tables/lobby': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/game/tables': () => json(200, { items: [], total: 0 }),
    ...roomRoutes(TABLE_ID, routes),
  });
}

function streams(seen: SeenRequest[]): SeenRequest[] {
  return seen.filter((request) => request.url.startsWith(`${BASE}/stream`));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('TableRoom', () => {
  it('방장은 초대 코드를 보고, 캐릭터를 정하지 않은 사람이 있으면 시작을 막는다. 스트림은 읽은 마지막 번호로 붙는다', async () => {
    const { seen } = open({
      [`GET ${BASE}/messages`]: () => json(200, { items: [chat(7)], last_sequence: 7 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('ABC123')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '시작하기' })).toBeDisabled();
    expect(screen.getByText('글 7')).toBeInTheDocument();

    await vi.waitFor(() => expect(streams(seen)).toHaveLength(1));
    const url = new URL(streams(seen)[0]?.url ?? '', 'http://x');
    expect(Object.fromEntries(url.searchParams)).toEqual({ events_after: '3', messages_after: '7', whispers_after: '0' });
    expect(streams(seen)[0]?.headers.get('Authorization')).toBe('Bearer a1');
  });

  it('스트림의 채팅을 더하고, 그 사람의 입력 중을 지운다', async () => {
    open({
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [sse('typing', { user_id: OTHER }), sse('chat_message', chat(1, OTHER, '안녕'), '3-1-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('안녕')).toBeInTheDocument();
    expect(screen.queryByText(/입력하는 중/)).not.toBeInTheDocument();
  });

  it('입력 중을 5초쯤 보인다', async () => {
    open({
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('typing', { user_id: OTHER })]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText(/님이 입력하는 중/)).toBeInTheDocument();
  });

  it('쓴 채팅을 바로 보이고, 스트림이 같은 것을 다시 줘도 한 번만 보인다', async () => {
    const { seen } = open({
      [`POST ${BASE}/messages`]: () => json(201, chat(1, ME, '반가워요')),
      [`POST ${BASE}/messages/typing`]: () => new Response(null, { status: 204 }),
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('chat_message', chat(1, ME, '반가워요'), '3-1-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.type(await screen.findByLabelText('채팅 쓰기'), '반가워요{Enter}');

    expect(await screen.findByText('반가워요')).toBeInTheDocument();
    expect(screen.getByLabelText('채팅 쓰기')).toHaveValue('');
    expect(seen.find((request) => request.method === 'POST' && request.url === `${BASE}/messages`)?.body).toEqual({
      content: '반가워요',
    });
    expect(screen.getAllByText('반가워요')).toHaveLength(1);
    expect(seen.filter((request) => request.url === `${BASE}/messages/typing`)).toHaveLength(1);
  });

  it('이벤트가 오면 테이블을 다시 읽는다. 붙을 때와 이벤트가 몰려 오면 한 번만 읽는다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}`]: () => {
        reads += 1;
        return json(200, tableDetail(TABLE_ID, reads >= 2 ? { title: '바뀐 이름' } : {}));
      },
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [
          sse('table_event', { sequence: 4, type: 'member_joined' }, '4-0-0'),
          sse('table_event', { sequence: 5, type: 'host_changed' }, '5-0-0'),
        ]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('heading', { name: '바뀐 이름', level: 1 }, { timeout: 3000 })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(reads).toBe(2);
  });

  it('서버가 꺼지면 잠깐 쉬었다가 마지막 id 를 Last-Event-ID 로 보내며 다시 붙는다', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    let opened = 0;
    const { seen } = open({
      [`GET ${BASE}/stream`]: (request) => {
        opened += 1;
        if (opened > 1) return sseResponse(request, []);
        return sseResponse(
          request,
          [sse('chat_message', chat(1), '3-1-0'), sse('closed', { reason: 'server_shutdown' })],
          false,
        );
      },
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await vi.waitFor(() => expect(streams(seen)).toHaveLength(2), { timeout: 3000 });
    expect(streams(seen)[1]?.headers.get('Last-Event-ID')).toBe('3-1-0');
  });

  it('토큰이 만료되면 갱신하고 새 토큰으로 다시 붙는다', async () => {
    let refreshes = 0;
    let opened = 0;
    const { seen } = open(
      {
        [`GET ${BASE}/stream`]: (request) => {
          opened += 1;
          if (opened > 1) return sseResponse(request, []);
          return sseResponse(request, [sse('closed', { reason: 'token_expired' })], false);
        },
      },
      () => {
        refreshes += 1;
        return json(200, tokens(`a${refreshes}`));
      },
    );
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await vi.waitFor(() => expect(streams(seen)).toHaveLength(2));
    expect(streams(seen)[1]?.headers.get('Authorization')).toBe('Bearer a2');
    expect(getSession()?.accessToken).toBe('a2');
  });

  it('모두 캐릭터를 정했으면 방장이 시작한다', async () => {
    const ready = [member(ME, { is_host: true, character: { name: '렌', description: '' } })];
    open({
      [`GET ${BASE}`]: () => json(200, tableDetail(TABLE_ID, { members: ready, member_count: 1 })),
      [`POST ${BASE}/start`]: () => json(200, tableDetail(TABLE_ID, { members: ready, status: 'playing' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '시작하기' }));

    expect(await screen.findByText(/진행 중입니다/)).toBeInTheDocument();
  });

  it('나가면 로비로 간다', async () => {
    const { seen } = open({ [`DELETE ${BASE}/members/me`]: () => new Response(null, { status: 204 }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '나가기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '나가기' }));

    expect(await screen.findByRole('heading', { name: '테이블 로비' })).toBeInTheDocument();
    expect(seen.some((request) => request.method === 'DELETE')).toBe(true);
  });

  it('내보내지면 스트림이 멈추고 테이블을 다시 읽어 앉아 있지 않다고 알린다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}`]: () => {
        reads += 1;
        return reads === 1 ? json(200, tableDetail(TABLE_ID)) : json(404, { detail: '없다' });
      },
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('closed', { reason: 'not_seated' })], false),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('앉아 있지 않거나 없는 테이블입니다.', {}, { timeout: 3000 })).toBeInTheDocument();
  });
});
