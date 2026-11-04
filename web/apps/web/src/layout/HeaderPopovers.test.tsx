// web/apps/web/src/layout/HeaderPopovers.test.tsx
// 위쪽 줄의 펼침 창. 알림 종(최근 알림, 모두 읽음, 모두 보기, 비었을 때)과 프로필 메뉴(잔액, 출석·충전, MY, 운영, 로그아웃),
// 창 밖을 누르거나 Esc 로 닫히는 것, 길을 누르면 닫히는 것을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { openAccountMenu } from '../test/accountMenu';
import { installFakeFetch, json, tokens, type SeenRequest } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { ME } from '../test/tableFixtures';
import { PANEL_SIZE } from './NotificationPanel';

const BOX = '/api/v1/notification/me/notifications';
const AT = '2026-11-04T01:00:00Z';

function notice(id: number, read = false) {
  return { id, source: 'billing', kind: 'credit.welcome', payload: { amount: String(id) }, read_at: read ? AT : null, created_at: AT };
}

function signedIn(items: ReturnType<typeof notice>[], routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '80', free: '10', total: '90', next_expiry: null }),
    [`GET ${BOX}/unread-count`]: () => json(200, { unread: items.filter((one) => one.read_at === null).length }),
    [`GET ${BOX}`]: () => json(200, { items, next_before: null }),
    [`POST ${BOX}/read-all`]: () => json(200, { updated: items.length }),
    'POST /api/v1/auth/logout': () => json(204, undefined),
    ...routes,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('알림 종', () => {
  it('누르면 최근 알림을 몇 개만 펼치고, 모두 보기는 알림 화면으로 가며 창을 닫는다', async () => {
    const items = Array.from({ length: PANEL_SIZE + 2 }, (_, index) => notice(20 - index));
    signedIn(items);
    renderApp('/settings');

    const bell = await screen.findByRole('button', { name: `알림, 읽지 않은 것 ${items.length}개` });
    expect(bell).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(bell);
    const panel = within(await screen.findByRole('region', { name: '알림 창' }));
    expect(await panel.findAllByRole('listitem')).toHaveLength(PANEL_SIZE);
    expect(bell).toHaveAttribute('aria-expanded', 'true');

    await userEvent.click(panel.getByRole('link', { name: '모두 보기' }));
    expect(await screen.findByRole('heading', { name: '알림', level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '알림 창' })).toBeNull();
  });

  it('알림의 길을 누르면 그 화면으로 가며 창을 닫는다. 읽음 단추는 닫지 않는다', async () => {
    signedIn([notice(12), notice(11)], { [`POST ${BOX}/12/read`]: () => json(200, notice(12, true)) });
    renderApp('/settings');

    await userEvent.click(await screen.findByRole('button', { name: /^알림, 읽지 않은 것/ }));
    let panel = within(await screen.findByRole('region', { name: '알림 창' }));
    const [first] = await panel.findAllByRole('listitem');
    await userEvent.click(within(first!).getByRole('button', { name: /^읽음:/ }));
    expect(screen.getByRole('region', { name: '알림 창' })).toBeInTheDocument();

    panel = within(screen.getByRole('region', { name: '알림 창' }));
    const [second] = panel.getAllByRole('listitem');
    await userEvent.click(within(second!).getByRole('link'));
    expect(screen.queryByRole('region', { name: '알림 창' })).toBeNull();
  });

  it('모두 읽음은 창에 보인 가장 새 번호까지 보낸다', async () => {
    const { seen } = signedIn([notice(12), notice(11)]);
    renderApp('/settings');

    await userEvent.click(await screen.findByRole('button', { name: /^알림, 읽지 않은 것/ }));
    const panel = within(await screen.findByRole('region', { name: '알림 창' }));
    await userEvent.click(await panel.findByRole('button', { name: '모두 읽음' }));

    await vi.waitFor(() =>
      expect(seen.filter((request) => request.method === 'POST' && request.url === `${BOX}/read-all`).map((request) => request.body)).toEqual([{ up_to: 12 }]),
    );
  });

  it('알림이 없으면 없다고 하고, 창 밖을 누르거나 Esc 로 닫힌다', async () => {
    signedIn([]);
    renderApp('/settings');

    await userEvent.click(await screen.findByRole('button', { name: '알림' }));
    expect(await screen.findByText('새 알림이 없습니다.')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('region', { name: '알림 창' })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '알림' }));
    expect(await screen.findByRole('region', { name: '알림 창' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('heading', { name: '설정' }));
    expect(screen.queryByRole('region', { name: '알림 창' })).toBeNull();
  });
});

describe('프로필 메뉴', () => {
  it('닉네임, 잔액, 출석·충전, MY 의 길을 펼친다. 길을 누르면 닫힌다', async () => {
    signedIn([]);
    renderApp('/settings');

    const menu = await openAccountMenu();
    expect(menu.getByText('모험가')).toBeInTheDocument();
    expect(await menu.findByRole('link', { name: '지갑: 골드 80 · 실버 10' })).toHaveAttribute('href', '/wallet');
    expect(menu.getByRole('link', { name: '출석' })).toHaveAttribute('href', '/wallet/attendance');
    expect(menu.getByRole('link', { name: '충전' })).toHaveAttribute('href', '/wallet/charge');
    const my = within(menu.getByRole('list', { name: 'MY' }));
    expect(my.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(['/me', '/me/hearts', '/me/personas', '/gallery', '/settings']);
    expect(menu.queryByRole('list', { name: '운영' })).toBeNull();

    await userEvent.click(my.getByRole('link', { name: '설정' }));
    expect(screen.queryByRole('navigation', { name: '내 메뉴' })).toBeNull();
  });

  it('로그아웃하면 첫 화면으로 가고 로그인 전의 위쪽 줄이다', async () => {
    const { seen } = signedIn([], {
      'GET /api/v1/game/tables/mine': () => json(200, { tables: [] }),
    });
    renderApp('/settings');

    const menu = await openAccountMenu();
    await userEvent.click(menu.getByRole('button', { name: '로그아웃' }));

    expect(await screen.findByRole('link', { name: '로그인' })).toBeInTheDocument();
    expect(seen.some((request) => request.method === 'POST' && request.url === '/api/v1/auth/logout')).toBe(true);
  });
});
