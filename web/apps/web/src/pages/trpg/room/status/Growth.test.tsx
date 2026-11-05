// web/apps/web/src/pages/trpg/room/status/Growth.test.tsx
// 성장(#286)을 화면으로 본다. 왼쪽 열(상태·장비, 일행·기록)의 레벨과 경험치, 쌓인 점수를 능력치에 놓기(POST abilities), 409 의 알림,
// 라운드가 닫는 중이면 막힘, 성장이 없는 규칙이면 그리지 않음.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, RULES, round, roomRoutes, sheet, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000ea';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const PROGRESSION = { levels: [{ xp: 100, max_hp: 2, points: 1 }, { xp: 300, max_hp: 2, points: 2 }] };
const GROWN = { xp: 150, level: 2, next_level_xp: 300, points: 2 };

function playing(mine: Record<string, unknown> = GROWN, progression: unknown = PROGRESSION) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    rules: { ...RULES, progression },
    members: [
      member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet(mine) }),
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet({ xp: 40, level: 1, next_level_xp: 100, points: 0 }) }),
    ],
  });
}

function open(table = playing(), routes: Record<string, (request: SeenRequest) => Response> = {}, status = 'open') {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, table),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { status })),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(2)], total: 1 }),
      ...routes,
    }),
  });
}

async function statusPanel() {
  return within(await screen.findByRole('region', { name: '상태' }));
}

function sent(seen: SeenRequest[]): SeenRequest[] {
  return seen.filter((request) => request.method === 'POST' && request.url === `${BASE}/abilities`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('성장', () => {
  it('내 레벨과 경험치, 놓지 않은 점수를 상태·장비에, 앉은 사람마다의 레벨을 일행·기록에 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await statusPanel();
    expect(await status.findAllByText('레벨 2 · 경험치 150 / 300')).toHaveLength(1);
    expect(status.getAllByText('놓지 않은 능력치 점수 2').length).toBeGreaterThan(0);
    await userEvent.click(status.getByRole('button', { name: /일행·기록/ }));
    expect(status.getByText('레벨 2 · 경험치 150 / 300')).toBeInTheDocument();
    expect(status.getByText('레벨 1 · 경험치 40 / 100')).toBeInTheDocument();
  });

  it('창에서 능력치를 골라 올리면 POST 로 보내고 받은 테이블로 바꾼다. 남은 점수와 상한을 넘게는 고르지 못한다', async () => {
    const after = playing({ xp: 150, level: 2, next_level_xp: 300, points: 0, abilities: { str: 15, dex: 12, con: 11 } });
    const { seen } = open(playing({ ...GROWN, abilities: { str: 14, dex: 12, con: 10 } }), { [`POST ${BASE}/abilities`]: () => json(200, after) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await statusPanel();
    await userEvent.click(await status.findByRole('button', { name: '능력치 올리기 (2)' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: '올리기' })).toBeDisabled();
    expect(dialog.getByRole('button', { name: '근력 내리기' })).toBeDisabled();
    await userEvent.click(dialog.getByRole('button', { name: '근력 올리기' }));
    await userEvent.click(dialog.getByRole('button', { name: '건강 올리기' }));
    expect(dialog.getByText('남은 점수 0 / 2. 한 점이 능력치 1 입니다. 놓은 점수는 되돌릴 수 없습니다.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '민첩 올리기' })).toBeDisabled();
    expect(dialog.getByText('근력 14 → 15, 건강 10 → 11')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '올리기' }));

    await vi.waitFor(() => expect(sent(seen)).toHaveLength(1));
    expect(sent(seen)[0]?.body).toEqual({ raises: { str: 1, con: 1 } });
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(status.queryByRole('button', { name: /능력치 올리기/ })).toBeNull();
  });

  it('서버가 막으면 까닭을 창에 알린다', async () => {
    open(playing(), { [`POST ${BASE}/abilities`]: () => json(409, { detail: 'x', reason: 'not_enough_points' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await statusPanel();
    await userEvent.click(await status.findByRole('button', { name: '능력치 올리기 (2)' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '민첩 올리기' }));
    await userEvent.click(dialog.getByRole('button', { name: '올리기' }));

    expect(await dialog.findByText('남은 점수가 모자랍니다.')).toBeInTheDocument();
  });

  it('라운드가 닫는 중이면 단추가 꺼져 있다', async () => {
    open(playing(), {}, 'closing');
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await statusPanel();
    expect(await status.findByRole('button', { name: '능력치 올리기 (2)' })).toBeDisabled();
  });

  it('성장이 없는 규칙이면 레벨도 단추도 그리지 않는다', async () => {
    open(playing(GROWN, null));
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await statusPanel();
    expect((await status.findAllByText('렌')).length).toBeGreaterThan(0);
    expect(status.queryByText(/레벨 2/)).toBeNull();
    expect(status.queryByRole('button', { name: /능력치 올리기/ })).toBeNull();
  });
});
