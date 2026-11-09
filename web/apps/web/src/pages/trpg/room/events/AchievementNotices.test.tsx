// web/apps/web/src/pages/trpg/room/events/AchievementNotices.test.tsx
// 테이블 방의 "업적을 얻었다" 알림. 방금 닫힌 라운드에 받은 업적이 지금 라운드 위에 뜨는지, 스트림으로 온 것도 뜨는지,
// 닫기를 누르면 감추는지, 되돌린 라운드의 업적은 빠지는지를 본다. 고르는 순수한 함수(achievementNoticeView.ts)도 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { TableEvent } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { event, ME, member, OTHER, round, roomRoutes, sheet, sse, sseResponse, tableDetail } from '../../../../test/tableFixtures';
import { isRecentRound, receiversLine, recentAchievements, toEarnedAchievement } from './achievementNoticeView';

const TABLE_ID = '00000000-0000-4000-8000-0000000000c9';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const PICTURE = '00000000-0000-4000-8000-00000000e001';

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  members: [
    member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() }),
    member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
  ],
});

const USERS = [
  { user_id: ME, character_name: '렌' },
  { user_id: OTHER, character_name: '미아' },
];

function earned(sequence: number, roundNumber: number, name: string, extra: Record<string, unknown> = {}, meta: Record<string, unknown> = {}) {
  return event(sequence, 'achievement_earned', { round: roundNumber, achievement_id: name, name, description: '', image_id: null, users: USERS, ...extra }, meta);
}

function open(items: unknown[], routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/events`]: () => json(200, { items, last_sequence: items.length + 10 }),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(3)),
      [`GET ${BASE}/rounds`]: () => json(200, { items: [round(3)], total: 1 }),
      [`GET ${BASE}/portraits/${PICTURE}/image`]: () => new Response('png', { status: 200 }),
      ...routes,
    }),
  });
}

async function earnedList() {
  return within(await screen.findByRole('list', { name: '얻은 업적' }));
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('업적을 얻었다 알림', () => {
  it('방금 닫힌 라운드에 받은 업적이 지금 라운드 위에 그림과 받은 사람과 함께 뜬다. 더 앞의 것은 뜨지 않는다', async () => {
    open([earned(1, 1, '첫걸음'), earned(2, 2, '용을 깨운 자', { description: '잠든 용을 깨웠다', image_id: PICTURE })]);
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const list = await earnedList();
    expect(await list.findByText('업적을 얻었습니다: 용을 깨운 자')).toBeInTheDocument();
    expect(list.getByText('잠든 용을 깨웠다')).toBeInTheDocument();
    expect(list.getByText('받은 사람: 렌, 미아')).toBeInTheDocument();
    expect(await list.findByRole('img', { name: '용을 깨운 자의 그림' })).toBeInTheDocument();
    expect(list.queryByText('업적을 얻었습니다: 첫걸음')).toBeNull();
  });

  it('스트림으로 온 업적도 뜨고, 닫기를 누르면 감춘다', async () => {
    open([], {
      [`GET ${BASE}/stream`]: (request) => sseResponse(request, [sse('table_event', earned(21, 3, '종지기'), '21-0-0')]),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const list = await earnedList();
    expect(await list.findByText('업적을 얻었습니다: 종지기')).toBeInTheDocument();
    await userEvent.click(list.getByRole('button', { name: '종지기 알림 닫기' }));
    expect(screen.queryByRole('list', { name: '얻은 업적' })).toBeNull();
  });

  it('방장이 되돌린 라운드의 업적은 뜨지 않는다', async () => {
    open([
      earned(1, 2, '용을 깨운 자', {}, { action_group_id: 'g-closing' }),
      event(2, 'round_reverted', { number: 2, group: 'g-closing' }),
      earned(3, 3, '종지기', {}, { action_group_id: 'g-later' }),
    ]);
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const list = await earnedList();
    expect(await list.findByText('업적을 얻었습니다: 종지기')).toBeInTheDocument();
    expect(list.queryByText('업적을 얻었습니다: 용을 깨운 자')).toBeNull();
  });
});

describe('업적 알림 고르기', () => {
  const nameOf = (userId: string) => (userId === OTHER ? '모험가2' : '모험가');

  it('지금 라운드와 바로 앞 라운드의 것만 고른다', () => {
    expect(isRecentRound(3, 3)).toBe(true);
    expect(isRecentRound(2, 3)).toBe(true);
    expect(isRecentRound(1, 3)).toBe(false);
    expect(isRecentRound(null, 3)).toBe(false);
    expect(isRecentRound(2, null)).toBe(false);
    const events = [earned(1, 1, 'a'), event(2, 'hp_changed', { round: 2 }), earned(3, 2, 'b'), earned(4, 3, 'c')] as unknown as TableEvent[];
    expect(recentAchievements(events, 3, nameOf).map((one) => one.name)).toEqual(['b', 'c']);
  });

  it('캐릭터의 이름이 없으면 사람의 이름을 쓰고, 이름이 없는 업적은 띄우지 않는다', () => {
    const one = toEarnedAchievement(earned(5, 3, '종지기', { users: [{ user_id: OTHER, character_name: null }, { user_id: ME, character_name: '렌' }] }) as unknown as TableEvent, nameOf);
    expect(one).toEqual({ key: '5', name: '종지기', description: '', imageId: null, receivers: ['모험가2', '렌'] });
    expect(toEarnedAchievement(earned(6, 3, '', {}) as unknown as TableEvent, nameOf)).toBeNull();
    expect(receiversLine([])).toBe('이 테이블에서 받았습니다');
    expect(receiversLine(['렌', '미아'])).toBe('받은 사람: 렌, 미아');
  });
});
