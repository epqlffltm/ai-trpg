// web/apps/web/src/pages/gallery/StoryGallery.test.tsx
// 갤러리(C7)의 story 탭. 내 세션의 세계관마다(겹치지 않게) 연 일러스트를 인물마다 묶고(인물이 없으면 세계관 칸), 크게 본다.
// 세계관마다 따로 실패한다. 세션이 없으면 안내한다. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryIllustration, StorySessionSummary } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castLabel, groupIllustrations, sessionWorlds, WORLD_GROUP } from './storyGalleryView';

const SUMMER = '00000000-0000-4000-8000-00000000bd01';
const WINTER = '00000000-0000-4000-8000-00000000bd02';
const IMAGE = (n: number) => `00000000-0000-4000-8000-00000000ad0${n}`;
const AT = '2026-10-27T03:00:00Z';

function summary(n: number, worldId: string, name: string): StorySessionSummary {
  return { id: `00000000-0000-4000-8000-00000000ae0${n}`, title: `세션 ${n}`, world: { id: worldId, version: 1, name, image_id: null, rating: 'all' }, model: null, created_at: AT, updated_at: AT, progress: null } as unknown as StorySessionSummary;
}

function illustration(kind: 'event' | 'ending', sceneId: string, cast: string[], n: number): StoryIllustration {
  return { kind, scene_id: sceneId, cast, image_id: IMAGE(n), first_seen_at: AT, conversation_id: null };
}

const CAST = [
  { id: 'mina', reveal: 'shown', name: '미나', image_id: null },
  { id: 'veil', reveal: 'hidden', name: null, image_id: null },
];

function signedIn(sessions: unknown[]) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/story/conversations': () => json(200, { items: sessions, total: sessions.length }),
    'GET /api/v1/story/gallery': (request) =>
      request.url.includes(SUMMER)
        ? json(200, { items: [illustration('event', 'rain', ['mina'], 1), illustration('ending', 'spring', [], 2)] })
        : json(503, { detail: '잠시' }),
    [`GET /api/v1/asset/listings/worlds/${SUMMER}`]: () => json(200, { id: SUMMER, name: '여름 학교', cast: CAST }),
    [`GET /api/v1/asset/listings/worlds/${WINTER}`]: () => json(404, { detail: 'x' }),
    [`GET /api/v1/asset/images/${IMAGE(1)}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${IMAGE(2)}`]: () => new Response('png', { status: 200 }),
  });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:scene'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('갤러리의 story 탭', () => {
  it('세계관마다 인물별로 묶어 보이고, 크게 본다. 한 세계관이 실패해도 나머지는 보인다', async () => {
    signedIn([summary(1, SUMMER, '여름 학교'), summary(2, SUMMER, '여름 학교'), summary(3, WINTER, '겨울 산장')]);
    renderApp('/gallery?tab=story');

    expect(await screen.findAllByRole('link', { name: '여름 학교' })).toHaveLength(1);
    const mina = within(await screen.findByRole('list', { name: '여름 학교 · 미나의 장면' }));
    expect(mina.getByText('이벤트')).toBeInTheDocument();
    const world = within(screen.getByRole('list', { name: `여름 학교 · ${WORLD_GROUP}의 장면` }));
    expect(world.getByText('엔딩')).toBeInTheDocument();
    expect(screen.getByText('2개 열림')).toBeInTheDocument();
    expect(await screen.findByText(/갤러리를 불러오지 못했습니다/, {}, { timeout: 4000 })).toBeInTheDocument();

    await userEvent.click(mina.getByRole('button', { name: '이벤트 장면 크게 보기' }));
    expect(await screen.findByRole('dialog', { name: '이벤트 장면' })).toBeInTheDocument();
  });

  it('세션이 없으면 안내한다', async () => {
    signedIn([]);
    renderApp('/gallery?tab=story');
    expect(await screen.findByText(/아직 걸어 본 세계관이 없습니다/)).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  it('세계관 모으기, 인물마다 묶기, 이름', () => {
    expect(sessionWorlds([summary(1, SUMMER, '여름 학교'), summary(2, WINTER, '겨울 산장'), summary(3, SUMMER, '여름 학교')])).toEqual([
      { id: SUMMER, name: '여름 학교' },
      { id: WINTER, name: '겨울 산장' },
    ]);
    const groups = groupIllustrations([illustration('event', 'rain', ['mina', 'veil'], 1), illustration('ending', 'spring', [], 2), illustration('event', 'walk', ['mina'], 3)], CAST);
    expect(groups.map((group) => [group.title, group.cells.map((cell) => cell.key)])).toEqual([
      ['미나', ['event:rain', 'event:walk']],
      ['???', ['event:rain']],
      [WORLD_GROUP, ['ending:spring']],
    ]);
    expect(castLabel(undefined, 'mina')).toBe('???');
    expect(groupIllustrations([], CAST)).toEqual([]);
  });
});
