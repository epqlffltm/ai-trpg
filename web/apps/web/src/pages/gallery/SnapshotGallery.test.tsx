// web/apps/web/src/pages/gallery/SnapshotGallery.test.tsx
// 갤러리(C7)의 "내 장면 그림"(#983). 탭마다 그 서비스의 다 그린 그림을 칸으로 보이고, 누르면 크게 보는 창에서 그 대화로 간다.
// 쪽으로 더 읽고, 비었을 때와 읽지 못했을 때를 알린다. 글과 주소를 짓는 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { KeptSnapshot } from '../../api/snapshots';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { conversationLinkLabel, conversationPath, snapshotCaption } from './snapshotGalleryView';

const IMAGE = (n: number) => `00000000-0000-4000-8000-00000000b98${n}`;
const CONVERSATION = '00000000-0000-4000-8000-00000000d983';
const AT = '2026-11-04T03:00:00Z';

function kept(n: number, extra: Partial<KeptSnapshot> = {}): KeptSnapshot {
  return { id: `00000000-0000-4000-8000-0000000c983${n}`, image_id: IMAGE(n), conversation_id: CONVERSATION, conversation_title: '비 오는 오후', work_name: '루나', message_id: null, created_at: AT, ...extra } as KeptSnapshot;
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/chat/gallery': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
    [`GET /api/v1/asset/images/${IMAGE(1)}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${IMAGE(2)}`]: () => new Response('png', { status: 200 }),
    ...routes,
  });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:snapshot'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('갤러리의 내 장면 그림', () => {
  it('chat 탭에 다 그린 그림을 보이고, 크게 보는 창에서 그 대화로 간다', async () => {
    signedIn({ 'GET /api/v1/chat/snapshots': () => json(200, { items: [kept(1)], total: 1 }) });
    renderApp('/gallery?tab=chat');

    const list = within(await screen.findByRole('list', { name: '내 장면 그림' }));
    expect(list.getByText('루나 · 비 오는 오후')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /내 장면 그림/ })).toHaveTextContent('1장');
    const open = await list.findByRole('button', { name: '루나 · 비 오는 오후 장면 그림 크게 보기' });
    await waitFor(() => expect(open).toBeEnabled());
    await userEvent.click(open);
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));

    expect(dialog.getByRole('link', { name: '그 대화로' })).toHaveAttribute('href', `/chat/conversations/${CONVERSATION}`);
    expect(dialog.getByRole('button', { name: '이 기기에 저장' })).toBeInTheDocument();
  });

  it('쪽으로 더 읽는다(한 쪽에 24장)', async () => {
    const { seen } = signedIn({
      'GET /api/v1/chat/snapshots': (request) =>
        request.url.includes('offset=0') ? json(200, { items: [kept(1)], total: 25 }) : json(200, { items: [kept(2, { conversation_title: '맑은 아침' })], total: 25 }),
    });
    renderApp('/gallery?tab=chat');

    await userEvent.click(await screen.findByRole('button', { name: '장면 그림 더 보기' }));

    const list = within(screen.getByRole('list', { name: '내 장면 그림' }));
    expect(await list.findByText('루나 · 맑은 아침')).toBeInTheDocument();
    expect(seen.filter((request) => request.url.startsWith('/api/v1/chat/snapshots')).map((request) => request.url)).toEqual([
      '/api/v1/chat/snapshots?limit=24&offset=0',
      '/api/v1/chat/snapshots?limit=24&offset=24',
    ]);
  });

  it('story 탭은 story 의 그림을 읽고, 비었으면 알린다', async () => {
    const { seen } = signedIn({ 'GET /api/v1/story/snapshots': () => json(200, { items: [], total: 0 }) });
    renderApp('/gallery?tab=story');

    expect(await screen.findByText(/아직 그린 장면 그림이 없습니다/)).toBeInTheDocument();
    expect(seen.some((request) => request.url.startsWith('/api/v1/chat/snapshots'))).toBe(false);
  });

  it('읽지 못하면 이 칸만 알리고 다시 읽는다', async () => {
    let fail = true;
    signedIn({ 'GET /api/v1/chat/snapshots': () => (fail ? json(503, { detail: 'x' }) : json(200, { items: [kept(1)], total: 1 })) });
    renderApp('/gallery?tab=chat');

    await userEvent.click(await screen.findByRole('button', { name: '장면 그림 다시 불러오기' }, { timeout: 5000 }));
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: '장면 그림 다시 불러오기' }));

    expect(await screen.findByText('루나 · 비 오는 오후')).toBeInTheDocument();
    expect(screen.getByText(/아직 연 일러스트가 없습니다/)).toBeInTheDocument();
  });
});

describe('내 장면 그림의 글과 주소', () => {
  it('칸의 이름, 대화의 주소, 길의 글', () => {
    expect(snapshotCaption({ work_name: '루나', conversation_title: '비 오는 오후' })).toBe('루나 · 비 오는 오후');
    expect(snapshotCaption({ work_name: '여름 학교', conversation_title: '여름 학교' })).toBe('여름 학교');
    expect(conversationPath('story', 'x')).toBe('/story/sessions/x');
    expect([conversationLinkLabel('chat'), conversationLinkLabel('story')]).toEqual(['그 대화로', '그 세션으로']);
  });
});
