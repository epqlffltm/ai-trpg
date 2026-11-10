// web/apps/web/src/pages/trpg/studio/scenarios/Chapters.test.tsx
// 시나리오의 장 탭(B9, #481). 첫 장 만들기(조건 없음), 다음 장(넘어오는 조건, 여는 장소와 퀘스트), 차례 바꾸기와 지우기의 막음,
// 다른 장이 연 것, 퀘스트의 조건에서 장 고르기, 게시 점검의 장 문제. 입력의 순수한 함수(chaptersForm.ts).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Chapter, QuestRule } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import {
  canMove,
  canRemove,
  chapterDraft,
  chapterHints,
  chapterLine,
  earlierChapters,
  followsLine,
  keepEarlierAfter,
  moved,
  newChapterId,
  toChapter,
  withoutChapter,
} from './chaptersForm';
import type { Targets } from './conditionsForm';
import { problemLine } from './publishProblems';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GATE = '00000000-0000-4000-8000-00000000c001';
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const TOWER = '00000000-0000-4000-8000-00000000c004';
const HUNT = '00000000-0000-4000-8000-00000000f001';
const COLLAPSE = '00000000-0000-4000-8000-00000000f003';

const DOOR = { from_place: GATE, to_place: CRYPT, two_way: true, visibility: 'open', find: null, travel_minutes: null, cross: null, lock: null, bar: null, force: null };

function chapter(id: string, name: string, extra: Partial<Chapter> = {}): Chapter {
  return { id, name, when: [], match: 'all', opens: { places: [], quests: [] }, after: [], ...extra };
}

const REACH_CRYPT = { kind: 'reach_place' as const, target: CRYPT, count: 1, consume: false };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenarioDetail({ rulebook_id: RULEBOOK, lorebook_ids: [LOREBOOK], start_place: GATE, routes: [DOOR], ...start });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [
        entry(GATE, '수도원 문', 'place'),
        entry(CRYPT, '지하 묘지', 'place'),
        entry(TOWER, '종탑', 'place'),
        entry(HUNT, '구울 사냥', 'event'),
        entry(COLLAPSE, '묘지 붕괴', 'event'),
      ]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  });
}

function patches(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as Record<string, unknown>);
}

async function chaptersPanel() {
  return within(await screen.findByRole('tabpanel', { name: '장' }));
}

