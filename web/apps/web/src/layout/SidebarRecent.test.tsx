// web/apps/web/src/layout/SidebarRecent.test.tsx
// 왼쪽 메뉴 열의 최근 대화. 로그인 전에는 안내와 로그인 단추만 있고 부르지 않으며, 로그인하면 세 서비스를 섞어 최근 것부터 한 목록이고
// 하나를 읽지 못해도 읽은 것은 보인다. 섞기와 거르기, 때의 글(순수한 함수).

import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { filterRecent, mergeRecent, relativeTime, type RecentRow } from './sidebarRecentView';

const NOW = Date.now();
const minutesAgo = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString();

function conversation(id: string, title: string, minutes: number) {
  const at = minutesAgo(minutes);
  return { id, title, character: { id: 'c', name: '루나', image_id: null }, model: 'm', created_at: at, updated_at: at };
}

function table(id: string, title: string, minutes: number) {
  return { id, title, status: 'playing', member_count: 3, capacity: 4, created_at: minutesAgo(minutes) };
}

describe('왼쪽 메뉴 열의 최근 대화', () => {
  it('로그인 전에는 안내와 로그인 단추만 있고 목록을 부르지 않는다', async () => {
    const { seen } = installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: '없음' }) });
    renderApp('/board');

    const sidebar = within(await screen.findByRole('complementary', { name: '사이트 메뉴' }));
    expect(sidebar.getByText('로그인하고 이어서 하기')).toBeInTheDocument();
    expect(sidebar.getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
    expect(seen.some((request) => request.url.startsWith('/api/v1/chat/conversations'))).toBe(false);
  });

  it('로그인하면 세 서비스를 섞어 최근 것부터 한 목록이고, 줄마다 종류 칩이 있다. 하나를 읽지 못해도 읽은 것은 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: 'u1' }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
      'GET /api/v1/game/tables': () => json(200, { items: [table('t1', '목요일 모임', 30)], total: 1 }),
      'GET /api/v1/chat/conversations': () => json(200, { items: [conversation('1', '대화 1', 14), conversation('2', '대화 2', 60)], total: 2 }),
      'GET /api/v1/story/conversations': () => json(503, { detail: '잠시' }),
    });
    renderApp('/board');

    const sidebar = within(await screen.findByRole('complementary', { name: '사이트 메뉴' }));
    const list = within(await sidebar.findByRole('list', { name: '최근 대화 목록' }));
    const links = list.getAllByRole('link');
    expect(links.map((link) => link.querySelector('.sidebar-recent__name')?.textContent)).toEqual(['대화 1', '목요일 모임', '대화 2']);
    expect(links[0]).toHaveAttribute('href', '/chat/conversations/1');
    expect(links[1]).toHaveAttribute('href', '/trpg/tables/t1');
    expect(links.map((link) => link.querySelector('.sidebar-recent__kind')?.textContent)).toEqual(['캐릭터', 'TRPG', '캐릭터']);
    expect(within(links[0] as HTMLElement).getByText('14분 전')).toBeInTheDocument();
    expect(await sidebar.findByText('일부를 불러오지 못했어요.')).toBeInTheDocument();
    expect(sidebar.queryByRole('link', { name: '전체 보기' })).toBeNull();
  });
});

function row(id: string, kind: RecentRow['kind'], at: string, name = id): RecentRow {
  return { id, kind, to: `/${id}`, name, detail: '', at };
}

describe('최근 대화 섞기', () => {
  it('때가 늦은 것부터 늘어놓고 정한 줄 수만 남긴다. 때를 읽지 못한 줄은 맨 뒤', () => {
    const merged = mergeRecent(
      [[row('t', 'trpg', '2026-11-09T10:00:00Z')], [row('c', 'character', '2026-11-09T12:00:00Z'), row('x', 'character', '')], [row('s', 'story', '2026-11-09T11:00:00Z')]],
      3,
    );
    expect(merged.map((item) => item.id)).toEqual(['c', 's', 't']);
  });

  it('종류와 검색어로 거른다', () => {
    const rows = [row('a', 'trpg', '', '목요일 모임'), row('b', 'character', '', '루나와 차'), row('c', 'story', '', '안개항')];
    expect(filterRecent(rows, 'character', '').map((item) => item.id)).toEqual(['b']);
    expect(filterRecent(rows, null, '안개').map((item) => item.id)).toEqual(['c']);
    expect(filterRecent(rows, null, '').map((item) => item.id)).toEqual(['a', 'b', 'c']);
  });
});

describe('최근 대화의 때', () => {
  it('방금, 분, 시간, 일, 그보다 오래면 날짜', () => {
    const now = Date.parse('2026-11-09T12:00:00Z');
    expect(relativeTime('2026-11-09T11:59:30Z', now)).toBe('방금');
    expect(relativeTime('2026-11-09T11:46:00Z', now)).toBe('14분 전');
    expect(relativeTime('2026-11-09T09:00:00Z', now)).toBe('3시간 전');
    expect(relativeTime('2026-11-07T12:00:00Z', now)).toBe('2일 전');
    expect(relativeTime('2026-10-01T12:00:00Z', now)).toContain('2026년');
    expect(relativeTime('nonsense', now)).toBe('nonsense');
  });
});
