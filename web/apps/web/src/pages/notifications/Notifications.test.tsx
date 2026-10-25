// web/apps/web/src/pages/notifications/Notifications.test.tsx
// 알림(A10). 머리의 "알림"과 읽지 않은 수, 알림 화면의 글과 갈 곳(모르는 종류는 일반 문구), 하나 읽기, 모두 읽기(받은 가장 새 번호까지),
// 더 보기, 받을 알림 끄고 켜기. 글을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import type { AppNotification } from '../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { notificationProblemText } from './notificationProblem';
import { badgeText, describeNotification, muteLabel, needsModelNames, newestId } from './notificationText';

const BOX = '/api/v1/notification/me/notifications';
const ORDER = '00000000-0000-4000-8000-0000000000b1';
const TABLE = '00000000-0000-4000-8000-0000000000b2';
const CTX = { modelName: (slug: string) => (slug === 'gpt-x' ? 'GPT X' : slug) };

function notice(id: number, source: string, kind: string, payload: Record<string, unknown>, read = false): AppNotification {
  return { id, source, kind, payload, created_at: '2026-10-24T03:00:00Z', read_at: read ? '2026-10-24T04:00:00Z' : null };
}

const PAID = notice(12, 'billing', 'order.paid', { order_id: ORDER, product_id: 'credits-1000', price: 1000, credits: '1000' });
const RETIRING = notice(11, 'game', 'narration_model.retiring', { table_id: TABLE, title: '종탑', narration_model: 'gpt-x', retires_on: '2026-11-21', days_left: 7 });
const ODD = notice(10, 'board', 'board.unknown', {}, true);
const OLD = notice(3, 'billing', 'credit.welcome', { amount: '1000', expires_at: '2026-11-23T00:00:00Z' }, true);

function signedIn() {
  let unread = 2;
  let mutes = [
    { kind: 'credit.short', muted: false },
    { kind: 'post.commented', muted: false },
  ];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/game/tables/narration-models': () => json(200, { default: 'gpt-x', models: [{ slug: 'gpt-x', display_name: 'GPT X' }] }),
    [`GET ${BOX}/unread-count`]: () => json(200, { unread }),
    [`GET ${BOX}`]: (request) =>
      request.url.includes('before=10') ? json(200, { items: [OLD], next_before: null }) : json(200, { items: [PAID, RETIRING, ODD], next_before: 10 }),
    [`POST ${BOX}/12/read`]: () => {
      unread = 1;
      return json(200, { ...PAID, read_at: '2026-10-24T05:00:00Z' });
    },
    [`POST ${BOX}/read-all`]: () => {
      unread = 0;
      return json(200, { read: 1 });
    },
    [`GET ${BOX}/mutes`]: () => json(200, { kinds: mutes }),
    [`PUT ${BOX}/mutes/credit.short`]: () => {
      mutes = mutes.map((item) => (item.kind === 'credit.short' ? { ...item, muted: true } : item));
      return json(200, { kinds: mutes });
    },
    [`DELETE ${BOX}/mutes/credit.short`]: () => {
      mutes = mutes.map((item) => (item.kind === 'credit.short' ? { ...item, muted: false } : item));
      return json(200, { kinds: mutes });
    },
  });
}

