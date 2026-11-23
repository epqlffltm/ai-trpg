// web/apps/web/src/pages/conversations/Conversations.test.tsx
// 내 채팅 화면(/conversations). 맨 아래 탭 바와 왼쪽 열의 "내 채팅"이 이 화면으로 가고, 로그인해야 열리며,
// 왼쪽 메뉴 열과 같은 섞은 한 목록을 줄을 늘려 보이고 종류 칩과 검색으로 거른다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const AT = new Date(Date.now() - 14 * 60_000).toISOString();

function conversation(n: number) {
  return { id: `c${n}`, title: `대화 ${n}`, character: { id: 'x', name: '루나', image_id: null }, model: 'm', created_at: AT, updated_at: AT };
}

function signedIn() {
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: 'u1' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/game/tables': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/game/tables/past': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/chat/conversations': () => json(200, { items: Array.from({ length: 12 }, (_, index) => conversation(index + 1)), total: 12 }),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
  });
}

describe('내 채팅 화면', () => {
  it('탭 바와 왼쪽 열의 내 채팅이 이 화면을 가리키고, 섞은 한 목록을 종류 칩과 검색으로 거른다', async () => {
    signedIn();
    renderApp('/conversations');

    const main = within(await screen.findByRole('main'));
    expect(await main.findByRole('heading', { level: 1, name: '내 채팅' })).toBeInTheDocument();
    const list = within(await main.findByRole('list', { name: '내 채팅 목록' }));
    expect(list.getAllByRole('link')).toHaveLength(12);
    expect(list.getByRole('link', { name: /^대화 1, 루나, 캐릭터,/ })).toHaveAttribute('href', '/chat/conversations/c1');
    expect(main.queryByRole('link', { name: '전체 보기' })).toBeNull();

    await userEvent.click(main.getByRole('button', { name: 'TRPG' }));
    expect(await main.findByText('맞는 대화가 없어요.')).toBeInTheDocument();
    await userEvent.click(main.getByRole('button', { name: '전체' }));
    await userEvent.type(main.getByRole('searchbox', { name: '대화 검색' }), '대화 12');
    expect(within(main.getByRole('list', { name: '내 채팅 목록' })).getAllByRole('link')).toHaveLength(1);

    const bar = within(screen.getByRole('navigation', { name: '아래 메뉴' }));
    expect(bar.getByRole('link', { name: '내 채팅' })).toHaveAttribute('href', '/conversations');
    expect(bar.getByRole('link', { name: '내 채팅' })).toHaveAttribute('aria-current', 'page');
  });

  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: '없음' }) });
    renderApp('/conversations');

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });
});
