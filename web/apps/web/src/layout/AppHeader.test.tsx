// web/apps/web/src/layout/AppHeader.test.tsx
// 머리의 주 메뉴. 지금 있는 서비스만 aria-current 로 알리고, 그 아래 경로에 있어도 그 서비스다.

import { screen, within } from '@testing-library/react';
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
