// web/apps/web/src/pages/trpg/room/Dice.test.tsx
// 테이블 방의 대화창의 주사위 탭(#404). 빠른 단추와 직접 적는 칸으로 굴리기(보내는 본문), 최근 굴림(이벤트와 스트림),
// 읽지 못하는 설명, 굴리는 수를 넘었을 때의 기다림, 끝난 테이블, 순수한 함수를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { TableEvent } from '../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { event, ME, member, OTHER, roomRoutes, sse, sseResponse, tableDetail } from '../../../test/tableFixtures';
import { readableDice, recentRolls } from './diceForm';

const TABLE_ID = '00000000-0000-4000-8000-0000000000d5';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

const TABLE = tableDetail(TABLE_ID, {
  members: [member(ME, { is_host: true, character: { name: '렌', description: '' } }), member(OTHER, { character: { name: '미아', description: '' } })],
});

function rolled(sequence: number, userId: string, name: string, dice: string, faces: number[], bonus: number) {
  const total = faces.reduce((sum, face) => sum + face, 0) + bonus;
  return event(sequence, 'dice_rolled', { user_id: userId, character_name: name, dice, faces, bonus, total }, { actor_id: userId });
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, { [`GET ${BASE}`]: () => json(200, TABLE), ...routes }),
  });
}

async function diceTab() {
  await userEvent.click(await screen.findByRole('tab', { name: '주사위' }));
  return within(await screen.findByRole('region', { name: '주사위' }));
}

function posted(seen: SeenRequest[]) {
  return seen.filter((request) => request.method === 'POST' && request.url === `${BASE}/dice`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('주사위 탭', () => {
  it('빠른 단추와 직접 적은 설명으로 굴린다. 최근 굴림은 이벤트에서 읽고 스트림이 더한다', async () => {
    const { seen } = open({
      [`GET ${BASE}/events`]: () => json(200, { items: [rolled(2, OTHER, '미아', 'd20', [17], 0)], last_sequence: 3 }),
      [`POST ${BASE}/dice`]: (request) => json(201, { sequence: 4, user_id: ME, character_name: '렌', dice: (request.body as { dice: string }).dice, faces: [3, 4], bonus: 1, total: 8 }),
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('table_event', rolled(4, ME, '렌', '2d6+1', [3, 4], 1), '4-0-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await diceTab();
    const list = within(await panel.findByRole('list', { name: '최근 굴림' }));
    expect(await list.findByText('2d6+1 굴림 → 3+4+1 = 8')).toBeInTheDocument();
    expect(list.getByText('d20 굴림 → 17 = 17')).toBeInTheDocument();

    await userEvent.click(panel.getByRole('button', { name: 'd20' }));
    const field = panel.getByLabelText('주사위 설명');
    const send = panel.getByRole('button', { name: '굴리기' });
    await userEvent.type(field, '2d7');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(send).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, ' 2D6+1 ');
    await userEvent.click(send);

    await vi.waitFor(() => expect(posted(seen)).toEqual([{ dice: 'd20' }, { dice: '2D6+1' }]));
    expect(field).toHaveValue('');
  });

  it('굴리는 수를 넘으면 기다릴 시간을 알리고 단추를 끈다', async () => {
    open({ [`POST ${BASE}/dice`]: () => json(429, { detail: '시도가 너무 많습니다.' }, { 'Retry-After': '30' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await diceTab();
    await userEvent.click(panel.getByRole('button', { name: 'd6' }));

    expect(await panel.findByText(/30초 뒤에 다시 시도하세요/)).toBeInTheDocument();
    expect(panel.getByRole('button', { name: 'd6' })).toBeDisabled();
  });

  it('끝난 테이블에서는 최근 굴림만 보인다', async () => {
    open({ [`GET ${BASE}`]: () => json(200, { ...TABLE, status: 'ended', ended_at: '2026-11-08T02:00:00Z' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await diceTab();
    expect(await panel.findByText('끝난 테이블에서는 굴릴 수 없습니다.')).toBeInTheDocument();
    expect(panel.queryByLabelText('주사위 설명')).toBeNull();
  });
});

describe('주사위의 순수한 함수', () => {
  it('서버와 같은 모양과 상한으로 본다', () => {
    expect(['d20', '2d6+1', ' 3D8-2 ', '10d100+100'].map(readableDice)).toEqual([true, true, true, true]);
    expect(['', '20', 'd7', '0d6', '11d6', '2d6+101', '2d6+1d4', 'd20'.padEnd(17, ' ') + '+1'].map(readableDice)).toEqual([
      false, false, false, false, false, false, false, false,
    ]);
  });

  it('최근 굴림은 새것이 위이고, 내 것을 가린다', () => {
    const events = [rolled(1, OTHER, '미아', 'd20', [5], 0), event(2, 'chat_message'), rolled(3, ME, '렌', 'd4', [2], 0)] as unknown as TableEvent[];
    const rolls = recentRolls(events, ME, () => '누군가');
    expect(rolls.map((roll) => [roll.sequence, roll.who, roll.mine])).toEqual([
      [3, '렌', true],
      [1, '미아', false],
    ]);
    expect(recentRolls(events, ME, () => '누군가', 1)).toHaveLength(1);
  });
});
