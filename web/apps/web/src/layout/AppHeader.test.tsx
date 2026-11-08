// web/apps/web/src/layout/AppHeader.test.tsx
// 머리의 주 메뉴. 지금 있는 서비스만 aria-current 로 알리고, 그 아래 경로에 있어도 그 서비스다.
// 좁은 화면의 검색 아이콘. 검색칸을 펼치고 접으며(위쪽 줄의 data-searching), 검색 결과 화면에서는 늘 펼쳐 둔다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';

function signedOut() {
  installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
}

describe('머리의 주 메뉴', () => {
  it('서비스 밖(설정)에서는 어느 메뉴도 지금 있는 곳이 아니다', async () => {
    signedOut();
    renderApp('/settings');

    const nav = await screen.findByRole('navigation', { name: '주 메뉴' });
    for (const link of within(nav).getAllByRole('link')) expect(link).not.toHaveAttribute('aria-current');
  });

  it('서비스의 아래 경로에 있으면 그 서비스의 메뉴만 지금 있는 곳이다', async () => {
    signedOut();
    renderApp('/chat/characters/new');

    const nav = await screen.findByRole('navigation', { name: '주 메뉴' });
    expect(within(nav).getByRole('link', { name: 'chat' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'TRPG' })).not.toHaveAttribute('aria-current');
    expect(within(nav).getByRole('link', { name: 'story' })).not.toHaveAttribute('aria-current');
  });
});

describe('좁은 화면의 검색 아이콘', () => {
  it('누르면 검색칸을 펼치고 다시 누르면 접는다', async () => {
    signedOut();
    renderApp('/settings');

    const toggle = await screen.findByRole('button', { name: '검색칸 펼치기' });
    const header = toggle.closest('header') as HTMLElement;
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls', screen.getByRole('search', { name: '작품 검색' }).id);
    expect(header).toHaveAttribute('data-searching', 'false');

    await userEvent.click(toggle);
    expect(screen.getByRole('button', { name: '검색칸 접기' })).toHaveAttribute('aria-expanded', 'true');
    expect(header).toHaveAttribute('data-searching', 'true');

    await userEvent.click(screen.getByRole('button', { name: '검색칸 접기' }));
    expect(header).toHaveAttribute('data-searching', 'false');
  });

  it('검색 결과 화면에서는 검색칸이 펼쳐져 있고 아이콘은 없다', async () => {
    signedOut();
    renderApp('/search');

    const form = await screen.findByRole('search', { name: '작품 검색' });
    expect(form.closest('header')).toHaveAttribute('data-searching', 'true');
    expect(screen.queryByRole('button', { name: /^검색칸/ })).toBeNull();
  });
});
