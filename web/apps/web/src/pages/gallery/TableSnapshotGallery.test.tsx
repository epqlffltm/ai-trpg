// web/apps/web/src/pages/gallery/TableSnapshotGallery.test.tsx
// 갤러리(C7)의 TRPG 탭(#983). 내가 그린 테이블의 장면 그림을 칸으로 보이고, 크게 보는 창에서 그 테이블로 가거나 지운다.
// 지운 테이블의 그림도 보이고 테이블로 가는 길은 없다. 비었을 때를 알린다. 글과 주소를 짓는 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { KeptTableSnapshot } from '../../api/tableSnapshots';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { tablePath, tableSnapshotCaption } from './tableSnapshotGalleryView';

const IMAGE = (n: number) => `00000000-0000-4000-8000-00000000a98${n}`;
const TABLE = '00000000-0000-4000-8000-00000000e983';
const AT = '2026-11-05T03:00:00Z';

function kept(n: number, extra: Partial<KeptTableSnapshot> = {}): KeptTableSnapshot {
  return { id: `00000000-0000-4000-8000-0000000e983${n}`, image_id: IMAGE(n), table_id: TABLE, table_title: '추격전', round_number: n, created_at: AT, ...extra } as KeptTableSnapshot;
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/asset/images/${IMAGE(1)}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${IMAGE(2)}`]: () => new Response('png', { status: 200 }),
    ...routes,
  });
}

async function openViewer(caption: string) {
  const list = within(await screen.findByRole('list', { name: '내 장면 그림' }));
  const open = await list.findByRole('button', { name: `${caption} 장면 그림 크게 보기` });
  await waitFor(() => expect(open).toBeEnabled());
  await userEvent.click(open);
  return within(await screen.findByRole('dialog', { name: '장면 그림' }));
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:snapshot'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('갤러리의 TRPG 장면 그림', () => {
  it('TRPG 탭에 내 그림을 보이고, 크게 보는 창에서 그 테이블로 간다', async () => {
    signedIn({ 'GET /api/v1/game/snapshots': () => json(200, { items: [kept(1)], total: 1 }) });
    renderApp('/gallery?tab=trpg');

    const tabs = within(await screen.findByRole('navigation', { name: '서비스' }));
    expect(tabs.getByRole('link', { name: 'TRPG' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { name: /내 장면 그림/ })).toHaveTextContent('1장');
    const dialog = await openViewer('추격전 · 라운드 1');

    expect(dialog.getByRole('link', { name: '그 테이블로' })).toHaveAttribute('href', `/trpg/tables/${TABLE}`);
    expect(dialog.getByRole('button', { name: '이 기기에 저장' })).toBeInTheDocument();
  });

  it('지운 테이블의 그림도 보이고, 테이블로 가는 길은 없다', async () => {
    signedIn({ 'GET /api/v1/game/snapshots': () => json(200, { items: [kept(2, { table_id: null, table_title: null })], total: 1 }) });
    renderApp('/gallery?tab=trpg');

    const dialog = await openViewer('지운 테이블 · 라운드 2');

    expect(dialog.queryByRole('link', { name: '그 테이블로' })).not.toBeInTheDocument();
    expect(dialog.getByText('지운 테이블의 그림입니다.')).toBeInTheDocument();
  });

  it('창에서 확인한 뒤 지우고 목록을 다시 읽는다', async () => {
    let items = [kept(1)];
    const { seen } = signedIn({
      'GET /api/v1/game/snapshots': () => json(200, { items, total: items.length }),
      [`DELETE /api/v1/game/snapshots/${kept(1).id}`]: () => {
        items = [];
        return new Response(null, { status: 204 });
      },
    });
    renderApp('/gallery?tab=trpg');

    const dialog = await openViewer('추격전 · 라운드 1');
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    expect(await screen.findByText(/아직 그린 장면 그림이 없습니다/)).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'DELETE')).toHaveLength(1);
  });

  it('지우지 못하면 창 안에 까닭을 알린다', async () => {
    signedIn({
      'GET /api/v1/game/snapshots': () => json(200, { items: [kept(1)], total: 1 }),
      [`DELETE /api/v1/game/snapshots/${kept(1).id}`]: () => json(503, { detail: '안 됨', code: 'asset_unavailable' }),
    });
    renderApp('/gallery?tab=trpg');

    const dialog = await openViewer('추격전 · 라운드 1');
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    expect(await dialog.findByText('지금은 그림을 지울 수 없습니다. 잠시 뒤에 다시 해 주세요.')).toBeInTheDocument();
  });

  it('그린 그림이 없으면 그렇게 알리고, chat 의 일러스트는 부르지 않는다', async () => {
    const { seen } = signedIn({ 'GET /api/v1/game/snapshots': () => json(200, { items: [], total: 0 }) });
    renderApp('/gallery?tab=trpg');

    expect(await screen.findByText(/아직 그린 장면 그림이 없습니다/)).toBeInTheDocument();
    expect(seen.some((request) => request.url.startsWith('/api/v1/chat/'))).toBe(false);
  });
});

describe('tableSnapshotGalleryView', () => {
  it('칸의 이름과 테이블의 주소를 짓는다', () => {
    expect(tableSnapshotCaption({ table_title: '추격전', round_number: 3 })).toBe('추격전 · 라운드 3');
    expect(tableSnapshotCaption({ table_title: null, round_number: 3 })).toBe('지운 테이블 · 라운드 3');
    expect(tablePath({ table_id: TABLE })).toBe(`/trpg/tables/${TABLE}`);
    expect(tablePath({ table_id: null })).toBeNull();
  });
});
