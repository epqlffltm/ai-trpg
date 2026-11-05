// web/apps/web/src/pages/trpg/room/Whisper.test.tsx
// 테이블 방의 대화창의 쪽지 탭(Stitch 20번). 지난 쪽지와 "나 → 미아"의 머리, 받는 사람을 골라 보내기(같은 번호는 한 번만),
// 스트림이 붙는 쪽지의 번호, 채팅 탭에 있을 때 나에게 온 쪽지의 안 읽은 수와 쪽지 탭을 열면 지워지는 것,
// 보내지 못한 까닭, 끝난 테이블, 순수한 함수를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { Whisper } from '../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, sse, sseResponse, tableDetail } from '../../../test/tableFixtures';
import { unreadLabel } from './RoomTalk';
import { mergeWhispers, nextUnreadWhispers, routeMessage } from './streamPolicy';
import { whisperRoute } from './WhisperPanel';

const TABLE_ID = '00000000-0000-4000-8000-0000000000d4';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function whisper(sequence: number, from: string, to: string, content: string): Whisper {
  return {
    sequence,
    sender_id: from,
    recipient_id: to,
    sender_character_name: from === ME ? '렌' : '미아',
    recipient_character_name: to === ME ? '렌' : '미아',
    content,
    gm_visible: false,
    round: 1,
    created_at: '2026-11-05T01:00:00Z',
  };
}

const TABLE = tableDetail(TABLE_ID, {
  members: [member(ME, { is_host: true, character: { name: '렌', description: '' } }), member(OTHER, { character: { name: '미아', description: '' } })],
});

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, { [`GET ${BASE}`]: () => json(200, TABLE), ...routes }),
  });
}

async function whisperTab() {
  await userEvent.click(await screen.findByRole('tab', { name: /^쪽지/ }));
  return within(await screen.findByRole('region', { name: '쪽지' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('쪽지 탭', () => {
  it('지난 쪽지를 보이고, 받는 사람을 골라 보낸다. 스트림이 같은 것을 다시 줘도 한 번만 보인다', async () => {
    const sent = whisper(3, ME, OTHER, '문 뒤를 봐');
    const { seen } = open({
      [`GET ${BASE}/whispers`]: () => json(200, { items: [whisper(1, OTHER, ME, '조심해'), whisper(2, ME, OTHER, '알았어')], last_sequence: 2 }),
      [`POST ${BASE}/whispers`]: () => json(201, sent),
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, []),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await whisperTab();
    const list = within(await panel.findByRole('list', { name: '주고받은 쪽지' }));
    expect(list.getByText('미아 → 나')).toBeInTheDocument();
    expect(list.getByText('나 → 미아')).toBeInTheDocument();

    const send = panel.getByRole('button', { name: '보내기' });
    await userEvent.type(panel.getByLabelText('쪽지 쓰기'), '문 뒤를 봐');
    expect(send).toBeDisabled();
    await userEvent.selectOptions(panel.getByLabelText('받는 사람'), OTHER);
    await userEvent.click(send);

    expect(await list.findByText('문 뒤를 봐')).toBeInTheDocument();
    const posted = seen.find((request) => request.method === 'POST' && request.url === `${BASE}/whispers`);
    expect(posted?.body).toEqual({ recipient_id: OTHER, content: '문 뒤를 봐' });
    expect(panel.getByLabelText('쪽지 쓰기')).toHaveValue('');
  });

  it('스트림은 읽은 쪽지의 마지막 번호로 붙는다', async () => {
    const { seen } = open({
      [`GET ${BASE}/whispers`]: () => json(200, { items: [whisper(4, OTHER, ME, '안녕')], last_sequence: 4 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await vi.waitFor(() => expect(seen.some((request) => request.url.startsWith(`${BASE}/stream`))).toBe(true));
    const stream = seen.find((request) => request.url.startsWith(`${BASE}/stream`));
    expect(new URL(stream?.url ?? '', 'http://x').searchParams.get('whispers_after')).toBe('4');
  });

  it('채팅 탭에 있을 때 나에게 온 쪽지를 안 읽은 수로 세고, 쪽지 탭을 열면 지운다', async () => {
    open({
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [sse('whisper', whisper(1, OTHER, ME, '몰래 말해'), '3-0-1'), sse('whisper', whisper(2, ME, OTHER, '응'), '3-0-2')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('tab', { name: '쪽지, 안 읽은 것 1개' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: '채팅' })).toHaveAttribute('aria-selected', 'true');

    const panel = await whisperTab();
    expect(await panel.findByText('몰래 말해')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '쪽지' })).toHaveAttribute('aria-selected', 'true');
  });

  it('받는 사람이 떠났으면 그 까닭을 알린다', async () => {
    open({ [`POST ${BASE}/whispers`]: () => json(404, { detail: '참가자를 찾을 수 없습니다.' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await whisperTab();
    await userEvent.selectOptions(panel.getByLabelText('받는 사람'), OTHER);
    await userEvent.type(panel.getByLabelText('쪽지 쓰기'), '있어?{Enter}');

    expect(await panel.findByText(/받는 사람이 테이블을 떠났거나/)).toBeInTheDocument();
  });

  it('끝난 테이블에서는 읽기만 한다', async () => {
    open({ [`GET ${BASE}`]: () => json(200, { ...TABLE, status: 'ended', ended_at: '2026-11-05T02:00:00Z' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await whisperTab();
    expect(await panel.findByText('주고받은 쪽지가 없습니다.')).toBeInTheDocument();
    expect(panel.queryByLabelText('쪽지 쓰기')).toBeNull();
  });
});

describe('쪽지의 순수한 함수', () => {
  it('스트림의 whisper 를 쪽지로 보낸다', () => {
    const data = whisper(1, OTHER, ME, '안녕');
    expect(routeMessage({ event: 'whisper', data: JSON.stringify(data), id: '1-0-1' })).toEqual({ kind: 'whisper', whisper: data });
  });

  it('번호 차례로 합치고 같은 번호는 한 번만 둔다', () => {
    const merged = mergeWhispers([whisper(2, ME, OTHER, 'b')], [whisper(1, OTHER, ME, 'a'), whisper(2, ME, OTHER, 'b')]);
    expect(merged.map((one) => one.sequence)).toEqual([1, 2]);
  });

  it('보고 있지 않을 때 나에게 온 것만 센다', () => {
    expect(nextUnreadWhispers(0, whisper(1, OTHER, ME, 'a'), ME, false)).toBe(1);
    expect(nextUnreadWhispers(1, whisper(2, ME, OTHER, 'b'), ME, false)).toBe(1);
    expect(nextUnreadWhispers(1, whisper(3, OTHER, ME, 'c'), ME, true)).toBe(1);
    expect(nextUnreadWhispers(0, whisper(4, OTHER, ME, 'd'), undefined, false)).toBe(0);
  });

  it('머리는 나를 "나"로, 다른 사람은 캐릭터의 이름으로 적는다. 탭의 이름에 안 읽은 수를 붙인다', () => {
    expect(whisperRoute(whisper(1, OTHER, ME, 'a'), [], ME, () => undefined)).toBe('미아 → 나');
    expect(unreadLabel('쪽지', 0)).toBe('쪽지');
    expect(unreadLabel('쪽지', 3)).toBe('쪽지, 안 읽은 것 3개');
  });
});
