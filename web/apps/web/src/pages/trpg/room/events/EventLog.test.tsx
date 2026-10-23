// web/apps/web/src/pages/trpg/room/events/EventLog.test.tsx
// 일어난 일(④-2). 상태 패널의 탭(L)에 읽어 둔 끝부분과 스트림으로 온 것이 최근 것부터 보이는지,
// 번호가 많을 때 끝부분만 읽는지, 이번 라운드의 서술을 막는 일이 지금 라운드 위의 알림으로 뜨는지,
// 스트림이 읽어 둔 끝 번호부터 받는지를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { event, ME, member, OTHER, round, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000c8';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  members: [
    member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
  ],
});

const TAIL = {
  items: [
    event(7, 'table_started', { members: [] }, { actor_id: ME }),
    event(8, 'round_opened', { number: 1, clock: { day: 1, hour: 22, minute: 0 } }),
    event(9, 'gm_narration', { text: '비가 온다.' }),
    event(10, 'items_gained', { round: 1, character_name: '미아', name: '횃불', count: 1, total: 1, source: 'place', place: { name: '수도원 문' } }),
  ],
  last_sequence: 10,
};

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/events`]: () => json(200, TAIL),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      ...routes,
    }),
  });
}

async function logTab() {
  const status = within(await screen.findByRole('region', { name: '상태' }));
  await userEvent.click(status.getByRole('tab', { name: /일어난 일/ }));
  return within(await status.findByRole('list', { name: /일어난 일/ }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('일어난 일', () => {
  it('읽어 둔 끝부분과 스트림으로 온 것을 최근 것부터 한 줄씩 보인다. 서술은 빠진다', async () => {
    const { seen } = open({
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [sse('table_event', event(11, 'hp_changed', { round: 2, character_name: '렌', before: 10, after: 6 }), '11-0-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const log = await logTab();
    expect(await log.findByText('렌: HP 10 → 6')).toBeInTheDocument();
    const lines = log.getAllByRole('listitem').map((item) => item.textContent);
    expect(lines).toEqual(['R2렌: HP 10 → 6', 'R1미아: 횃불 ×1 얻음(지금 1) · 수도원 문에서', 'R1라운드 1: 열림 · 1일째 22:00', '테이블을 시작했습니다.']);
    expect(log.queryByText(/비가 온다/)).not.toBeInTheDocument();
    const stream = seen.find((request) => request.url.startsWith(`${BASE}/stream`));
    expect(stream?.url).toContain('events_after=10');
  });

  it('번호가 많으면 끝의 100개만 읽고, 앞의 것은 보이지 않는다고 알린다', async () => {
    const { seen } = open({
      [`GET ${BASE}/events`]: (request) =>
        request.url.includes('limit=1&') || request.url.endsWith('limit=1')
          ? json(200, { items: [event(1, 'table_created')], last_sequence: 250 })
          : json(200, { items: [event(151, 'member_joined', {}, { actor_id: OTHER })], last_sequence: 250 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const log = await logTab();
    expect(await log.findByText('미아: 들어왔습니다.')).toBeInTheDocument();
    expect(screen.getByText('그 앞의 일은 여기에 보이지 않습니다.')).toBeInTheDocument();
    const reads = seen.filter((request) => request.url.startsWith(`${BASE}/events`)).map((request) => request.url);
    expect(reads).toContainEqual(expect.stringContaining('after=150'));
  });

  it('L 키로 연다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.keyboard('l');
    expect(status.getByRole('tab', { name: /일어난 일/ })).toHaveAttribute('aria-selected', 'true');
    expect(await status.findByText('테이블을 시작했습니다.')).toBeInTheDocument();
  });

  it('이번 라운드에 크레딧이 모자란 사람이 있으면 지금 라운드 위에 알린다. 지난 라운드의 것은 알리지 않는다', async () => {
    open({
      [`GET ${BASE}/events`]: () =>
        json(200, {
          items: [...TAIL.items, event(11, 'narration_credits_short', { round: 1, user_id: ME, reason: 'credits' })],
          last_sequence: 11,
        }),
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [sse('table_event', event(12, 'narration_credits_short', { round: 2, user_id: OTHER, reason: 'credits' }), '12-0-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('미아: 크레딧이 모자라 서술하지 못합니다.');
    expect(screen.queryByText(/렌: 크레딧이 모자라/)).not.toBeInTheDocument();
  });
});
