// web/apps/web/src/pages/story/studio/WorldAchievements.test.tsx
// 세계관의 업적 탭(D7, docs/architecture/achievements.md 의 "story"). 업적마다 이름, 받는 법, 숨김, 받는 조건을 적어 저장한다.
// 받는 조건이 없거나 이름이 비면 저장하지 않는다. 순수한 함수: 더하기(50 개까지), 위로, 지우기, 보낼 모양, 힌트.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import {
  ACHIEVEMENTS_MAX,
  achievementDrafts,
  achievementsHints,
  addAchievement,
  changeAchievement,
  hasAchievementsHints,
  moveAchievementUp,
  removeAchievement,
  toAchievementsBody,
  type AchievementDraft,
} from './achievementsForm';
import { addCondition, changeCondition, type ConditionChoices } from './conditionsForm';

const WORLDS = '/api/v1/asset/worlds';
const ID = '00000000-0000-4000-8000-0000000000fa';
const AT = '2026-11-01T00:00:00Z';
const BOOK = '00000000-0000-4000-8000-0000000000fb';

function world(extra: Partial<StoryWorldDetail> = {}): StoryWorldDetail {
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
    achievements: [],
    lorebooks: [BOOK],
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StoryWorldDetail;
}

function signedIn(extra: Partial<StoryWorldDetail> = {}) {
  let current = world(extra);
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

const REACH_PARK = { kind: 'reach_place' as const, target: 'park', value: null, count: 1 };

describe('업적 탭', () => {
  it('이름, 받는 법, 숨김, 받는 조건을 적어 업적을 더한다. 조건이 없으면 저장하지 않는다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}?tab=achievements`);

    const form = within(await screen.findByRole('form', { name: '업적' }));
    expect(form.getByText('아직 업적이 없습니다.')).toBeInTheDocument();
    await userEvent.click(form.getByRole('button', { name: '업적 더하기' }));
    await userEvent.type(form.getByLabelText('업적 1의 이름'), '공원 산책');
    expect(form.getByText('받는 조건을 하나 이상 적어 주세요.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(form.getByLabelText('공원 산책의 받는 법(선택)'), '공원에 갔다');
    await userEvent.click(form.getByRole('checkbox', { name: /공원 산책: 숨긴 업적/ }));
    await userEvent.click(form.getByRole('button', { name: '공원 산책의 조건 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('공원 산책의 조건 1의 대상'), 'park');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const body = patches(seen)[0] as { achievements: Record<string, unknown>[] };
    expect(body.achievements).toEqual([
      {
        id: expect.stringMatching(/^achievement-/),
        name: '공원 산책',
        description: '공원에 갔다',
        hidden: true,
        image_id: null,
        when: { match: 'all', items: [{ kind: 'reach_place', target: 'park', count: 1 }] },
      },
    ]);
  });

  it('저장된 업적의 차례를 바꾸고 지운다', async () => {
    const achievements = [
      { id: 'a', name: '첫걸음', description: '', hidden: false, image_id: null, when: { match: 'all' as const, items: [REACH_PARK] } },
      { id: 'b', name: '소나기', description: '', hidden: false, image_id: null, when: { match: 'all' as const, items: [{ kind: 'event_seen' as const, target: 'rain', value: null, count: 1 }] } },
    ];
    const { seen } = signedIn({ achievements });
    renderApp(`/story/studio/worlds/${ID}?tab=achievements`);

    const form = within(await screen.findByRole('form', { name: '업적' }));
    expect(form.getByRole('button', { name: '첫걸음을(를) 위로' })).toBeDisabled();
    await userEvent.click(form.getByRole('button', { name: '소나기을(를) 위로' }));
    await userEvent.click(form.getByRole('button', { name: '첫걸음 지우기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0] as { achievements: { id: string }[] }).achievements.map((one) => one.id)).toEqual(['b']);
  });
});

describe('업적의 입력', () => {
  const choices: ConditionChoices = { places: [{ id: 'park', name: '공원' }], items: [], cast: [], slots: [], events: [] };

  function filled(id: string): AchievementDraft {
    const [draft] = addAchievement([], id);
    const when = changeCondition(addCondition((draft as AchievementDraft).when), 0, { target: 'park' });
    return { ...(draft as AchievementDraft), name: id, when };
  }

  it('50 개까지 더하고, 위로 올리고 지운다', () => {
    let many: AchievementDraft[] = [];
    for (let at = 0; at < ACHIEVEMENTS_MAX + 1; at += 1) many = addAchievement(many, `a${at}`);
    expect(many).toHaveLength(ACHIEVEMENTS_MAX);
    const three = [filled('a'), filled('b'), filled('c')];
    expect(moveAchievementUp(three, 2).map((one) => one.id)).toEqual(['a', 'c', 'b']);
    expect(moveAchievementUp(three, 0)).toBe(three);
    expect(removeAchievement(three, 'b').map((one) => one.id)).toEqual(['a', 'c']);
    expect(changeAchievement(three, 'a', (one) => ({ ...one, hidden: true }))[0]?.hidden).toBe(true);
  });

  it('이름, 받는 법의 길이, 받는 조건, 고르지 않은 대상을 본다', () => {
    const [empty] = addAchievement([], 'x');
    const long = { ...filled('y'), name: '가'.repeat(41), description: '나'.repeat(201) };
    const unpicked = { ...filled('z'), when: addCondition((empty as AchievementDraft).when) };
    const hints = achievementsHints([empty as AchievementDraft, long, unpicked, filled('ok')], choices);

    expect(hints.x).toMatchObject({ name: '이름을 적어 주세요.', when: '받는 조건을 하나 이상 적어 주세요.' });
    expect(hints.y).toMatchObject({ name: '이름은 40자까지입니다.', description: '받는 법은 200자까지입니다.' });
    expect(Object.keys(hints.z?.conditions ?? {})).toEqual(['0']);
    expect(hasAchievementsHints({ ok: hints.ok! })).toBe(false);
    expect(hasAchievementsHints(hints)).toBe(true);
  });

  it('보낼 때 이름과 받는 법의 빈칸을 자르고, 저장된 업적을 다시 읽는다', () => {
    const body = toAchievementsBody([{ ...filled('a'), name: ' 첫걸음 ', description: ' 공원 ', imageId: 'img' }]);
    expect(body.achievements).toEqual([{ id: 'a', name: '첫걸음', description: '공원', hidden: false, image_id: 'img', when: { match: 'all', items: [{ kind: 'reach_place', target: 'park', count: 1 }] } }]);
    const read = achievementDrafts({ achievements: [{ id: 'a', name: '첫걸음', description: '', hidden: true, image_id: null, when: { match: 'any', items: [REACH_PARK] } }] });
    expect(read).toEqual([{ id: 'a', name: '첫걸음', description: '', hidden: true, imageId: null, when: { match: 'any', items: [{ kind: 'reach_place', target: 'park', value: '', count: '1' }] } }]);
  });
});
