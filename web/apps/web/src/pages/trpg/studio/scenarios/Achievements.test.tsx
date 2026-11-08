// web/apps/web/src/pages/trpg/studio/scenarios/Achievements.test.tsx
// 시나리오의 업적 탭(B9). 업적 만들기(이름, 받는 법, 숨김, 그림, 받는 조건), 받는 조건이 없으면 막기, 차례 바꾸기와 지우기,
// 장이 있으면 받는 조건에서 장 고르기, 그림이 내 것이 아닐 때(422), 게시 점검의 업적 문제. 입력의 순수한 함수(achievementsForm.ts).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Achievement } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME } from '../../../../test/tableFixtures';
import {
  achievementDraft,
  achievementHints,
  achievementLine,
  canMoveAchievement,
  hasAchievementHints,
  movedAchievement,
  newAchievementId,
  toAchievement,
  withAchievement,
  withoutAchievement,
} from './achievementsForm';
import type { Targets } from './conditionsForm';
import { problemLine } from './publishProblems';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const TOWER = '00000000-0000-4000-8000-00000000c004';
const HUNT = '00000000-0000-4000-8000-00000000f001';
const PICTURE = '00000000-0000-4000-8000-00000000e001';

const REACH_TOWER = { kind: 'reach_place' as const, target: TOWER, count: 1, consume: false };
const HUNT_DONE = { kind: 'quest_succeeded' as const, target: HUNT, count: 1, consume: false };

function achievement(id: string, name: string, extra: Partial<Achievement> = {}): Achievement {
  return { id, name, description: '', hidden: false, image_id: null, when: [REACH_TOWER], match: 'all', ...extra };
}

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

type Options = { start?: Record<string, unknown>; patch?: () => Response };

