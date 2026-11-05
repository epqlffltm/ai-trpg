// web/apps/web/src/pages/trpg/room/snapshots/RoundSnapshots.test.tsx
// 테이블 방(B6)의 장면 그림(#983). 라운드의 장면 아래의 "장면 그림 · 160"으로 그 라운드를 그리고,
// 다 그린 그림을 게임 서버의 주소로 받아 그 라운드 아래에 띄운다. 남이 그린 것도 보이고, 내 것에는 "내가 그림"을 적는다.
// 남의 실패는 보이지 않는다. 그리는 중이면 단추를 막는다. 그릴 수 없는 서버면 단추를 숨긴다. 시작하지 못한 까닭을 알린다.
// 스트림의 scene_snapshot 이 오면 목록을 다시 읽는다(남이 그린 것이 곧 보인다).
// 내가 그린 그림만 크게 보는 창에서 한 번 더 확인한 뒤 지운다. 지우지 못하면 창 안에 까닭을 알린다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { TableSnapshot } from '../../../../api/tableSnapshots';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, round, roomRoutes, sheet, sse, tableDetail } from '../../../../test/tableFixtures';
import { snapshotsOfRound } from './tableSnapshotsView';

const TABLE_ID = '00000000-0000-4000-8000-0000000009b3';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const AT = '2026-11-05T03:00:00Z';
const S = (n: number) => `00000000-0000-4000-8000-00000000c9${n}0`;
const SELLING = { available: true, credits: '160', tier: 'standard', promo: false };

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  members: [
    member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
  ],
});

function snapshot(n: number, extra: Partial<TableSnapshot> = {}): TableSnapshot {
  return { id: S(n), round_number: 1, status: 'ready', by_me: false, code: null, created_at: AT, ...extra } as TableSnapshot;
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(1, { status: 'closed', waiting_for: [] }), round(2)], total: 2 }),
      'GET /api/v1/game/snapshots/price': () => json(200, SELLING),
      ...routes,
    }),
  });
}

/** 그 라운드의 글이 든 칸(라운드 하나의 article) */
async function roundOf(n: number) {
  return within((await screen.findByText(`${n}번째 장면`)).closest('article') as HTMLElement);
}

