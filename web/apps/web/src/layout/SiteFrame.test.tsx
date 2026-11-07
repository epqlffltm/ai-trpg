// web/apps/web/src/layout/SiteFrame.test.tsx
// 사이트의 틀(Stitch 설계서의 [모든 화면의 틀]). 왼쪽 메뉴 열의 이름·만들기·주 메뉴·공지, ☰ 로 접고 펴기,
// 플레이 화면에서 접은 채로 시작하는 것, 아래 탭 바의 탐색 창, 만들기의 입구를 본다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { CREATE_TARGETS, createPath } from '../pages/create/createTargets';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { ME } from '../test/tableFixtures';
import { isPlayPath } from './sidebarRoutes';

function signedOut() {
  installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
}

function signedIn() {
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('사이트의 틀', () => {
  it('왼쪽 메뉴 열에 이름, 만들기, 주 메뉴, 공지가 있고 ☰ 로 접고 편다', async () => {
    signedOut();
    renderApp('/settings');

    const sidebar = await screen.findByRole('complementary', { name: '사이트 메뉴' });
    expect(within(sidebar).getByRole('link', { name: /이매망량의 서재/ })).toHaveAttribute('href', '/');
    expect(within(sidebar).getByRole('link', { name: '만들기' })).toHaveAttribute('href', '/create');
    const nav = within(sidebar).getByRole('navigation', { name: '주 메뉴' });
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['홈', 'TRPG', 'chat', 'story', '게시판']);
    expect(within(sidebar).getByRole('link', { name: '공지' })).toHaveAttribute('href', '/board/notice');

    await userEvent.click(screen.getByRole('button', { name: '사이트 메뉴 접기' }));
    expect(screen.queryByRole('complementary', { name: '사이트 메뉴' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '사이트 메뉴 펼치기' }));
    expect(screen.getByRole('complementary', { name: '사이트 메뉴' })).toBeInTheDocument();
  });

  it('서비스 안에서는 그 서비스가 지금 있는 곳이고 홈은 아니다', async () => {
    signedOut();
    renderApp('/chat/characters/new');

    const nav = await screen.findByRole('navigation', { name: '주 메뉴' });
    expect(within(nav).getByRole('link', { name: 'chat' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: '홈' })).not.toHaveAttribute('aria-current');
  });

  it('아래 탭 바의 탐색은 서비스와 게시판으로 가는 창을 열고, 고르면 닫힌다', async () => {
    signedOut();
    renderApp('/settings');

    const bar = await screen.findByRole('navigation', { name: '아래 메뉴' });
    expect(within(bar).getByRole('link', { name: '만들기' })).toHaveAttribute('href', '/create');
    expect(within(bar).getByRole('link', { name: '마이' })).toHaveAttribute('href', '/me');
    await userEvent.click(within(bar).getByRole('button', { name: '탐색' }));
    const sheet = within(bar).getByRole('group', { name: '탐색' });
    expect(within(sheet).getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(['/trpg', '/chat', '/story', '/board']);

    await userEvent.click(within(sheet).getByRole('link', { name: '게시판' }));
    expect(within(bar).queryByRole('group', { name: '탐색' })).toBeNull();
  });

  it('만들기는 로그인해야 열리고, 고른 서비스의 제작 화면으로 간다. 고르기 전에는 다음이 꺼져 있다', async () => {
    signedIn();
    renderApp('/create');

    const form = within(await screen.findByRole('form', { name: '만들 것 고르기' }));
    expect(form.getByRole('button', { name: '다음' })).toBeDisabled();
    await userEvent.selectOptions(form.getByRole('combobox', { name: '무엇을 만들까요' }), 'chat');
    await userEvent.click(form.getByRole('button', { name: '다음' }));

    await waitFor(() => expect(screen.queryByRole('form', { name: '만들 것 고르기' })).toBeNull());
  });

  it('로그인하지 않았으면 만들기는 로그인으로 보낸다', async () => {
    signedOut();
    renderApp('/create');

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });
});

describe('틀의 순수한 함수', () => {
  it('플레이 화면(테이블 방, 대화, 장면)만 메뉴 열을 접은 채로 시작한다', () => {
    expect(isPlayPath('/trpg/tables/t1')).toBe(true);
    expect(isPlayPath('/chat/conversations/c1')).toBe(true);
    expect(isPlayPath('/story/sessions/s1')).toBe(true);
    expect(isPlayPath('/trpg/tables/new')).toBe(false);
    expect(isPlayPath('/trpg/tables/past')).toBe(false);
    expect(isPlayPath('/trpg/tables/past/t1')).toBe(false);
    expect(isPlayPath('/trpg')).toBe(false);
    expect(isPlayPath('/chat/characters/c1')).toBe(false);
  });

  it('만들기의 갈래는 셋이고 저마다 제작 화면이 있다', () => {
    expect(CREATE_TARGETS.map((one) => one.value)).toEqual(['trpg', 'chat', 'story']);
    expect(CREATE_TARGETS.map((one) => createPath(one.value, 'scenarios'))).toEqual(['/trpg/studio/scenarios/new', '/chat/studio/characters/new', '/story/studio/worlds/new']);
  });
});
