// web/apps/web/src/pages/me/works/MyWorks.test.tsx
// 마이페이지(Stitch 10번)의 내 작품과 최근 사용 내역: 캐릭터를 공개 상태 칩으로 거르고, 종류를 바꾸면 그 목록을, 내 포인트에는 최근 다섯 줄의 표를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { filterByStatus, workStatus } from './myWorksView';

const AT = '2026-11-01T00:00:00Z';

function character(id: string, name: string, extra: Record<string, unknown> = {}) {
  return { id, name, visibility: 'private', latest_version: null, hidden_at: null, rating: 'all', updated_at: AT, ...extra };
}

function entry(id: string, reason: string, amount: string) {
  return { id, operation_id: 'op', kind: 'free', reason, amount, order_id: null, hold_id: null, hold_status: null, source: null, created_at: AT };
}

function signedIn() {
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', username: 'one', identity: { verified: false, legal_adult: false, adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/billing/wallet/entries': () =>
      json(200, { entries: ['1', '2', '3', '4', '5', '6'].map((id) => entry(id, 'spend', '-3')).concat([entry('r', 'regroup', '0')]), next_before: 'x' }),
    'GET /api/v1/asset/characters': () =>
      json(200, {
        items: [
          character('c1', '초안 캐릭터'),
          character('c2', '공개 캐릭터', { visibility: 'public', latest_version: 2 }),
          character('c3', '숨긴 캐릭터', { visibility: 'public', latest_version: 1, hidden_at: AT }),
        ],
        total: 3,
      }),
    'GET /api/v1/asset/worlds': () => json(200, { items: [character('w1', '여름 학교', { visibility: 'unlisted', latest_version: 1 })], total: 1 }),
    'GET /api/v1/game/scenarios': () => json(200, { items: [{ id: 's1', title: '잿빛 수도원', description: '', created_at: AT, updated_at: AT, visibility: 'private', rating: 'all' }], total: 1 }),
    'GET /api/v1/game/campaigns': () => json(200, { items: [], total: 0 }),
  });
}

describe('내 작품', () => {
  it('캐릭터를 공개 상태 칩으로 거르고, 줄마다 상태와 고치기가 있다', async () => {
    signedIn();
    renderApp('/me?tab=creator');

    const list = within(await screen.findByRole('list', { name: '내 캐릭터' }));
    expect(await list.findByText('초안 캐릭터')).toBeInTheDocument();
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(list.getByRole('link', { name: '공개 캐릭터 고치기' })).toHaveAttribute('href', '/chat/studio/characters/c2');

    const chips = within(screen.getByRole('group', { name: '공개 상태' }));
    await userEvent.click(chips.getByRole('button', { name: '공개 중' }));
    expect(list.getAllByRole('listitem').map((item) => item.querySelector('.my-works__name')?.textContent)).toEqual(['공개 캐릭터']);
    await userEvent.click(chips.getByRole('button', { name: '숨겨짐' }));
    expect(list.getByText('숨긴 캐릭터')).toBeInTheDocument();
  });

  it('종류를 바꾸면 그 목록이 보인다(세계관은 칩, 시나리오는 칩 없이)', async () => {
    signedIn();
    renderApp('/me?tab=creator');
    const kinds = within(await screen.findByRole('group', { name: '작품의 종류' }));

    await userEvent.click(kinds.getByRole('button', { name: '세계관' }));
    const worlds = within(await screen.findByRole('list', { name: '내 세계관' }));
    expect(await worlds.findByText('링크 공개')).toBeInTheDocument();

    await userEvent.click(kinds.getByRole('button', { name: '시나리오·캠페인' }));
    const scenarios = within(await screen.findByRole('list', { name: '내 시나리오와 캠페인' }));
    expect(await scenarios.findByRole('link', { name: '잿빛 수도원 고치기' })).toHaveAttribute('href', '/trpg/studio/scenarios/s1');
    expect(screen.queryByRole('group', { name: '공개 상태' })).toBeNull();
  });

  it('공개 상태: 숨김이 먼저, 판이 없으면 초안', () => {
    expect(workStatus({ visibility: 'public', latest_version: 1, hidden_at: AT })).toBe('hidden');
    expect(workStatus({ visibility: 'public', latest_version: null })).toBe('draft');
    expect(workStatus({ visibility: 'unlisted', latest_version: 1 })).toBe('unlisted');
    expect(workStatus({ visibility: 'private', latest_version: 1 })).toBe('private');
    const works = [{ visibility: 'public' as const, latest_version: 1 }, { visibility: 'private' as const, latest_version: null }];
    expect(filterByStatus(works, undefined)).toHaveLength(2);
    expect(filterByStatus(works, 'draft')).toEqual([works[1]]);
  });
});

describe('최근 사용 내역', () => {
  it('내 포인트에 최근 다섯 줄을 표로 보이고 정리 줄은 숨긴다', async () => {
    signedIn();
    renderApp('/me?tab=points');

    const table = await screen.findByRole('table');
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['때', '무엇에', '얼마']);
    expect(await within(table).findAllByText('-3')).toHaveLength(5);
    expect(screen.getByRole('link', { name: '전체 내역 보기' })).toHaveAttribute('href', '/wallet');
  });
});
