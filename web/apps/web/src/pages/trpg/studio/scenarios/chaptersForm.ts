// web/apps/web/src/pages/trpg/studio/scenarios/chaptersForm.ts
// 시나리오의 장(B9 장 탭, #481). 장 하나의 입력과 장 목록을 바꾸는 것. 순수한 함수다(서버의 Chapter·check_chapters 를 따른다).
//
// - 목록의 차례가 장의 차례다. 첫 장은 처음부터 그 장이라 넘어오는 조건이 없고, 그 뒤의 장에는 하나 이상 적는다
// - 넘어오는 조건은 퀘스트의 조건과 같은 모양이다(가져가기 없음, 장 조건 없음)
// - 여는 것: 그 장부터 열리는 맵의 장소와 퀘스트(사건 항목). 하나는 한 장에만 적는다. 시작 장소는 첫 장 뒤에 열지 못한다
// - id 는 판이 바뀌어도 그대로 두는 이름표다. 만들 때 정하고(chapter-1, chapter-2 …) 고치지 않는다.
//   조건의 장(chapter_at_least)과 테이블의 지금 장이 이것을 가리킨다
// - 갈림길(after, #289): 그 장이 어느 장 다음에 올 수 있는지. 목록에서 앞의 장만 적는다. 비우면 바로 앞의 장 다음이다.
//   고르는 칸은 아직 없다. 받은 것을 그대로 보내고, 지우거나 옮겨 앞의 장이 아니게 된 것은 뺀다

import type { Chapter, ChapterBody, QuestMatch } from '../../../../api/types';
import { conditionDrafts, conditionLine, conditionsHints, toConditions, type ConditionDraft, type Targets } from './conditionsForm';

export const MAX_CHAPTERS = 20;
export const CHAPTER_NAME_MAX_LENGTH = 40;
export const CHAPTER_MAX_OPENS = 100;

export type ChapterDraft = {
  name: string;
  when: ConditionDraft[];
  match: QuestMatch;
  places: string[];
  quests: string[];
  after: string[];
};

export function chapterDraft(chapter: Chapter | undefined): ChapterDraft {
  return {
    name: chapter?.name ?? '',
    when: conditionDrafts(chapter?.when ?? []),
    match: chapter?.match ?? 'all',
    places: chapter?.opens.places ?? [],
    quests: chapter?.opens.quests ?? [],
    after: chapter?.after ?? [],
  };
}

/** 새 장의 id. 쓰지 않은 chapter-N 가운데 가장 작은 것 */
export function newChapterId(chapters: Pick<Chapter, 'id'>[]): string {
  const used = new Set(chapters.map((chapter) => chapter.id));
  let number = 1;
  while (used.has(`chapter-${number}`)) number += 1;
  return `chapter-${number}`;
}

/** 이 장이 아닌 장들이 이미 연 것. id → 몇째 장(1 부터) */
export function openedElsewhere(chapters: Chapter[], chapterId: string): Map<string, number> {
  const opened = new Map<string, number>();
  chapters.forEach((chapter, index) => {
    if (chapter.id === chapterId) return;
    for (const one of [...(chapter.opens.places ?? []), ...(chapter.opens.quests ?? [])]) opened.set(one, index + 1);
  });
  return opened;
}

export type ChapterHints = { when: Record<number, string>; fields: Record<string, string> };

type HintContext = { first: boolean; chapters: Chapter[]; chapterId: string; startPlace: string | null };

/** 장 하나의 문제. first: 첫 장인가(만들 때는 목록이 비었는가) */
export function chapterHints(draft: ChapterDraft, { first, chapters, chapterId, startPlace }: HintContext): ChapterHints {
  const fields: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') fields.name = '이름을 적어 주세요.';
  else if (name.length > CHAPTER_NAME_MAX_LENGTH) fields.name = `이름은 ${CHAPTER_NAME_MAX_LENGTH}자까지입니다.`;
  if (!first && draft.when.length === 0) fields.when = '첫 장 뒤의 장에는 넘어오는 조건을 하나는 적어 주세요.';
  const elsewhere = openedElsewhere(chapters, chapterId);
  if (draft.places.some((one) => elsewhere.has(one)) || draft.quests.some((one) => elsewhere.has(one))) fields.opens = '다른 장이 이미 연 것이 있습니다. 하나는 한 장에만 엽니다.';
  if (!first && startPlace !== null && draft.places.includes(startPlace)) fields.places = '시작 장소는 처음부터 열려 있어야 합니다. 첫 장 뒤에 열지 못합니다.';
  if (draft.places.length > CHAPTER_MAX_OPENS) fields.places = `장소는 ${CHAPTER_MAX_OPENS}개까지 엽니다.`;
  if (draft.quests.length > CHAPTER_MAX_OPENS) fields.quests = `퀘스트는 ${CHAPTER_MAX_OPENS}개까지 엽니다.`;
  return { when: first ? {} : conditionsHints(draft.when, ''), fields };
}

