// web/apps/web/src/pages/gallery/Gallery.test.tsx
// 갤러리(C7). 마이페이지에서 가기, chat 탭의 캐릭터마다 해금 대상 씬의 칸(연 것은 이름과 날, 열지 않은 것은 흐린 그림),
// 크게 보기, 볼 수 없는 캐릭터, 빈 갤러리, story 탭. 칸을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { ChatUnlock, EventSceneDocument } from '../../api/types';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { groupUnlocks, openedLabel, sceneCells } from './galleryView';

const LUNA = '00000000-0000-4000-8000-00000000c101';
const GONE = '00000000-0000-4000-8000-00000000c102';
const IMAGE = (n: number) => `00000000-0000-4000-8000-00000000a10${n}`;

function scene(id: string, title: string, n: number, collectible = true): EventSceneDocument {
  return { id, title, image_id: IMAGE(n), description: '', collectible, when: { kind: 'reach_place', target: 'park' } } as EventSceneDocument;
}

const SCENES = [scene('rain', '비 오는 공원', 1), scene('cafe', '창가의 카페', 2), scene('secret', '숨은 장면', 3, false)];
const UNLOCKS = [
  { character_id: LUNA, scene_id: 'rain', unlocked_at: '2026-10-24T03:00:00Z' },
  { character_id: GONE, scene_id: 'x', unlocked_at: '2026-10-23T03:00:00Z' },
];

function signedIn(unlocks: ChatUnlock[] = UNLOCKS) {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:scene'), revokeObjectURL: vi.fn() });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/chat/gallery': () => json(200, { items: unlocks, total: unlocks.length }),
    [`GET /api/v1/asset/listings/characters/${LUNA}`]: () => json(200, { id: LUNA, version: 2, published_at: '', document: { name: '루나', event_scenes: SCENES } }),
    [`GET /api/v1/asset/listings/characters/${GONE}`]: () => json(404, { detail: 'x' }),
    [`GET /api/v1/asset/images/${IMAGE(1)}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${IMAGE(2)}`]: () => new Response('png', { status: 200 }),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('갤러리', () => {
  it('마이페이지에서 가서, 캐릭터마다 해금 대상 씬의 칸을 보이고, 연 것을 크게 본다. 볼 수 없는 캐릭터는 연 수만', async () => {
    signedIn();
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: '내가 연 일러스트' }));
    const luna = within(await screen.findByRole('list', { name: '루나의 장면' }));
    expect(screen.getByText('1 / 2 열림')).toBeInTheDocument();
    expect(luna.getAllByRole('listitem')).toHaveLength(2);
    expect(luna.getByText('비 오는 공원')).toBeInTheDocument();
    expect(luna.getByText('아직 열지 않음')).toBeInTheDocument();
    expect(luna.queryByText('창가의 카페')).toBeNull();
    expect(await screen.findByText(/연 장면 1개는 기록에 남아 있습니다/)).toBeInTheDocument();

    await userEvent.click(luna.getByRole('button', { name: '비 오는 공원 크게 보기' }));
    expect(await screen.findByRole('dialog', { name: '비 오는 공원' })).toBeInTheDocument();
  });

  it('연 것이 없으면 안내하고, story 탭은 준비 중이라 적는다', async () => {
    signedIn([]);
    renderApp('/gallery');
    expect(await screen.findByText(/아직 연 일러스트가 없습니다/)).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole('navigation', { name: '서비스' })).getByRole('link', { name: 'story' }));
    expect(await screen.findByText(/story 의 갤러리는 준비 중입니다/)).toBeInTheDocument();
  });
});

describe('갤러리의 순수한 함수', () => {
  it('캐릭터마다 묶고 처음 연 때를 남긴다. 해금 대상만 칸이 된다', () => {
    const groups = groupUnlocks([...UNLOCKS, { character_id: LUNA, scene_id: 'rain', unlocked_at: '2020-01-01T00:00:00Z' }]);
    expect([...groups.keys()]).toEqual([LUNA, GONE]);
    expect(groups.get(LUNA)?.get('rain')).toBe('2026-10-24T03:00:00Z');
    const cells = sceneCells(SCENES, groups.get(LUNA) ?? new Map());
    expect(cells.map((cell) => [cell.id, cell.unlockedAt !== null])).toEqual([
      ['rain', true],
      ['cafe', false],
    ]);
    expect(openedLabel(cells)).toBe('1 / 2 열림');
  });
});