const TARGETS: Targets = {
  places: [
    { id: GATE, name: '수도원 문' },
    { id: CRYPT, name: '지하 묘지' },
  ],
  monsters: [],
  items: [],
  npcs: [],
  quests: [{ id: COLLAPSE, name: '묘지 붕괴' }],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장 탭', () => {
  it('첫 장은 넘어오는 조건 없이 만든다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const panel = await chaptersPanel();
    expect(await panel.findByText('장이 없습니다. 장이 없으면 모든 것이 처음부터 열려 있습니다.')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '장 더하기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '새 장(1장)' }));
    expect(dialog.getByText('첫 장입니다. 테이블은 이 장에서 시작하므로 넘어오는 조건이 없습니다.')).toBeInTheDocument();
    expect(dialog.queryByRole('button', { name: '넘어오는 조건 더하기' })).toBeNull();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(dialog.getByRole('textbox', { name: '이름' }), '도착');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.chapters).toEqual([{ id: 'chapter-1', name: '도착', when: [], match: 'all', opens: { places: [], quests: [] }, after: [] }]);
  });

  it('다음 장은 넘어오는 조건이 있어야 하고, 맵의 장소와 퀘스트를 연다. 시작 장소는 열지 못한다', async () => {
    const { seen } = signedIn({ chapters: [chapter('chapter-1', '도착')] });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const panel = await chaptersPanel();
    await userEvent.click(await panel.findByRole('button', { name: '장 더하기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '새 장(2장)' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '이름' }), '지하');
    expect(dialog.getByText('첫 장 뒤의 장에는 넘어오는 조건을 하나는 적어 주세요.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '넘어오는 조건 더하기' }));
    const when = within(dialog.getByRole('group', { name: '넘어오는 조건 1' }));
    // 장의 넘어오는 조건에는 장을 쓰지 않는다
    expect(within(when.getByRole('combobox', { name: '종류' })).queryByRole('option', { name: '지금 장이 그 장 이상이다' })).toBeNull();
    await userEvent.selectOptions(when.getByRole('combobox', { name: '대상' }), CRYPT);

    const places = within(dialog.getByRole('group', { name: '여는 장소' }));
    // 맵의 장소만 고른다(종탑은 맵에 없다)
    expect(places.queryByRole('checkbox', { name: '종탑' })).toBeNull();
    await userEvent.click(places.getByRole('checkbox', { name: '수도원 문' }));
    expect(dialog.getByText('시작 장소는 처음부터 열려 있어야 합니다. 첫 장 뒤에 열지 못합니다.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(places.getByRole('checkbox', { name: '수도원 문' }));
    await userEvent.click(places.getByRole('checkbox', { name: '지하 묘지' }));
    await userEvent.click(within(dialog.getByRole('group', { name: '여는 퀘스트' })).getByRole('checkbox', { name: '묘지 붕괴' }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.chapters).toEqual([
      { id: 'chapter-1', name: '도착', when: [], match: 'all', opens: { places: [], quests: [] }, after: [] },
      { id: 'chapter-2', name: '지하', when: [REACH_CRYPT], match: 'all', opens: { places: [CRYPT], quests: [COLLAPSE] }, after: [] },
    ]);
  });

  it('첫 자리는 옮기지 않고 뒤의 장끼리 옮긴다. 다른 장이 있으면 첫 장은 지우지 못한다', async () => {
    const chapters = [chapter('a', '도착'), chapter('b', '지하', { when: [REACH_CRYPT] }), chapter('c', '끝', { when: [REACH_CRYPT] })];
    const { seen } = signedIn({ chapters });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const list = within(await (await chaptersPanel()).findByRole('list', { name: '장' }));
    expect(list.getByText('처음부터 · 여는 것 없음')).toBeInTheDocument();
    expect(list.getAllByText('넘어옴: 지하 묘지에 닿는다 · 여는 것 없음')).toHaveLength(2);
    expect(list.getByRole('button', { name: '도착 아래로' })).toBeDisabled();
    expect(list.getByRole('button', { name: '지하 위로' })).toBeDisabled();
    expect(list.getByRole('button', { name: '끝 아래로' })).toBeDisabled();
    await userEvent.click(list.getByRole('button', { name: '지하 아래로' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.chapters as Chapter[]).map((one) => one.id)).toEqual(['a', 'c', 'b']);

    await userEvent.click(list.getByRole('button', { name: '도착 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: '장 지우기' })).toBeDisabled();
    expect(dialog.getByText('다른 장이 있으면 첫 장은 지우지 못합니다. 뒤의 장부터 지우세요.')).toBeInTheDocument();
  });

  it('앞의 장을 골라 갈림길을 만들고, 줄에 어느 장 다음인지 보인다(#289)', async () => {
    const chapters = [
      chapter('a', '도착'),
      chapter('b', '마을', { when: [REACH_CRYPT], after: ['a'] }),
      chapter('c', '들', { when: [REACH_CRYPT], after: ['a'] }),
      chapter('d', '끝', { when: [REACH_CRYPT] }),
    ];
    const { seen } = signedIn({ chapters });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const list = within(await (await chaptersPanel()).findByRole('list', { name: '장' }));
    expect(list.getAllByText('「도착」 다음')).toHaveLength(2);
    await userEvent.click(list.getByRole('button', { name: '끝 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    const after = within(dialog.getByRole('group', { name: '앞의 장' }));
    expect(after.getAllByRole('checkbox')).toHaveLength(3);
    expect(dialog.getByText(/고르지 않으면 바로 앞의 장\(「들」\) 다음입니다/)).toBeInTheDocument();
    await userEvent.click(after.getByRole('checkbox', { name: '2장: 마을' }));
    await userEvent.click(after.getByRole('checkbox', { name: '3장: 들' }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.chapters as Chapter[]).map((one) => one.after)).toEqual([[], ['a'], ['a'], ['b', 'c']]);
    expect(await list.findByText('「마을」, 「들」 다음')).toBeInTheDocument();
  });

  it('첫 장의 창에는 앞의 장이 없다', async () => {
    signedIn({ chapters: [chapter('a', '도착'), chapter('b', '마을', { when: [REACH_CRYPT] })] });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const list = within(await (await chaptersPanel()).findByRole('list', { name: '장' }));
    await userEvent.click(list.getByRole('button', { name: '도착 고치기' }));
    expect(within(await screen.findByRole('dialog')).queryByRole('group', { name: '앞의 장' })).toBeNull();
  });

  it('다른 장이 연 것은 그 장을 적고 고르지 못한다', async () => {
    const chapters = [chapter('a', '도착'), chapter('b', '지하', { when: [REACH_CRYPT], opens: { places: [CRYPT], quests: [] } }), chapter('c', '끝', { when: [REACH_CRYPT] })];
    signedIn({ chapters });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=chapters`);

    const list = within(await (await chaptersPanel()).findByRole('list', { name: '장' }));
    await userEvent.click(list.getByRole('button', { name: '끝 고치기' }));
    const places = within(within(await screen.findByRole('dialog')).getByRole('group', { name: '여는 장소' }));
    expect(places.getByRole('checkbox', { name: '지하 묘지' })).toBeDisabled();
    expect(places.getByText('2장이 엽니다')).toBeInTheDocument();
  });

  it('장이 있는 시나리오면 퀘스트의 조건에서 장을 고른다', async () => {
    const chapters = [chapter('a', '도착'), chapter('b', '지하', { when: [REACH_CRYPT] })];
    const { seen } = signedIn({ chapters });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=quests`);

    const list = within(await within(await screen.findByRole('tabpanel', { name: '퀘스트·사건' })).findByRole('list', { name: '퀘스트' }));
    await userEvent.click(list.getByRole('button', { name: '구울 사냥 퀘스트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '이루는 조건 더하기' }));
    const goal = within(dialog.getByRole('group', { name: '이루는 조건 1' }));
    await userEvent.selectOptions(goal.getByRole('combobox', { name: '종류' }), 'chapter_at_least');
    await userEvent.selectOptions(goal.getByRole('combobox', { name: '장' }), 'b');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.quests as QuestRule[])[0]?.conditions).toEqual([{ kind: 'chapter_at_least', chapter: 'b', count: 1, consume: false }]);
  });

  it('장이 없으면 퀘스트의 조건에 장이 없다', async () => {
    signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=quests`);

    const list = within(await within(await screen.findByRole('tabpanel', { name: '퀘스트·사건' })).findByRole('list', { name: '퀘스트' }));
    await userEvent.click(list.getByRole('button', { name: '구울 사냥 퀘스트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '이루는 조건 더하기' }));
    const kinds = within(within(dialog.getByRole('group', { name: '이루는 조건 1' })).getByRole('combobox', { name: '종류' }));
    expect(kinds.queryByRole('option', { name: '지금 장이 그 장 이상이다' })).toBeNull();
  });
});

describe('장 입력', () => {
  const chapters = [chapter('chapter-1', '도착'), chapter('chapter-3', '지하', { when: [REACH_CRYPT], opens: { places: [CRYPT], quests: [COLLAPSE] } })];

  it('새 장의 이름표는 쓰지 않은 가장 작은 번호다', () => {
    expect(newChapterId([])).toBe('chapter-1');
    expect(newChapterId(chapters)).toBe('chapter-2');
  });

  it('이름, 넘어오는 조건, 다른 장이 연 것, 시작 장소를 본다', () => {
    const context = { first: false, chapters, chapterId: 'new', startPlace: GATE };
    const blank = chapterHints(chapterDraft(undefined), context);
    expect(blank.fields).toMatchObject({ name: '이름을 적어 주세요.', when: '첫 장 뒤의 장에는 넘어오는 조건을 하나는 적어 주세요.' });
    const taken = chapterHints({ ...chapterDraft(chapters[1]), name: '끝', quests: [COLLAPSE] }, context);
    expect(taken.fields.opens).toContain('다른 장이 이미 연 것');
    // 첫 장은 조건이 없어도 되고 시작 장소를 열어도 된다(처음부터 열려 있다)
    expect(chapterHints({ ...chapterDraft(undefined), name: '도착', places: [GATE] }, { ...context, first: true, chapters: [] })).toEqual({ when: {}, fields: {} });
    expect(chapterHints({ ...chapterDraft(chapters[1]), places: [GATE] }, { ...context, chapterId: 'chapter-3' }).fields.places).toContain('시작 장소');
  });

  it('첫 장은 조건을 보내지 않고, 첫 자리는 옮기거나 (다른 장이 있으면) 지우지 못한다', () => {
    expect(toChapter('chapter-1', { ...chapterDraft(chapters[1]), name: ' 도착 ' }, true)).toEqual({ id: 'chapter-1', name: '도착', when: [], match: 'all', opens: { places: [CRYPT], quests: [COLLAPSE] }, after: [] });
    expect([canMove(3, 0, 1), canMove(3, 1, -1), canMove(3, 1, 1), canMove(3, 2, 1)]).toEqual([false, false, true, false]);
    expect(moved(chapters, 0, 1).map((one) => one.id)).toEqual(['chapter-1', 'chapter-3']);
    expect([canRemove(chapters, 0), canRemove(chapters, 1), canRemove(chapters.slice(0, 1), 0)]).toEqual([false, true, true]);
    expect(withoutChapter(chapters, 'chapter-3').map((one) => one.id)).toEqual(['chapter-1']);
  });

  it('갈림길(after)은 받은 대로 보내고, 지우거나 옮겨 앞의 장이 아니게 된 것은 뺀다(#289)', () => {
    const forked = [
      chapter('a', '도착'),
      chapter('b', '마을', { when: [REACH_CRYPT], after: ['a'] }),
      chapter('c', '들', { when: [REACH_CRYPT], after: ['a'] }),
      chapter('d', '끝', { when: [REACH_CRYPT], after: ['b', 'c'] }),
    ];
    expect(toChapter('d', chapterDraft(forked[3]), false).after).toEqual(['b', 'c']);
    expect(toChapter('a', { ...chapterDraft(forked[3]) }, true).after).toEqual([]);
    expect(withoutChapter(forked, 'b').map((one) => one.after)).toEqual([[], ['a'], ['c']]);
    // 들(c)을 끝(d) 뒤로 옮기면 끝은 들 다음일 수 없다
    expect(moved(forked, 2, 1).map((one) => [one.id, one.after])).toEqual([
      ['a', []],
      ['b', ['a']],
      ['d', ['b']],
      ['c', ['a']],
    ]);
    expect(keepEarlierAfter([toChapter('x', { ...chapterDraft(undefined), name: 'x', after: ['y'] }, false)])[0]?.after).toEqual([]);
    expect(earlierChapters(forked, 2).map((one) => one.id)).toEqual(['a', 'b']);
    expect(earlierChapters(forked, null).map((one) => one.id)).toEqual(['a', 'b', 'c', 'd']);
    expect([followsLine(forked[0]!, 0, forked), followsLine(forked[3]!, 3, forked)]).toEqual([null, '「마을」, 「들」 다음']);
    expect(followsLine(chapter('z', 'z', { after: ['gone'] }), 1, forked)).toBe('(찾을 수 없음) 다음');
    expect(followsLine(chapter('z', 'z'), 1, forked)).toBeNull();
  });

  it('목록의 한 줄과 게시 점검의 장 문제', () => {
    expect(chapterLine(chapters[1]!, 1, TARGETS)).toBe('넘어옴: 지하 묘지에 닿는다 · 열림: 장소 1, 퀘스트 1');
    const problems = ['place_off_map', 'quest_missing', 'quest_not_event', 'condition_missing', 'condition_invalid', 'condition_impossible', 'start_locked'];
    for (const problem of problems) expect(problemLine(`chapter_${problem}`).section).toBe('chapters');
    expect(problemLine('chapter_place_off_map').text).toContain('맵에 없는 장소');
  });
});