/** 붙은 뒤 LATER_MS 가 지나서 글 하나를 보내는 스트림. 요청이 끊길 때까지 닫지 않는다 */
const LATER_MS = 800;
function laterStream(request: SeenRequest, chunk: () => string): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(': connected\n\n'));
      const timer = setTimeout(() => controller.enqueue(encoder.encode(chunk())), LATER_MS);
      request.signal?.addEventListener('abort', () => {
        clearTimeout(timer);
        controller.error(new DOMException('aborted', 'AbortError'));
      });
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('테이블의 장면 그림', () => {
  it('라운드의 단추로 그 라운드를 그리고, 다 그린 그림을 그 라운드 아래에 띄운다', async () => {
    let list: TableSnapshot[] = [];
    const { seen } = open({
      [`GET ${BASE}/snapshots`]: () => json(200, list),
      [`POST ${BASE}/rounds/1/snapshot`]: () => {
        // 이 시험은 그리기를 기다리지 않는다. 받자마자 다 그린 것으로 둔다
        list = [snapshot(1, { by_me: true })];
        return json(202, { ...list[0], status: 'drawing' });
      },
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const first = await roundOf(1);
    await userEvent.click(await first.findByRole('button', { name: '장면 그림 · 160' }));

    await waitFor(() => expect(first.getByAltText('장면 그림')).toHaveAttribute('src', 'blob:image'));
    expect(first.getByText('AI 가 만든 그림 · 내가 그림')).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'POST' && request.url === `${BASE}/rounds/1/snapshot`)).toHaveLength(1);
  });

  it('남이 그린 그림도 보이고, 남의 실패는 보이지 않는다', async () => {
    open({
      [`GET ${BASE}/snapshots`]: () => json(200, [snapshot(1), snapshot(2, { status: 'failed', code: null })]),
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const first = await roundOf(1);

    expect(await first.findByText('AI 가 만든 그림')).toBeInTheDocument();
    expect(first.queryByText(/그림을 만들지 못했습니다/)).not.toBeInTheDocument();
  });

  it('그리는 중이면 모든 라운드의 단추를 막고, 내 실패는 까닭과 함께 보인다', async () => {
    open({
      [`GET ${BASE}/snapshots`]: () =>
        json(200, [snapshot(1, { status: 'failed', by_me: true, code: 'credit_short' }), snapshot(2, { round_number: 2, status: 'drawing', by_me: true })]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const first = await roundOf(1);
    const second = await roundOf(2);

    expect(await first.findByText('크레딧이 모자라 그리지 못했습니다.')).toBeInTheDocument();
    expect(second.getByText('장면 그림을 그리는 중…')).toBeInTheDocument();
    expect(await first.findByRole('button', { name: '장면 그림 · 160' })).toBeDisabled();
    expect(second.getByRole('button', { name: '장면 그림 · 160' })).toBeDisabled();
  });

  it('시작하지 못하면 그 라운드 아래에 까닭을 알린다', async () => {
    open({
      [`POST ${BASE}/rounds/2/snapshot`]: () => json(409, { detail: '그리는 중', code: 'snapshot_in_progress' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const second = await roundOf(2);
    await userEvent.click(await second.findByRole('button', { name: '장면 그림 · 160' }));

    expect(await second.findByText('이 테이블에서 다른 그림을 그리는 중입니다. 끝나면 다시 해 주세요.')).toBeInTheDocument();
    expect((await roundOf(1)).queryByText(/다른 그림을 그리는 중/)).not.toBeInTheDocument();
  });

  it('스트림의 scene_snapshot 이 오면 목록을 다시 읽어 남이 그린 그림을 띄운다', async () => {
    let announced = false;
    open({
      [`GET ${BASE}/snapshots`]: () => json(200, announced ? [snapshot(1)] : []),
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
      // 방이 붙고 처음 읽기를 마친 뒤에 알림이 온다. 붙을 때의 다시 읽기와 섞이지 않게 늦게 보낸다
      [`GET ${BASE}/stream`]: (request) => laterStream(request, () => {
        announced = true;
        return sse('scene_snapshot', {});
      }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const first = await roundOf(1);

    expect(await first.findByText('AI 가 만든 그림', {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('그릴 수 없는 서버면 단추를 숨긴다', async () => {
    open({ 'GET /api/v1/game/snapshots/price': () => json(200, { available: false, credits: null, tier: null, promo: false }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await roundOf(2);
    await waitFor(() => expect(screen.queryByRole('button', { name: /장면 그림/ })).not.toBeInTheDocument());
  });
});

describe('테이블의 장면 그림 지우기', () => {
  it('내 그림은 창에서 확인한 뒤 지우고, 창을 닫고 목록을 다시 읽는다', async () => {
    let list: TableSnapshot[] = [snapshot(1, { by_me: true })];
    const { seen } = open({
      [`GET ${BASE}/snapshots`]: () => json(200, list),
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
      [`DELETE ${BASE}/snapshots/${S(1)}`]: () => {
        list = [];
        return new Response(null, { status: 204 });
      },
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const first = await roundOf(1);
    await userEvent.click(await first.findByRole('button', { name: '장면 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    expect(dialog.getByText(/낸 크레딧은 돌려받지 못하고/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(first.queryByAltText('장면 그림')).not.toBeInTheDocument());
    expect(seen.filter((request) => request.method === 'DELETE')).toHaveLength(1);
  });

  it('남이 그린 그림에는 지우기가 없다', async () => {
    open({
      [`GET ${BASE}/snapshots`]: () => json(200, [snapshot(1)]),
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await (await roundOf(1)).findByRole('button', { name: '장면 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));

    expect(dialog.getByRole('button', { name: '이 기기에 저장' })).toBeInTheDocument();
    expect(dialog.queryByRole('button', { name: '지우기' })).not.toBeInTheDocument();
  });

  it('지우지 못하면 창 안에 까닭을 알리고 그림은 남는다', async () => {
    open({
      [`GET ${BASE}/snapshots`]: () => json(200, [snapshot(1, { by_me: true })]),
      [`GET ${BASE}/snapshots/${S(1)}/image`]: () => new Response('png', { status: 200 }),
      [`DELETE ${BASE}/snapshots/${S(1)}`]: () => json(409, { detail: '정리 중', code: 'snapshot_settling' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await (await roundOf(1)).findByRole('button', { name: '장면 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    expect(await dialog.findByText('청구를 정리하는 중입니다. 잠시 뒤에 다시 해 주세요.')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '장면 그림' })).toBeInTheDocument();
  });
});

describe('snapshotsOfRound', () => {
  it('그 라운드의 것만, 내 실패는 끝의 것만 남긴다', () => {
    const list = [
      snapshot(1, { status: 'failed', by_me: true, code: 'refused' }),
      snapshot(2),
      snapshot(3, { status: 'failed', by_me: true, code: 'credit_short' }),
      snapshot(4, { round_number: 2 }),
      snapshot(5, { status: 'failed' }),
    ];

    expect(snapshotsOfRound(list, 1).map((item) => item.id)).toEqual([S(2), S(3)]);
    expect(snapshotsOfRound(list, 2).map((item) => item.id)).toEqual([S(4)]);
  });
});
