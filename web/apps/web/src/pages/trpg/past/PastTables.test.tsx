// web/apps/web/src/pages/trpg/past/PastTables.test.tsx
// 떠난 테이블(B10). 홈에서 떠난 테이블로, 목록(떠난 길), 떠난 때까지의 이야기(라운드의 머리 아래 장면, 선언, 판정, 일어난 일),
// 이어 읽기와 끝, 기록 받기(떠난 테이블의 주소), 떠난 적 없는 테이블. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import { REFRESH_PATH } from '../../../api/refresh';
import type { TableEvent } from '../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { event, ME } from '../../../test/tableFixtures';
import { pastProblemText } from './pastProblem';
import { checkLine, departureLabel, pastStory } from './pastStory';

const TABLE_ID = '00000000-0000-4000-8000-0000000000c9';
const PAST = '/api/v1/game/tables/past';
const HOST = '00000000-0000-4000-8000-0000000000e2';

const ROW = { table_id: TABLE_ID, scenario_id: TABLE_ID, title: '안개 낀 종탑', character_name: '렌', kind: 'kicked', last_sequence: 8, left_at: '2026-10-24T03:00:00Z' };

const FIRST = [
  event(1, 'table_started', { members: [] }),
  event(2, 'gm_narration', { text: '비가 내리는 밤, 종탑 아래에 선다.' }),
  event(3, 'round_opened', { number: 1 }),
  event(4, 'player_action', { round: 1, character_name: '렌', content: '문을 민다', action: { kind: 'check' } }),
  event(5, 'check_rolled', { round: 1, character_name: '렌', roll: 13, modifier: 2, total: 15, target: 15, success: true }),
];
const SECOND = [
  event(6, 'gm_narration', { text: '문이 열리고 계단이 보인다.' }),
  event(7, 'round_opened', { number: 2 }),
  event(8, 'member_kicked', { user_id: ME, character_name: '렌' }, { actor_id: HOST }),
];

function signedIn(eventsAnswer?: (request: SeenRequest) => Response) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/game/tables': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/chat/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: HOST, nickname: '방장' }] }),
    [`GET ${PAST}`]: () => json(200, { items: [ROW], total: 1 }),
    [`GET ${PAST}/${TABLE_ID}/events`]:
      eventsAnswer ??
      ((request) => (new URL(request.url, 'http://x').searchParams.get('after') === '5' ? json(200, { items: SECOND, last_sequence: 8 }) : json(200, { items: FIRST, last_sequence: 8 }))),
    [`GET ${PAST}/${TABLE_ID}/transcript`]: () => json(429, { detail: 'x' }, { 'Retry-After': '30' }),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('떠난 테이블', () => {
  it('홈에서 목록으로 가고, 떠난 때까지의 이야기를 처음부터 읽고, 이어 읽어 떠난 데서 끝난다', async () => {
    const { seen } = signedIn();
    renderApp('/');

    await userEvent.click(await screen.findByRole('link', { name: '떠난 테이블' }));
    const list = within(await screen.findByRole('list', { name: '떠난 테이블' }));
    expect(await list.findByText(/렌 · 방장이 내보냄/)).toBeInTheDocument();
    await userEvent.click(list.getByRole('link', { name: '안개 낀 종탑' }));

    expect(await screen.findByRole('heading', { name: '안개 낀 종탑' })).toBeInTheDocument();
    const story = within(screen.getByRole('region', { name: '이야기' }));
    expect(within(await story.findByRole('article', { name: '라운드 1' })).getByText('비가 내리는 밤, 종탑 아래에 선다.')).toBeInTheDocument();
    expect(story.getByText(/문을 민다/)).toBeInTheDocument();
    expect(story.getByText('렌: 눈 13, 보정 +2, 합 15 / 목표 15 · 성공')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '이어 읽기' }));
    expect(within(await story.findByRole('article', { name: '라운드 2' })).getByText('문이 열리고 계단이 보인다.')).toBeInTheDocument();
    expect(story.getByText('렌: 방장이 내보냈습니다.')).toBeInTheDocument();
    expect(screen.getByText('여기서 떠났습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '이어 읽기' })).toBeNull();
    expect(seen.some((request) => request.url.endsWith(`/events?after=5&limit=100`))).toBe(true);
  });

  it('기록 받기는 떠난 테이블의 주소로 부른다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/tables/past/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '기록 받기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '기록 받기' }));
    expect(dialog.getByText(/떠난 때까지의 서술/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '글(.txt)' }));
    expect(await dialog.findByText(/30초 뒤에 다시 받아 주세요/)).toBeInTheDocument();
    expect(seen.some((request) => request.url === `${PAST}/${TABLE_ID}/transcript?format=txt`)).toBe(true);
  });

  it('떠난 적 없는 테이블이면 까닭을 적는다', async () => {
    signedIn(() => json(404, { detail: 'x' }));
    renderApp(`/trpg/tables/past/${TABLE_ID}`);
    expect(await screen.findByText(/떠난 기록이 없는 테이블입니다/)).toBeInTheDocument();
  });
});

describe('떠난 테이블의 순수한 함수', () => {
  it('서술과 이어지는 라운드를 하나로, 따로 있는 서술, 규칙을 모르면 부상은 이름표 그대로', () => {
    const ctx = { table: { rules: null, currency: null }, nameOfMember: () => '누군가', modelName: (slug: string) => slug };
    const events = [
      ...FIRST.slice(1, 3),
      event(9, 'injury_gained', { round: 1, character_name: '렌', injury: 'broken_arm' }),
      event(10, 'gm_narration', { text: '끝.' }),
    ] as unknown as TableEvent[];
    const blocks = pastStory(events, ctx);
    expect(blocks.map((block) => block.kind)).toEqual(['round', 'line', 'narration']);
    expect(blocks[1]).toMatchObject({ text: '렌: broken_arm 입음' });
    expect(checkLine({ character_name: '미아', roll: 3, modifier: -1, total: 2, target: 10, success: false })).toBe('미아: 눈 3, 보정 -1, 합 2 / 목표 10 · 실패');
    expect(departureLabel('dropped')).toBe('크레딧이 모자라 빠짐');
    expect(pastProblemText(new ApiError({ status: 500, detail: 'x' }))).toContain('불러오지 못했습니다');
  });
});