function posts(seen: SeenRequest[], url: string): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === url).map((request) => request.body ?? null);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('알림', () => {
  it('머리에 읽지 않은 수를 보이고, 알림 화면에 글과 갈 곳을 보인다. 모르는 종류는 일반 문구', async () => {
    signedIn();
    renderApp('/');

    await userEvent.click(await screen.findByRole('link', { name: '알림, 읽지 않은 것 2개' }));
    const list = within(await screen.findByRole('list', { name: '알림' }));
    expect(await list.findByRole('link', { name: '충전했습니다: 1,000원 · 골드 1,000' })).toHaveAttribute('href', `/wallet/orders/${ORDER}`);
    expect(await list.findByRole('link', { name: /"종탑" 테이블의 서술 모델 GPT X: 11월 21일에 끝납니다\(7일 남음\)/ })).toHaveAttribute('href', `/trpg/tables/${TABLE}`);
    expect(list.getByText('새 알림입니다')).toBeInTheDocument();
    expect(list.getAllByText('새 알림')).toHaveLength(2);
  });

  it('하나를 읽으면 그 줄과 수가 바뀌고, 모두 읽음은 받은 가장 새 번호까지 보낸다', async () => {
    const { seen } = signedIn();
    renderApp('/notifications');

    const list = within(await screen.findByRole('list', { name: '알림' }));
    await userEvent.click(await list.findByRole('button', { name: '읽음: 충전했습니다: 1,000원 · 골드 1,000' }));
    await vi.waitFor(() => expect(list.getAllByText('새 알림')).toHaveLength(1));
    expect(await screen.findByRole('link', { name: '알림, 읽지 않은 것 1개' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '모두 읽음' }));
    await vi.waitFor(() => expect(posts(seen, `${BOX}/read-all`)).toEqual([{ up_to: 12 }]));
    expect(await screen.findByRole('link', { name: '알림' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '모두 읽음' })).toBeNull();
  });

  it('더 보기로 다음 쪽을 읽는다', async () => {
    signedIn();
    renderApp('/notifications');
    await userEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    expect(await screen.findByText(/환영 실버를 받았습니다: 실버 1,000/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
  });

  it('받을 알림을 끄고 다시 켠다', async () => {
    const { seen } = signedIn();
    renderApp('/notifications');

    const short = await screen.findByRole('checkbox', { name: '크레딧이 모자라 서술 값을 걸지 못함' });
    expect(short).toBeChecked();
    await userEvent.click(short);
    await vi.waitFor(() => expect(short).not.toBeChecked());
    await userEvent.click(short);
    await vi.waitFor(() => expect(short).toBeChecked());
    const methods = seen.filter((request) => request.url === `${BOX}/mutes/credit.short`).map((request) => request.method);
    expect(methods).toEqual(['PUT', 'DELETE']);
  });
});

describe('알림의 순수한 함수', () => {
  it('종류마다의 글과 갈 곳, 빠진 칸', () => {
    expect(describeNotification(notice(1, 'billing', 'credit.short', { amount: '120', gold_required: true }), CTX)).toEqual({
      text: '크레딧이 모자라 서술 값을 걸지 못했습니다(120). 프리미엄 모델은 골드로만 냅니다',
      to: '/wallet/charge',
    });
    expect(describeNotification(notice(1, 'game', 'scenario.sanctioned', { scenario_id: 's1', title: '수도원', version_number: 3, publishing_banned: true }), CTX)).toEqual({
      text: '운영자가 시나리오 "수도원"(판 3)에 조치했습니다. 지금은 시나리오를 공개할 수 없습니다',
      to: '/trpg/studio/scenarios/s1',
    });
    expect(describeNotification(notice(1, 'game', 'narration_model.replaced', {}), CTX).text).toBe('내 테이블의 서술 모델을 바꿨습니다: 서버의 기본 모델 → 서버의 기본 모델(앞의 모델이 끝남)');
    expect(describeNotification(notice(1, 'board', 'post.commented', { post_title: '첫 글', post_id: '7' }), CTX)).toEqual({ text: '내 글 "첫 글"에 댓글이 달렸습니다', to: '/board/posts/7' });
    expect(describeNotification(notice(1, 'asset', 'character.hidden', { character_id: 'c1', name: '렌' }), CTX).to).toBe('/chat/studio/characters/c1');
    expect(describeNotification(notice(1, 'game', 'order.paid', {}), CTX).text).toBe('새 알림입니다');
  });

  it('표시, 끄기의 이름, 가장 새 번호, 모델 이름이 필요한지, 실패의 글', () => {
    expect(badgeText(0)).toBe('');
    expect(badgeText(7)).toBe('7');
    expect(badgeText(100)).toBe('99+');
    expect(muteLabel('post.commented')).toBe('내 글에 달린 댓글');
    expect(muteLabel('new.kind')).toBe('new.kind');
    expect(newestId([OLD, PAID, ODD])).toBe(12);
    expect(newestId([])).toBeNull();
    expect(needsModelNames([PAID])).toBe(false);
    expect(needsModelNames([RETIRING])).toBe(true);
    expect(notificationProblemText(new ApiError({ status: 503, detail: 'x', retryAfter: 5 }))).toContain('5초 뒤에');
  });
});
