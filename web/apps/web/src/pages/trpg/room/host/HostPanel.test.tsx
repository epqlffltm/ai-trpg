// web/apps/web/src/pages/trpg/room/host/HostPanel.test.tsx
// 방장의 운영(B6 의 ⑤). 방장에게만 보이기, 내보내기와 새 초대 코드, 방장 넘기기, 설정 바꾸기, 한 번 더 굴리기, 끝내기, 실패를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, roll, roomRoutes, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e5';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function waiting(extra: Record<string, unknown> = {}, other: Record<string, unknown> = {}) {
  return tableDetail(TABLE_ID, {
    members: [
      member(ME, { is_host: true, character: { name: '렌', description: '' } }),
      member(OTHER, { character: { name: '미아', description: '' }, ...other }),
    ],
    recommended_narration_style: 'classic',
    ...extra,
  });
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}, me = ME) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: me }),
    ...roomRoutes(TABLE_ID, { [`GET ${BASE}`]: () => json(200, waiting()), ...routes }),
  });
}

async function hostPanel() {
  const summary = await screen.findByText('방장', { selector: 'h2' });
  await userEvent.click(summary);
  return within(summary.closest('details') as HTMLElement);
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === `${BASE}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('HostPanel', () => {
  it('방장이 아니면 보이지 않는다', async () => {
    open({}, OTHER);
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(screen.queryByText('방장', { selector: 'h2' })).not.toBeInTheDocument();
  });

  it('내보내면 한 번 더 묻고, 새 초대 코드를 알린다', async () => {
    const { seen } = open({
      [`DELETE ${BASE}/members/${OTHER}`]: () =>
        json(200, waiting({ members: [member(ME, { is_host: true })], invite_code: 'NEW999' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.click(panel.getByRole('button', { name: '미아 내보내기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '내보내기' }));

    expect(await screen.findByText(/새 초대 코드는 NEW999입니다/)).toBeInTheDocument();
    expect(sent(seen, 'DELETE', `/members/${OTHER}`)).toHaveLength(1);
  });

  it('방장을 넘기면 패널이 사라진다', async () => {
    const { seen } = open({
      [`PUT ${BASE}/host`]: () => json(200, waiting({ host_id: OTHER })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.click(panel.getByRole('button', { name: '미아에게 방장 넘기기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '넘기기' }));

    await vi.waitFor(() => expect(screen.queryByText('방장', { selector: 'h2' })).not.toBeInTheDocument());
    expect(sent(seen, 'PUT', '/host')[0]?.body).toEqual({ user_id: OTHER });
  });

  it('설정을 고르면 바로 보낸다', async () => {
    const { seen } = open({
      [`PUT ${BASE}/round-time-limit`]: () => json(200, waiting({ round_time_limit: 600 })),
      [`PUT ${BASE}/credit-wait`]: () => json(200, waiting({ remove_short_payers: false })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.selectOptions(panel.getByLabelText('라운드 시간 제한'), '10분');
    await vi.waitFor(() => expect(panel.getByLabelText('라운드 시간 제한')).toHaveValue('600'));
    await userEvent.click(panel.getByRole('checkbox', { name: '기다려도 모자라면 그 사람을 빼고 서술하기' }));

    expect(sent(seen, 'PUT', '/round-time-limit')[0]?.body).toEqual({ round_time_limit: 600 });
    await vi.waitFor(() =>
      expect(sent(seen, 'PUT', '/credit-wait')[0]?.body).toEqual({ credit_wait_seconds: 300, remove_short_payers: false }),
    );
  });

  it('굴린 사람에게 "한 번 더 굴리기"를 준다', async () => {
    const { seen } = open({
      [`GET ${BASE}`]: () => json(200, waiting({}, { roll: roll([15, 12, 9]) })),
      [`POST ${BASE}/members/${OTHER}/reroll`]: () =>
        json(200, waiting({}, { roll: roll([15, 12, 9], { reroll_granted: true }) })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.click(panel.getByRole('button', { name: '미아에게 한 번 더 굴리기' }));

    await vi.waitFor(() => expect(panel.queryByRole('button', { name: '미아에게 한 번 더 굴리기' })).not.toBeInTheDocument());
    expect(sent(seen, 'POST', `/members/${OTHER}/reroll`)).toHaveLength(1);
  });

  it('테이블을 끝내면 끝난 테이블이 된다', async () => {
    open({
      [`POST ${BASE}/end`]: () => json(200, waiting({ status: 'ended' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.click(panel.getByRole('button', { name: '테이블 끝내기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '끝내기' }));

    expect(await screen.findByText(/끝난 테이블입니다/)).toBeInTheDocument();
    expect(screen.queryByText('방장', { selector: 'h2' })).not.toBeInTheDocument();
  });

  it('그 사이 방장이 바뀌었으면 알리고 다시 읽는다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}`]: () => {
        reads += 1;
        return json(200, reads === 1 ? waiting() : waiting({ host_id: OTHER }));
      },
      [`PUT ${BASE}/whisper-notice`]: () => json(403, { detail: '방장이 아니다' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await hostPanel();
    await userEvent.click(panel.getByRole('checkbox', { name: '쪽지 알림' }));

    await vi.waitFor(() => expect(screen.queryByText('방장', { selector: 'h2' })).not.toBeInTheDocument());
    expect(reads).toBeGreaterThanOrEqual(2);
  });
});
