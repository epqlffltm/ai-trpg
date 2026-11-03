// web/apps/web/src/pages/story/studio/WorldChapters.test.tsx
// 세계관의 장 탭(D7, docs/architecture/chapters.md). 첫 장은 조건이 없고 뒤의 장은 조건을 적는다. 장마다 여는 장소와 이벤트를 고른다.
// 순수한 함수: 하나는 한 장에만 열고, 뒤의 장이 시작 장소를 열면 알리고, 첫 장이 된 장의 조건은 보내지 않는다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { addChapter, changeChapter, chaptersHints, hasChaptersHints, loreChoices, loreKey, moveChapterUp, toChaptersBody, toggleOpen, type ChapterDraft } from './chaptersForm';
import { addCondition, changeCondition, type ConditionChoices } from './conditionsForm';
import { worldProblemLine, worldWarningText } from './worldPublishText';

const WORLDS = '/api/v1/asset/worlds';
const ID = '00000000-0000-4000-8000-0000000000fa';
const AT = '2026-11-01T00:00:00Z';
const BOOK = '00000000-0000-4000-8000-0000000000fb';

function world(): StoryWorldDetail {
  return {
    id: ID,
    name: '여름 학교',
    intro_html: '',
    genre: 'romance',
    tags: [],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [{ id: 'morning', name: '아침', start_hour: 7 }],
    start_slot: 'morning',
    deadline_days: null,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro'] },
    places: [
      { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
      { id: 'square', name: '광장', description: '', image_id: null, backgrounds: {} },
    ],
    paths: [],
    start_place: 'park',
    items: [],
    start_items: [],
    cast: [],
    events: [{ id: 'rain', name: '소나기', when: { match: 'all', items: [] }, repeat: false, scene: { text: '비가 온다.', cast: [], image_id: null, collectible: false }, on_open: [], choices: [] }],
    endings: [],
    chapters: [],
    shortcuts: [],
    lorebooks: [BOOK],
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
  } as StoryWorldDetail;
}

function signedIn() {
  let current = world();
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${WORLDS}/${ID}`]: () => json(200, current),
    [`PATCH ${WORLDS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Partial<StoryWorldDetail>) };
      return json(200, current);
    },
    [`GET ${WORLDS}/${ID}/publish-check`]: () => json(200, { ready: true, problems: [], warnings: [], removed: [] }),
    [`GET ${WORLDS}/${ID}/versions`]: () => json(200, []),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    [`GET /api/v1/asset/lorebooks/${BOOK}`]: () =>
      json(200, { id: BOOK, name: '제국', entries: [{ id: 'city', name: '가나폴리아', kind: 'place', keywords: [], content: '수도.', constant: true }], latest_version: 1 }),
    'GET /api/v1/asset/characters': () => json(200, { items: [], total: 0 }),
  });
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH').map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장 탭', () => {
  it('첫 장과 조건을 적은 둘째 장을 만들고, 둘째 장이 광장과 소나기를 연다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}?tab=chapters`);

    const form = within(await screen.findByRole('form', { name: '장' }));
    await userEvent.click(form.getByRole('button', { name: '장 더하기' }));
    await userEvent.type(form.getByLabelText('1장의 이름'), '여름의 시작');
    await userEvent.click(form.getByRole('button', { name: '장 더하기' }));
    await userEvent.type(form.getByLabelText('2장의 이름'), '축제');
    // 조건이 없으면 저장하지 않는다
    expect(form.getByText('넘어오는 조건을 하나 이상 적어 주세요.')).toBeInTheDocument();
    await userEvent.click(form.getByRole('button', { name: '축제의 조건 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('축제의 조건 1의 대상'), 'park');
    await userEvent.click(form.getByLabelText('축제: 광장'));
    await userEvent.click(form.getByLabelText('축제: 소나기'));
    await userEvent.click(await form.findByLabelText('축제: 제국: 가나폴리아'));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const body = patches(seen)[0] as { chapters: Record<string, unknown>[] };
    expect(body.chapters).toHaveLength(2);
    expect(body.chapters[0]).toMatchObject({ name: '여름의 시작', when: { match: 'all', items: [] }, opens: { places: [], events: [] } });
    expect(body.chapters[1]).toMatchObject({
      name: '축제',
      when: { match: 'all', items: [{ kind: 'reach_place', target: 'park', count: 1 }] },
      opens: { places: ['square'], events: ['rain'], lore: [{ lorebook: BOOK, entry: 'city' }] },
    });
  });
});

describe('순수한 함수', () => {
  const choices: ConditionChoices = { places: [{ id: 'park', name: '공원' }], items: [], cast: [], slots: [], events: [], chapters: [{ id: 'a', name: '1장' }] };

  function two(): ChapterDraft[] {
    let chapters = addChapter(addChapter([], 'a'), 'b');
    chapters = changeChapter(chapters, 'a', (chapter) => ({ ...chapter, name: '시작' }));
    return changeChapter(chapters, 'b', (chapter) => ({ ...chapter, name: '축제', when: changeCondition(addCondition(chapter.when), 0, { target: 'park' }) }));
  }

  it('로어북 항목은 열쇠로 들고 다니다가 {lorebook, entry} 로 보낸다', () => {
    const chapters = toggleOpen(two(), 'b', 'lore', loreKey(BOOK, 'city'));
    const body = toChaptersBody(chapters) as { chapters: { opens: { lore: unknown[] } }[] };
    expect(body.chapters.map((chapter) => chapter.opens.lore)).toEqual([[], [{ lorebook: BOOK, entry: 'city' }]]);
    expect(loreChoices([{ id: BOOK, name: '제국', entries: [{ id: 'city', name: '가나폴리아' }] }])).toEqual([{ id: loreKey(BOOK, 'city'), name: '제국: 가나폴리아' }]);
  });

  it('하나는 한 장에만 연다. 다른 장에서 고르면 앞의 장에서 빠진다', () => {
    const chapters = toggleOpen(toggleOpen(two(), 'a', 'places', 'square'), 'b', 'places', 'square');
    expect(chapters.map((chapter) => chapter.places)).toEqual([[], ['square']]);
    expect(toggleOpen(chapters, 'b', 'places', 'square').map((chapter) => chapter.places)).toEqual([[], []]);
  });

  it('뒤의 장이 시작 장소를 열면 알린다', () => {
    const hints = chaptersHints(toggleOpen(two(), 'b', 'places', 'park'), choices, 'park');
    expect(hints.b?.opens).toMatch(/시작 장소/);
    expect(hasChaptersHints(hints)).toBe(true);
    expect(hasChaptersHints(chaptersHints(two(), choices, 'park'))).toBe(false);
  });

  it('위로 옮겨 첫 장이 된 장은 조건을 보내지 않는다', () => {
    const body = toChaptersBody(moveChapterUp(two(), 1)) as { chapters: { id: string; when: { items: unknown[] } }[] };
    expect(body.chapters.map((chapter) => [chapter.id, chapter.when.items.length])).toEqual([
      ['b', 0],
      ['a', 0],
    ]);
  });

  it('장의 막는 것은 장 탭으로 간다', () => {
    expect(worldProblemLine('chapter_start_locked').tab).toBe('chapters');
    expect(worldProblemLine('chapter_content_missing').tab).toBe('chapters');
    expect(worldWarningText('chapter_content_late')).toMatch(/이미 지난 날/);
  });
});
