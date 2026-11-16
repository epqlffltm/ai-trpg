// web/apps/web/src/pages/create/Create.test.tsx
// 만들기의 입구(Stitch 12번): 작품 카드 넷과 재료 카드 넷이 저마다 새로 만드는 화면으로 가고,
// 스토리 세계의 "JSON 으로 세계관 넣기"는 운영자에게만 보이며, 내 작품으로 가는 길이 있는지 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

function signedIn(roles: string[] = []) {
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: 'u1' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
  });
}

async function cards(name: string) {
  renderApp('/create');
  return within(await screen.findByRole('list', { name }));
}

describe('만들기의 입구', () => {
  it('작품 카드 넷이 저마다 새로 만드는 화면으로 간다', async () => {
    signedIn();
    const works = await cards('새로 만들 작품');
    expect(works.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual([
      '/trpg/studio/scenarios/new',
      '/trpg/studio/campaigns/new',
      '/chat/studio/characters/new',
      '/story/studio/worlds/new',
    ]);
  });

  it('재료 카드를 누르면 그 재료를 새로 만드는 화면이다', async () => {
    signedIn();
    const materials = await cards('새로 만들 재료');
    await userEvent.click(materials.getByRole('link', { name: /몬스터 모음/ }));

    expect(await screen.findByRole('heading', { name: '새 몬스터 모음 만들기' })).toBeInTheDocument();
  });

  it('운영자에게만 JSON 으로 세계관 넣기가 보인다', async () => {
    signedIn(['operator']);
    const works = await cards('새로 만들 작품');
    expect(works.getByRole('link', { name: 'JSON 으로 세계관 넣기' })).toHaveAttribute('href', '/story/worlds/import');
  });

  it('운영자가 아니면 JSON 으로 넣기는 없고, 내 작품으로 가는 길이 있다', async () => {
    signedIn();
    const works = await cards('새로 만들 작품');
    expect(works.queryByRole('link', { name: 'JSON 으로 세계관 넣기' })).toBeNull();
    expect(screen.getByRole('link', { name: '내 작품 보기' })).toHaveAttribute('href', '/me?tab=creator');
  });
});