function signedIn({ start = {}, patch }: Options = {}) {
  let current = scenarioDetail({ lorebook_ids: [LOREBOOK], ...start });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () => json(200, [entry(TOWER, '종탑', 'place'), entry(HUNT, '구울 사냥', 'event')]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      if (patch) return patch();
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${GAME}/portraits`]: () => json(200, { items: [{ id: PICTURE, created_at: '' }], total: 1 }),
    [`GET ${GAME}/portraits/${PICTURE}/image`]: () => new Response('png', { status: 200 }),
  });
}

function patches(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as Record<string, unknown>);
}

async function achievementsPanel() {
  renderApp(`/trpg/studio/scenarios/${ID}?tab=achievements`);
  return within(await screen.findByRole('tabpanel', { name: '업적' }));
}

const TARGETS: Targets = {
  places: [{ id: TOWER, name: '종탑' }],
  monsters: [],
  items: [],
  npcs: [],
  quests: [{ id: HUNT, name: '구울 사냥' }],
};

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('업적 탭', () => {
  it('이름, 받는 법, 숨김, 그림, 받는 조건을 적어 업적을 더한다. 받는 조건이 없으면 저장하지 못한다', async () => {
    const { seen } = signedIn();
    const panel = await achievementsPanel();

    expect(await panel.findByText('업적이 없습니다.')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '업적 더하기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '새 업적' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '이름' }), '종지기');
    expect(dialog.getByText('받는 조건을 하나는 적어 주세요.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();

    await userEvent.type(dialog.getByRole('textbox', { name: '받는 법(선택)' }), '종탑에 올랐다');
    await userEvent.click(dialog.getByRole('checkbox', { name: /숨긴 업적/ }));
    const picture = within(dialog.getByRole('group', { name: '업적의 그림' }));
    await userEvent.click(picture.getByRole('button', { name: '그림 붙이기' }));
    await userEvent.click(await picture.findByRole('button', { name: '그림 1 고르기' }));
    await userEvent.click(dialog.getByRole('button', { name: '받는 조건 더하기' }));
    const when = within(dialog.getByRole('group', { name: '받는 조건 1' }));
    // 업적은 물건을 가져가지 않는다
    await userEvent.selectOptions(when.getByRole('combobox', { name: '종류' }), 'hold_item');
    expect(dialog.queryByRole('checkbox', { name: /가져간다/ })).toBeNull();
    await userEvent.selectOptions(when.getByRole('combobox', { name: '종류' }), 'reach_place');
    await userEvent.selectOptions(when.getByRole('combobox', { name: '대상' }), TOWER);
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.achievements).toEqual([
      { id: 'achievement-1', name: '종지기', description: '종탑에 올랐다', hidden: true, image_id: PICTURE, when: [REACH_TOWER], match: 'all' },
    ]);
    const list = within(await panel.findByRole('list', { name: '업적' }));
    expect(await list.findByText('숨김 · 그림 있음 · 받는 조건: 종탑에 닿는다')).toBeInTheDocument();
  });

  it('업적의 차례를 바꾸고 지운다', async () => {
    const achievements = [achievement('a', '첫걸음'), achievement('b', '종지기', { when: [HUNT_DONE] })];
    const { seen } = signedIn({ start: { achievements } });
    const panel = await achievementsPanel();

    const list = within(await panel.findByRole('list', { name: '업적' }));
    expect(list.getByText('받는 조건: 「구울 사냥」 성공')).toBeInTheDocument();
    expect(list.getByRole('button', { name: '첫걸음 위로' })).toBeDisabled();
    expect(list.getByRole('button', { name: '종지기 아래로' })).toBeDisabled();
    await userEvent.click(list.getByRole('button', { name: '종지기 위로' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.achievements as Achievement[]).map((one) => one.id)).toEqual(['b', 'a']);

    await userEvent.click(list.getByRole('button', { name: '첫걸음 고치기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '업적: 첫걸음' }));
    expect(dialog.getByText(/이름표: a\./)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '업적 지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1]?.achievements as Achievement[]).map((one) => one.id)).toEqual(['b']);
  });

  it('장이 있는 시나리오면 받는 조건에서 장을 고른다', async () => {
    const chapters = [
      { id: 'chapter-1', name: '도착', when: [], match: 'all', opens: { places: [], quests: [] } },
      { id: 'chapter-2', name: '끝', when: [REACH_TOWER], match: 'all', opens: { places: [], quests: [] } },
    ];
    const { seen } = signedIn({ start: { chapters } });
    const panel = await achievementsPanel();

    await userEvent.click(await panel.findByRole('button', { name: '업적 더하기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '새 업적' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '이름' }), '끝까지');
    await userEvent.click(dialog.getByRole('button', { name: '받는 조건 더하기' }));
    const when = within(dialog.getByRole('group', { name: '받는 조건 1' }));
    await userEvent.selectOptions(when.getByRole('combobox', { name: '종류' }), 'chapter_at_least');
    await userEvent.selectOptions(when.getByRole('combobox', { name: '장' }), 'chapter-2');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.achievements as Achievement[])[0]?.when).toEqual([{ kind: 'chapter_at_least', chapter: 'chapter-2', count: 1, consume: false }]);
  });

  it('그림이 내가 올린 것이 아니면(422) 다시 고르라고 한다', async () => {
    signedIn({
      start: { achievements: [achievement('a', '첫걸음', { image_id: PICTURE })] },
      patch: () => json(422, { detail: 'achievements.image_id: 지웠거나 남의 그림입니다' }),
    });
    const panel = await achievementsPanel();

    const list = within(await panel.findByRole('list', { name: '업적' }));
    await userEvent.click(list.getByRole('button', { name: '첫걸음 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));
    expect(await dialog.findByText('그림을 다시 골라 주세요. 지웠거나 내가 올리지 않은 그림입니다.')).toBeInTheDocument();
  });
});

describe('업적 입력', () => {
  it('새 업적의 이름표는 쓰지 않은 가장 작은 번호다', () => {
    expect(newAchievementId([])).toBe('achievement-1');
    expect(newAchievementId([{ id: 'achievement-1' }, { id: 'achievement-3' }])).toBe('achievement-2');
  });

  it('이름, 받는 법의 길이, 받는 조건을 본다', () => {
    const empty = achievementHints(achievementDraft(undefined));
    expect(empty.fields).toEqual({ name: '이름을 적어 주세요.', when: '받는 조건을 하나는 적어 주세요.' });
    const long = achievementHints({ ...achievementDraft(achievement('a', 'x'.repeat(41))), description: 'y'.repeat(201) });
    expect(long.fields).toEqual({ name: '이름은 40자까지입니다.', description: '받는 법은 200자까지입니다.' });
    const unpicked = achievementHints({ ...achievementDraft(achievement('a', '첫걸음')), when: [{ kind: 'reach_place', target: '', chapter: '', count: '1', consume: false }] });
    expect(unpicked.when).toEqual({ 0: '대상을 골라 주세요.' });
    expect(hasAchievementHints(achievementHints(achievementDraft(achievement('a', '첫걸음'))))).toBe(false);
  });

  it('보낼 때 가져가기를 빼고, 같은 id 는 바꾸고 새 id 는 끝에 더한다', () => {
    const consumed = { ...achievementDraft(achievement('a', ' 첫걸음 ')), when: [{ kind: 'hold_item' as const, target: TOWER, chapter: '', count: '2', consume: true }] };
    expect(toAchievement('a', consumed)).toEqual({ id: 'a', name: '첫걸음', description: '', hidden: false, image_id: null, when: [{ kind: 'hold_item', target: TOWER, count: 2, consume: false }], match: 'all' });
    const list = [achievement('a', '첫걸음'), achievement('b', '종지기')];
    expect(withAchievement(list, toAchievement('b', achievementDraft(achievement('b', '새 이름')))).map((one) => one.name)).toEqual(['첫걸음', '새 이름']);
    expect(withAchievement(list, toAchievement('c', achievementDraft(achievement('c', '셋째')))).map((one) => one.id)).toEqual(['a', 'b', 'c']);
    expect(withoutAchievement(list, 'a').map((one) => one.id)).toEqual(['b']);
  });

  it('목록 안에서만 한 칸 옮긴다', () => {
    const list = [achievement('a', '첫걸음'), achievement('b', '종지기'), achievement('c', '끝')];
    expect(canMoveAchievement(3, 0, -1)).toBe(false);
    expect(canMoveAchievement(3, 0, 1)).toBe(true);
    expect(canMoveAchievement(3, 2, 1)).toBe(false);
    expect(movedAchievement(list, 0, 1).map((one) => one.id)).toEqual(['b', 'a', 'c']);
    expect(movedAchievement(list, 2, 1).map((one) => one.id)).toEqual(['a', 'b', 'c']);
  });

  it('목록의 한 줄과 게시 점검의 업적 문제', () => {
    expect(achievementLine(achievement('a', '첫걸음', { when: [REACH_TOWER, HUNT_DONE], match: 'any' }), TARGETS)).toBe('받는 조건: 종탑에 닿는다 또는 「구울 사냥」 성공');
    expect(achievementLine(achievement('a', '첫걸음', { hidden: true }), TARGETS)).toBe('숨김 · 받는 조건: 종탑에 닿는다');
    for (const problem of ['missing', 'invalid', 'impossible']) expect(problemLine(`achievement_condition_${problem}`).section).toBe('achievements');
  });
});
