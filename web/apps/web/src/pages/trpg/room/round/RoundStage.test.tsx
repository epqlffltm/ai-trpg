// web/apps/web/src/pages/trpg/room/round/RoundStage.test.tsx
// 진행 중인 테이블의 라운드(B6 의 ③). 지난 라운드와 지금 라운드, 판정을 붙인 선언, 고치기, 마감한 뒤의 결과,
// 서술의 미리 보기와 끝, 방장의 닫기, 그 사이 마감했을 때를 본다.

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

  it('판정을 붙여 선언하면 낸 것이 보이고, 고칠 수 있다', async () => {
    const mine = declaration(ME, {
      content: '문을 밀어 연다',
      action: { kind: 'check', ability: 'str', difficulty: 'easy', lethal: false },
    });
    const { seen } = open({
      [`PUT ${BASE}/rounds/current/declaration`]: () => json(200, round(2, { declarations: [mine], waiting_for: [OTHER] })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '문을 밀어 연다');
    await userEvent.selectOptions(form.getByLabelText('행동'), '판정');
    await userEvent.selectOptions(form.getByLabelText('난이도'), '쉬움(10)');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

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
    let reads = 0;
    let releaseStale: (() => void) | undefined;
    open({
      // 첫 읽기는 바로, 두 번째(스트림이 붙은 뒤의 묶은 읽기)는 선언을 낸 뒤까지 붙잡아 둔다
      [`GET ${BASE}/rounds/current`]: (() => {
        reads += 1;
        if (reads === 1) return json(200, round(2));
        return new Promise<Response>((resolve) => {
          releaseStale = () => resolve(json(200, round(2)));
        });
      }) as unknown as () => Response,
      [`PUT ${BASE}/rounds/current/declaration`]: () => json(200, round(2, { declarations: [mine], waiting_for: [OTHER] })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const form = within(await screen.findByRole('form', { name: '선언' }));
    await vi.waitFor(() => expect(reads).toBe(2));
    await userEvent.type(form.getByLabelText('무엇을 하나요'), '기다린다');
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));
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
    expect(screen.getByText('눈 9, 보정 +1, 합 10 / 목표 15 · 실패')).toBeInTheDocument();
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
    await userEvent.click(form.getByRole('button', { name: '선언하기' }));

    expect(await screen.findByText(/결과를 서술하는 중입니다/)).toBeInTheDocument();
    expect(reads).toBeGreaterThanOrEqual(2);
  });
});
