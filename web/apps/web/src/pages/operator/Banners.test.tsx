// web/apps/web/src/pages/operator/Banners.test.tsx
// 홍보 배너 관리(#994)와 첫 화면의 배너: 운영자가 서버마다 건 배너를 보고 걸고 내린다. 첫 화면은 두 서버의 배너를 서비스 차례로 넘긴다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function operatorToken(): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles: ['operator'] }))}.sig`;
}

const ADMIN_SCENARIO = { id: 'g-1', scenario_id: SCENARIO_ID, title: '잿빛 수도원', position: 1, starts_at: '2026-11-01T00:00:00Z', ends_at: null, created_at: '2026-11-01T00:00:00Z', shown: true };
const ADMIN_WORLD = { id: 'a-1', kind: 'world', target_id: 'w-1', name: '여름 학교', position: 0, starts_at: '2026-11-01T00:00:00Z', ends_at: '2026-12-01T00:00:00Z', created_at: '2026-11-01T00:00:00Z', shown: false };

function operatorRoutes(extra: Record<string, (request: SeenRequest) => Response> = {}) {
  let scenarioBanners = [ADMIN_SCENARIO];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(operatorToken())),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', public_id: 'u1' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/game/admin/banners': () => json(200, scenarioBanners),
    'GET /api/v1/asset/admin/banners': () => json(200, [ADMIN_WORLD]),
    'DELETE /api/v1/game/admin/banners/g-1': () => {
      scenarioBanners = [];
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
}

describe('BannersPage', () => {
  it('두 서버의 배너를 보이고, 보이지 않는 것을 알리고, 내린다', async () => {
    operatorRoutes();
    renderApp('/operator/banners');

    const list = (await screen.findByRole('heading', { name: '건 배너' })).closest('section') as HTMLElement;
    expect(await within(list).findByText('잿빛 수도원')).toBeInTheDocument();
    expect(await within(list).findByText('여름 학교')).toBeInTheDocument();
    expect(within(list).getByText('지금 안 보임')).toBeInTheDocument();
    await userEvent.click(within(list).getByRole('button', { name: '잿빛 수도원 배너 내리기' }));

    expect(await within(list).findByText('여름 학교')).toBeInTheDocument();
    expect(within(list).queryByText('잿빛 수도원')).not.toBeInTheDocument();
  });

  it('고른 종류의 서버에 걸고, 공개되지 않은 작품이면 까닭을 적는다', async () => {
    let answer = json(409, { detail: '공개 목록에 나오는 작품만 걸 수 있습니다.', code: 'not_published' });
    const { seen } = operatorRoutes({ 'POST /api/v1/asset/admin/banners': () => answer });
    renderApp('/operator/banners');

    const form = within(await screen.findByRole('form', { name: '배너 걸기' }));
    await userEvent.selectOptions(form.getByRole('combobox', { name: '작품의 종류' }), 'chat 캐릭터');
    await userEvent.type(form.getByRole('textbox', { name: '작품 ID' }), SCENARIO_ID);
    await userEvent.click(form.getByRole('button', { name: '걸기' }));

    expect(await form.findByText(/작품의 종류와 ID, 공개 여부를 확인해 주세요/)).toBeInTheDocument();
    expect(seen.find((request) => request.method === 'POST' && request.url === '/api/v1/asset/admin/banners')?.body).toEqual({ kind: 'character', target_id: SCENARIO_ID, position: 0 });

    answer = json(201, { ...ADMIN_WORLD, id: 'a-2', kind: 'character' });
    await userEvent.click(form.getByRole('button', { name: '걸기' }));
    expect(await form.findByText('걸었습니다.')).toBeInTheDocument();
  });
});

describe('PromoBanner', () => {
  it('첫 화면에 두 서버의 배너를 서비스 차례로 넘긴다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/game/banners': () =>
        json(200, {
          items: [{ id: 'g-1', listing: { scenario_id: SCENARIO_ID, creator_id: 'c', title: '잿빛 수도원', tagline: '종이 울리지 않는 밤', description: '', genre: 'horror', tags: [], rating: 'all', recommended_players: { min: 2, max: 4 }, version: 1, version_note: '', published_at: '2026-10-20T00:00:00Z' } }],
        }),
      'GET /api/v1/asset/banners': () =>
        json(200, { items: [{ id: 'a-1', kind: 'world', character: null, world: { id: 'w-1', version: 1, name: '여름 학교', image_id: null, rating: 'all', tags: ['학원'], deadline_days: 30, published_at: '2026-10-26T00:00:00Z' } }] }),
    });
    renderApp('/');

    const banner = await screen.findByRole('region', { name: '홍보' });
    expect(await within(banner).findByText('잿빛 수도원')).toBeInTheDocument();
    expect(within(banner).getByText('1 / 2')).toBeInTheDocument();
    await userEvent.click(within(banner).getByRole('button', { name: '다음' }));

    expect(within(banner).getByText('여름 학교').closest('a')).toHaveAttribute('href', '/story/worlds/w-1');
    await userEvent.click(within(banner).getByRole('button', { name: '다음' }));
    expect(within(banner).getByText('잿빛 수도원')).toBeInTheDocument();
  });
});
