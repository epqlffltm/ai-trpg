// web/apps/web/src/pages/trpg/room/status/StatusPanel.test.tsx
// 진행 중인 테이블의 왼쪽 열 창 넷(B7, Stitch 20번). 처음 펼친 상태·장비의 내 HP, 일행·기록의 부상과 쓰러짐, 소지품, 퀘스트와 지도,
// 창이 하나만 펼쳐지는 것과 다시 누르면 접히는 것, 단축키, 이벤트가 오면 다시 읽기를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000c7';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function playing(mySheet: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    members: [
      member(OTHER, {
        character: { name: '미아', description: '' },
        sheet: sheet({ hp: 0, death_successes: 1, injuries: [{ injury: 'sprain', round: 2, ends_after_round: 3, heals_at: null }] }),
      }),
      member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet(mySheet) }),
    ],
    items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', effects: [{ kind: 'heal', magnitude: 'light' }] }],
    quests: [
      { entry_id: 'q1', name: '사라진 수도사', status: 'active', due_at: { day: 2, hour: 6, minute: 0, time_of_day: 'dawn' } },
      { entry_id: 'q2', name: '종을 울려라', status: 'succeeded', due_at: null },
    ],
    map: {
      places: [
        {
          entry_id: 'p1',
          name: '수도원 문',
          items: [{ entry_id: 'i2', name: '횃불', count: 1 }],
          traps: [{ trap_id: 't1', entry_id: 'i9', name: '올가미' }],
        },
        { entry_id: 'p2', name: '부엌', items: [] },
      ],
      routes: [{ from_place: 'p1', to_place: 'p2', travel_minutes: 5, two_way: true }],
    },
    ...extra,
  });
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () =>
        json(200, playing({ place_id: 'p1', items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', count: 2 }] })),
      ...routes,
    }),
  });
}

async function panel() {
  return within(await screen.findByRole('region', { name: '상태' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('StatusPanel', () => {
  it('처음에는 상태·장비가 펼쳐져 내 캐릭터만 보인다. 일행·기록은 앉은 사람의 쓰러짐과 부상을 나부터 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await panel();
    expect(status.getByRole('button', { name: /상태·장비/ })).toHaveAttribute('aria-expanded', 'true');
    expect(status.getAllByText('HP 12 / 12')).toHaveLength(1);
    expect(status.queryByText('미아')).toBeNull();

    await userEvent.click(status.getByRole('button', { name: /일행·기록/ }));

    expect(status.getByRole('button', { name: /상태·장비/ })).toHaveAttribute('aria-expanded', 'false');
    expect(status.getByText(/쓰러짐 · 죽음의 굴림 성공 1\/3 · 실패 0\/3/)).toBeInTheDocument();
    expect(status.getByText('(라운드 3까지)')).toBeInTheDocument();
    const names = status.getAllByText(/^(렌|미아)$/).map((node) => node.textContent);
    expect(names).toEqual(['렌', '미아']);
  });

  it('펼친 창의 단추를 다시 누르면 접혀 아무 창도 펼쳐져 있지 않다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = await panel();
    await userEvent.click(status.getByRole('button', { name: /상태·장비/ }));

    expect(status.getAllByRole('button', { expanded: false })).toHaveLength(4);
    expect(status.queryByText('HP 12 / 12')).toBeNull();
  });

  it('소지품·돈은 물건과 개수, 회복량을 보인다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click((await panel()).getByRole('button', { name: /소지품·돈/ }));

    const mine = within(screen.getByRole('region', { name: '렌의 소지품' }));
    expect(mine.getByText('×2')).toBeInTheDocument();
    expect(mine.getByText('소모품 · 보통 · 회복 가벼움(1d4)')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '미아의 소지품' })).getByText('지닌 물건이 없습니다.')).toBeInTheDocument();
  });

  it('J 를 누르면 퀘스트·지도를 펼친다. 글을 쓰는 중에는 단축키가 아니다', async () => {
    open();
    renderApp(`/trpg/tables/${TABLE_ID}`);
    const status = await panel();

    await userEvent.type(screen.getByLabelText('채팅 쓰기'), 'j');
    expect(status.getByRole('button', { name: /상태·장비/ })).toHaveAttribute('aria-expanded', 'true');

    screen.getByLabelText('채팅 쓰기').blur();
    await userEvent.keyboard('j');

    expect(status.getByRole('button', { name: /퀘스트·지도/ })).toHaveAttribute('aria-expanded', 'true');
    expect(status.getByText('1일째 08:00 · 아침')).toBeInTheDocument();
    expect(status.getByText('진행 중 · 기한 2일째 06:00')).toBeInTheDocument();
    expect(status.getByText(/지금 있는 곳: 수도원 문/)).toBeInTheDocument();
    expect(within(status.getByRole('list', { name: '여기 놓인 것' })).getByText(/횃불 ×1/)).toBeInTheDocument();
    // 찾아낸 덫(#806 ①-b)과 해제
    expect(within(status.getByRole('list', { name: '찾아낸 덫' })).getByText(/올가미/)).toBeInTheDocument();
    expect(within(status.getByRole('list', { name: '갈 수 있는 곳' })).getByText('부엌')).toBeInTheDocument();
  });

  it('이벤트가 오면 테이블을 다시 읽어 HP 를 바꾼다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}`]: () => {
        reads += 1;
        return json(200, playing(reads >= 2 ? { hp: 5 } : {}));
      },
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('table_event', { sequence: 4, type: 'hp_changed' }, '4-0-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await (await panel()).findAllByText('HP 5 / 12', {}, { timeout: 3000 })).toHaveLength(1);
  });

  it('맵이 없는 판이면 장소를 숨긴다', async () => {
    open({ [`GET ${BASE}`]: () => json(200, playing({}, { map: null })) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click((await panel()).getByRole('button', { name: /퀘스트·지도/ }));
    expect(screen.queryByRole('heading', { name: '장소' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '퀘스트' })).toBeInTheDocument();
  });
});
