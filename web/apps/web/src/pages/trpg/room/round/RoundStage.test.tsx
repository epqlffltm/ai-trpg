// web/apps/web/src/pages/trpg/room/round/RoundStage.test.tsx
// 진행 중인 테이블의 라운드(B6 의 ③). 지난 라운드와 지금 라운드, 판정을 붙인 선언, 고치기, 마감한 뒤의 결과,
// 서술의 미리 보기와 끝, 방장의 닫기와 되돌리기(#288), 그 사이 마감했을 때, 차례대로 진행하는 테이블(#287)을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { declaration, ME, member, OTHER, round, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000b7';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  members: [
    member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
  ],
});

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(1, { status: 'closed', waiting_for: [] }), round(2)], total: 2 }),
      ...routes,
    }),
  });
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === `${BASE}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RoundStage', () => {
  it('지난 라운드와 지금 라운드의 장면, 아직 선언하지 않은 사람을 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('2번째 장면')).toBeInTheDocument();
    expect(screen.getByText('1번째 장면')).toBeInTheDocument();
    expect(screen.getByText('아직 선언하지 않은 사람: 렌, 미아')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '라운드 닫기' })).toBeInTheDocument();
  });

  it('마감이 있으면 라운드 줄에 마감 시각과 남은 시간을 보인다', async () => {
    const deadline = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    open({ [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { deadline_at: deadline })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText(/^마감 (오전|오후) \d{1,2}:\d{2}$/)).toBeInTheDocument();
    expect(screen.getByText(/^남은 시간 \d+분( \d+초)?$/)).toBeInTheDocument();
  });

  it('판정을 붙여 선언하면 낸 것이 보이고, 고칠 수 있다', async () => {
    const mine = declaration(ME, {
      content: '문을 밀어 연다',
      action: { kind: 'check', ability: 'str', difficulty: 'easy', lethal: false },
    });
    // 낸 뒤의 라운드 읽기도 낸 선언을 돌려준다(진짜 서버처럼). 선언하면 화면이 라운드를 다시 읽는데,
    // 처음 라운드를 계속 돌려주면 그 읽기가 "고치기"를 누르는 때와 겹쳐 빈 입력이 열린다(CI 에서 가끔 실패했다)
    const declared = round(2, { declarations: [mine], waiting_for: [OTHER] });
    let current = round(2);
    const { seen } = open({
      [`GET ${BASE}/rounds/current`]: () => json(200, current),
      [`PUT ${BASE}/rounds/current/declaration`]: () => {
        current = declared;
        return json(200, declared);
      },
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '문을 밀어 연다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '판정');
    await userEvent.selectOptions(form.getByLabelText('난이도'), '쉬움(10)');
    await userEvent.click(form.getByRole('button', { name: '선언 보내기' }));

    expect(await screen.findByText('판정 · 근력, 쉬움')).toBeInTheDocument();
    expect(sent(seen, 'PUT', '/rounds/current/declaration')[0]?.body).toEqual({
      content: '문을 밀어 연다',
      action: { kind: 'check', ability: 'str', difficulty: 'easy', lethal: false },
    });
    expect(screen.getByText('아직 선언하지 않은 사람: 미아')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '고치기' }));
    expect(within(screen.getByRole('form', { name: '선언' })).getByLabelText('무엇을 하나요')).toHaveValue('문을 밀어 연다');
  });

  it('선언을 내는 동안 시작한 라운드 읽기가 늦게 돌아와도 낸 선언을 덮지 않는다', async () => {
    const mine = declaration(ME, { content: '기다린다', action: null });
    const declared = round(2, { declarations: [mine], waiting_for: [OTHER] });
    let reads = 0;
    let sent = false;
    let releaseStale: (() => void) | undefined;
    open({
      // 첫 읽기는 바로, 두 번째(스트림이 붙은 뒤의 묶은 읽기)는 선언을 낸 뒤까지 붙잡아 둔다(선언 전의 라운드다).
      // 선언을 받은 뒤의 읽기는 서버처럼 낸 선언이 든 라운드를 준다(멈춘 읽기를 대신해 다시 읽는다)
      [`GET ${BASE}/rounds/current`]: (() => {
        reads += 1;
        if (reads === 1) return json(200, round(2));
        if (sent) return json(200, declared);
        return new Promise<Response>((resolve) => {
          releaseStale = () => resolve(json(200, round(2)));
        });
      }) as unknown as () => Response,
      [`PUT ${BASE}/rounds/current/declaration`]: () => {
        sent = true;
        return json(200, declared);
      },
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await vi.waitFor(() => expect(reads).toBe(2));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '기다린다');
    await userEvent.click(form.getByRole('button', { name: '선언 보내기' }));
    expect(await screen.findByRole('button', { name: '고치기' })).toBeInTheDocument();

    releaseStale?.();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole('button', { name: '고치기' })).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '선언' })).not.toBeInTheDocument();
  });

  it('마감한 라운드는 모두의 선언과 판정 결과를 보이고, 쓰이는 서술을 이어 보이다가 끝나면 지운다', async () => {
    let reads = 0;
    const closing = round(2, {
      status: 'closing',
      waiting_for: [],
      declarations: [
        declaration(OTHER, {
          content: '창문으로 숨어든다',
          action: { kind: 'check', ability: 'dex', difficulty: null, lethal: false },
          outcome: { roll: 9, modifier: 1, total: 10, target: 15, success: false },
        }),
      ],
    });
    open({
      [`GET ${BASE}/rounds/current`]: () => {
        reads += 1;
        return json(200, reads === 1 ? closing : round(3));
      },
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [
          sse('narration_preview', { round: 2, attempt: 1, seq: 0, text: '창틀이 ' }),
          sse('narration_preview', { round: 2, attempt: 1, seq: 1, text: '삐걱인다.' }),
        ]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('판정 · 민첩, 보통')).toBeInTheDocument();
    expect(screen.getByText('눈 9, 보정 +1, 합 10 / 목표 15')).toBeInTheDocument();
    expect(screen.getByText('판정 실패')).toBeInTheDocument();
    expect(await screen.findByText('창틀이 삐걱인다.')).toBeInTheDocument();
  });

  it('서술이 끝났다는 이벤트가 오면 미리 보기를 지우고 다음 라운드를 읽는다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}/rounds/current`]: () => {
        reads += 1;
        return json(200, reads === 1 ? round(2, { status: 'closing', waiting_for: [] }) : round(3));
      },
      [`GET ${BASE}/stream`]: (request) =>
        sseResponse(request, [
          sse('narration_preview', { round: 2, attempt: 1, seq: 0, text: '미리 쓴 글' }),
          sse('table_event', { sequence: 4, type: 'gm_narration' }, '4-0-0'),
          sse('table_event', { sequence: 5, type: 'round_opened' }, '5-0-0'),
        ]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('3번째 장면', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText('미리 쓴 글')).not.toBeInTheDocument();
  });

  it('방장이 한 번 더 묻고 라운드를 닫는다', async () => {
    const { seen } = open({
      [`POST ${BASE}/rounds/current/close`]: () => json(202, round(2, { status: 'closing', waiting_for: [] })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '라운드 닫기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '마감하기' }));

    expect(await screen.findByText(/결과를 서술하는 중입니다/)).toBeInTheDocument();
    expect(sent(seen, 'POST', '/rounds/current/close')).toHaveLength(1);
  });

  it('차례대로의 테이블에서 남의 차례면 누구의 차례인지 보이고, 방장은 그 차례를 건너뛴다', async () => {
    const turn = round(3, { cycle: 2, actor_id: OTHER, waiting_for: [OTHER] });
    const { seen } = open({
      [`GET ${BASE}`]: () => json(200, { ...PLAYING, turn_mode: 'turns' }),
      [`GET ${BASE}/rounds/current`]: () => json(200, turn),
      [`POST ${BASE}/rounds/current/close`]: () => json(202, { ...turn, status: 'closing', waiting_for: [] }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('2바퀴 · 미아의 차례')).toBeInTheDocument();
    expect(screen.getByText('지금은 미아의 차례입니다. 자기 차례에 선언합니다.')).toBeInTheDocument();
    expect(screen.queryByText(/아직 선언하지 않은 사람/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '선언 보내기' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '차례 건너뛰기' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/미아의 선언을 기다리지 않고/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: '건너뛰기' }));

    expect(await screen.findByText(/결과를 서술하는 중입니다/)).toBeInTheDocument();
    expect(sent(seen, 'POST', '/rounds/current/close')).toHaveLength(1);
  });

  it('차례대로의 테이블에서 내 차례면 선언 칸이 열린다', async () => {
    open({
      [`GET ${BASE}`]: () => json(200, { ...PLAYING, turn_mode: 'turns' }),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { cycle: 1, actor_id: ME, waiting_for: [ME] })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('1바퀴 · 렌의 차례')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '선언 보내기' })).toBeInTheDocument();
  });

  it('서술에 실패한 라운드는 방장에게 다시 맡기기를 보인다', async () => {
    open({
      [`GET ${BASE}/rounds/current`]: () =>
        json(200, round(2, { status: 'closing', waiting_for: [], narration_failed_at: '2026-10-22T00:00:00Z', narration_failures: 2 })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText(/서술에 실패했습니다\(2번\)/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '서술 다시 맡기기' })).toBeInTheDocument();
  });

  it('그 사이 마감했으면 알리고 라운드를 다시 읽는다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}/rounds/current`]: () => {
        reads += 1;
        return json(200, reads === 1 ? round(2) : round(2, { status: 'closing', waiting_for: [] }));
      },
      [`PUT ${BASE}/rounds/current/declaration`]: () => json(409, { detail: 'x', reason: 'round_closing' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '기다린다');
    await userEvent.click(form.getByRole('button', { name: '선언 보내기' }));

    expect(await screen.findByText(/결과를 서술하는 중입니다/)).toBeInTheDocument();
    expect(reads).toBeGreaterThanOrEqual(2);
  });

  it('방장이 한 번 더 묻고 바로 앞 라운드를 되돌리면 그 라운드가 그때의 선언으로 다시 열린다', async () => {
    const reopened = round(1, { declarations: [declaration(ME, { content: '문을 밀어 연다' })], waiting_for: [OTHER] });
    const { seen } = open({ [`POST ${BASE}/rounds/current/revert`]: () => json(200, reopened) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '1 라운드 되돌리기' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/서술 값은 돌려주지 않습니다/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '되돌리기' }));

    expect(await screen.findByRole('heading', { name: /^라운드 1/ })).toBeInTheDocument();
    expect(screen.getByText('아직 선언하지 않은 사람: 미아')).toBeInTheDocument();
    expect(sent(seen, 'POST', '/rounds/current/revert')).toHaveLength(1);
  });

  it('첫 라운드에는 되돌릴 앞 라운드가 없어 되돌리기를 보이지 않는다', async () => {
    open({
      [`GET ${BASE}/rounds/current`]: () => json(200, round(1)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(1)], total: 1 }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('button', { name: '라운드 닫기' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /라운드 되돌리기$/ })).not.toBeInTheDocument();
  });

  it('그 사이 다른 일이 있어 되돌릴 수 없으면 까닭을 알린다', async () => {
    open({ [`POST ${BASE}/rounds/current/revert`]: () => json(409, { detail: 'x', reason: 'revert_blocked' }) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '1 라운드 되돌리기' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '되돌리기' }));

    expect(await screen.findByText(/선언이나 다른 일이 있어 되돌릴 수 없습니다/)).toBeInTheDocument();
  });

  it('누가 선언한 라운드에는 되돌리기를 보이지 않는다', async () => {
    open({ [`GET ${BASE}/rounds/current`]: () => json(200, round(2, { declarations: [declaration(OTHER)], waiting_for: [ME] })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByRole('button', { name: '라운드 닫기' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '1 라운드 되돌리기' })).not.toBeInTheDocument();
  });
});