export function hasChapterHints(hints: ChapterHints): boolean {
  return Object.keys(hints.when).length > 0 || Object.keys(hints.fields).length > 0;
}

/** 보낼 장. 첫 장은 넘어오는 조건과 앞의 장을 보내지 않는다 */
export function toChapter(id: string, draft: ChapterDraft, first: boolean): ChapterBody {
  return {
    id,
    name: draft.name.trim(),
    when: first ? [] : toConditions(draft.when, false),
    match: draft.match,
    opens: { places: draft.places, quests: draft.quests },
    after: first ? [] : draft.after,
  };
}

/** 받은 장을 보낼 모양으로 */
function asBody(chapter: Chapter, index: number): ChapterBody {
  return toChapter(chapter.id, chapterDraft(chapter), index === 0);
}

/** 그 장을 바꾸거나(같은 id) 끝에 더한 목록 */
export function withChapter(chapters: Chapter[], chapter: ChapterBody): ChapterBody[] {
  const bodies = chapters.map(asBody);
  return bodies.some((one) => one.id === chapter.id) ? bodies.map((one) => (one.id === chapter.id ? chapter : one)) : [...bodies, chapter];
}

/** 장마다 앞의 장(after)에서 목록의 앞에 없는 장을 뺀다. 지우거나 옮긴 뒤에 서버의 모양(앞의 장만)을 지킨다 */
export function keepEarlierAfter(bodies: ChapterBody[]): ChapterBody[] {
  return bodies.map((body, index) => {
    const earlier = new Set(bodies.slice(0, index).map((one) => one.id));
    return { ...body, after: body.after.filter((one) => earlier.has(one)) };
  });
}

/** 그 장을 지운 목록 */
export function withoutChapter(chapters: Chapter[], chapterId: string): ChapterBody[] {
  return keepEarlierAfter(chapters.map(asBody).filter((one) => one.id !== chapterId));
}

/**
 * 다른 장이 있으면 첫 장은 지우지 못한다. 다음 장이 첫 장이 되면 그 넘어오는 조건이 갈 곳이 없다.
 * 뒤의 장부터 지운다
 */
export function canRemove(chapters: Chapter[], index: number): boolean {
  return index > 0 || chapters.length === 1;
}

/**
 * 장을 한 칸 옮길 수 있는가. 첫 자리는 옮기지 않는다(첫 장은 조건이 없고 뒤의 장은 조건이 있어야 한다).
 * 둘째 장부터 그 뒤의 장들끼리만 옮긴다
 */
export function canMove(length: number, index: number, step: -1 | 1): boolean {
  const target = index + step;
  return index >= 1 && target >= 1 && target < length;
}

/** 그 장을 한 칸 옮긴 목록. 옮길 수 없으면 그대로 */
export function moved(chapters: Chapter[], index: number, step: -1 | 1): ChapterBody[] {
  const bodies = chapters.map(asBody);
  if (!canMove(chapters.length, index, step)) return bodies;
  const target = index + step;
  [bodies[index], bodies[target]] = [bodies[target]!, bodies[index]!];
  return keepEarlierAfter(bodies);
}

/** 목록의 한 줄. "처음부터 · 여는 것 없음", "넘어옴: 종탑에 닿는다 · 열림: 장소 2, 퀘스트 1" */
export function chapterLine(chapter: Chapter, index: number, targets: Targets): string {
  const when = index === 0 ? '처음부터' : `넘어옴: ${chapter.when.map((one) => conditionLine(one, targets)).join(chapter.match === 'all' ? ' 그리고 ' : ' 또는 ')}`;
  const places = chapter.opens.places?.length ?? 0;
  const quests = chapter.opens.quests?.length ?? 0;
  const opens = places + quests === 0 ? '여는 것 없음' : `열림: ${[places ? `장소 ${places}` : '', quests ? `퀘스트 ${quests}` : ''].filter(Boolean).join(', ')}`;
  return `${when} · ${opens}`;
}
