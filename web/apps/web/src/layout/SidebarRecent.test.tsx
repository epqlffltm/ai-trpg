// web/apps/web/src/layout/SidebarRecent.test.tsx
// 왼쪽 메뉴 열의 최근 대화. 로그인 전에는 안내만 있고 부르지 않으며, 로그인하면 서비스마다 묶음(최근 세 줄, 전체 보기)이고
// 묶음 하나를 읽지 못해도 다른 묶음은 보인다. 때의 글(순수한 함수).

import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { relativeTime } from './sidebarRecentView';

const AT = new Date(Date.now() - 14 * 60_000).toISOString();

function conversation(id: string, title: string) {
  return { id, title, character: { id: 'c', name: '루나', image_id: null }, model: 'm', created_at: AT, updated_at: AT };
}

function table(id: string, title: string) {
  return { id, title, status: 'playing', member_count: 3, capacity: 4 };
}

describe('왼쪽 메뉴 열의 최근 대화', () => {
  it('로그인 전에는 안내 한 줄만 있고 목록을 부르지 않는다', async () => {
    const { seen } = installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: '없음' }) });
    renderApp('/board');

    const sidebar = await screen.findByRole('complementary', { name: '사이트 메뉴' });
    expect(within(sidebar).getByText('로그인하면 최근 대화가 여기 보입니다.')).toBeInTheDocument();
    expect(seen.some((request) => request.url.startsWith('/api/v1/chat/conversations'))).toBe(false);
  });

  it('로그인하면 서비스마다 최근 세 줄과 전체 보기가 있고, 하나를 읽지 못해도 다른 묶음은 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: 'u1' }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
      'GET /api/v1/game/tables': () => json(200, { items: [table('t1', '목요일 모임')], total: 1 }),
      'GET /api/v1/chat/conversations': () => json(200, { items: ['1', '2', '3', '4'].map((n) => conversation(n, `대화 ${n}`)), total: 4 }),
      'GET /api/v1/story/conversations': () => json(503, { detail: '잠시' }),
    });
    renderApp('/board');

    const sidebar = within(await screen.findByRole('complementary', { name: '사이트 메뉴' }));
    const chats = within(await sidebar.findByRole('list', { name: '최근 chat 대화' }));
    expect(chats.getAllByRole('link').map((link) => link.querySelector('.sidebar-recent__name')?.textContent)).toEqual(['대화 1', '대화 2', '대화 3']);
    expect(chats.getAllByText('루나 · 14분 전')).toHaveLength(3);
    expect(within(await sidebar.findByRole('list', { name: '최근 TRPG 테이블' })).getByRole('link', { name: /목요일 모임/ })).toHaveAttribute('href', '/trpg/tables/t1');
    expect(await sidebar.findByText('불러오지 못했습니다.')).toBeInTheDocument();
    expect(sidebar.getAllByRole('link', { name: '전체 보기' }).map((link) => link.getAttribute('href'))).toEqual(['/trpg', '/chat', '/story']);
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
