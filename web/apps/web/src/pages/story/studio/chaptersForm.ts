// web/apps/web/src/pages/story/studio/chaptersForm.ts
// 세계관의 장 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Chapter, docs/architecture/chapters.md).
//
//   - 장은 20 개까지이고 적은 차례가 장의 차례다. id 는 화면이 붙이고 판이 바뀌어도 그대로 둔다
//   - 첫 장에는 넘어오는 조건이 없다(처음부터 그 장이다). 그 뒤의 장에는 조건을 하나 이상 적는다
//   - 장마다 그 장부터 열리는 장소와 이벤트를 고른다. 하나는 한 장에만 적는다. 어느 장에도 고르지 않은 것은 처음부터 열려 있다
//   - 시작 장소는 첫 장 뒤의 장이 열지 못한다(게시 점검이 막는 것을 미리 알린다)

import type { StoryWorldChapter, StoryWorldDetail, StoryWorldUpdate } from '../../../api/storyWorlds';
import { conditionsDraft, conditionsHints, EMPTY_CONDITIONS, toConditions, type ConditionChoices, type ConditionsDraft } from './conditionsForm';

export const CHAPTERS_MAX = 20;
export const CHAPTER_NAME_MAX = 40;

export type ChapterDraft = { id: string; name: string; when: ConditionsDraft; places: string[]; events: string[] };

export function chapterDraft(chapter: StoryWorldChapter): ChapterDraft {
  return { id: chapter.id, name: chapter.name, when: conditionsDraft(chapter.when), places: [...chapter.opens.places], events: [...chapter.opens.events] };
}

export function chapterDrafts(world: Pick<StoryWorldDetail, 'chapters'>): ChapterDraft[] {
  return (world.chapters ?? []).map(chapterDraft);
}

export function addChapter(chapters: ChapterDraft[], id: string): ChapterDraft[] {
  if (chapters.length >= CHAPTERS_MAX) return chapters;
  return [...chapters, { id, name: '', when: EMPTY_CONDITIONS, places: [], events: [] }];
}

export function changeChapter(chapters: ChapterDraft[], id: string, change: (chapter: ChapterDraft) => ChapterDraft): ChapterDraft[] {
  return chapters.map((chapter) => (chapter.id === id ? change(chapter) : chapter));
}

export function removeChapter(chapters: ChapterDraft[], id: string): ChapterDraft[] {
  return chapters.filter((chapter) => chapter.id !== id);
}

export function moveChapterUp(chapters: ChapterDraft[], index: number): ChapterDraft[] {
  if (index <= 0 || index >= chapters.length) return chapters;
  const next = [...chapters];
  [next[index - 1], next[index]] = [next[index] as ChapterDraft, next[index - 1] as ChapterDraft];
  return next;
}

/** 그 장이 여는 장소나 이벤트 하나를 넣거나 뺀다. 넣으면 다른 장에서는 뺀다(하나는 한 장에만) */
export function toggleOpen(chapters: ChapterDraft[], id: string, kind: 'places' | 'events', contentId: string): ChapterDraft[] {
  const owner = chapters.find((chapter) => chapter.id === id);
  if (!owner) return chapters;
  const adding = !owner[kind].includes(contentId);
  return chapters.map((chapter) => {
    if (chapter.id === id) return { ...chapter, [kind]: adding ? [...chapter[kind], contentId] : chapter[kind].filter((entry) => entry !== contentId) };
    return adding ? { ...chapter, [kind]: chapter[kind].filter((entry) => entry !== contentId) } : chapter;
  });
}

export type ChapterHints = { name?: string; when?: string; opens?: string; conditions: Record<number, string> };

function chapterHints(chapter: ChapterDraft, index: number, earlier: ChapterDraft[], choices: ConditionChoices, startPlace: string | null): ChapterHints {
  const hints: ChapterHints = { conditions: index === 0 ? {} : conditionsHints(chapter.when, choices) };
  const name = chapter.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > CHAPTER_NAME_MAX) hints.name = `이름은 ${CHAPTER_NAME_MAX}자까지입니다.`;
  else if (earlier.some((other) => other.name.trim() === name)) hints.name = '같은 이름의 장이 이미 있습니다.';
  if (index > 0 && chapter.when.items.length === 0) hints.when = '넘어오는 조건을 하나 이상 적어 주세요.';
  if (index > 0 && startPlace !== null && chapter.places.includes(startPlace)) hints.opens = '시작 장소는 처음부터 열려 있어야 합니다. 첫 장 뒤의 장에서 빼 주세요.';
  return hints;
}

export function chaptersHints(chapters: ChapterDraft[], choices: ConditionChoices, startPlace: string | null): Record<string, ChapterHints> {
  const hints: Record<string, ChapterHints> = {};
  chapters.forEach((chapter, index) => {
    hints[chapter.id] = chapterHints(chapter, index, chapters.slice(0, index), choices, startPlace);
  });
  return hints;
}

export function hasChaptersHints(hints: Record<string, ChapterHints>): boolean {
  return Object.values(hints).some((entry) => Boolean(entry.name || entry.when || entry.opens) || Object.keys(entry.conditions).length > 0);
}

/** 장 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 첫 장은 조건을 보내지 않는다(위로 옮겨 첫 장이 된 장의 조건도 비운다) */
export function toChaptersBody(chapters: ChapterDraft[]): StoryWorldUpdate {
  return {
    chapters: chapters.map((chapter, index) => ({
      id: chapter.id,
      name: chapter.name.trim(),
      when: index === 0 ? toConditions(EMPTY_CONDITIONS) : toConditions(chapter.when),
      opens: { places: chapter.places, events: chapter.events },
    })),
  };
}
