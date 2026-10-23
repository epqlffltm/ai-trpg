// web/apps/web/src/pages/chat/studio/characters/startsForm.ts
// 캐릭터의 시작 상황 목록의 입력. 순수한 함수다.
// 5 개까지. 제목(30자)은 대화를 열 때 고르는 목록에, 상황(2,000자)은 모델에 간다. 시각(0~23시)은 1일째의 그 시각에서 시작한다.
// 목록의 차례가 고르는 화면의 차례다. 처음 있는 장소와 시작 소지품은 캐릭터에 하나씩이라 지도·물건 탭에 있다.

import type { AssetCharacterStart, AssetCharacterUpdate } from '../../../../api/types';

export const STARTS_MAX = 5;
export const START_TITLE_MAX = 30;
export const SITUATION_MAX = 2000;
export const START_HOUR_DEFAULT = 12;

/** 시각은 글로 들고 있다가 보낼 때 바꾼다 */
export type StartDraft = { title: string; situation: string; hour: string };

export function startDrafts(starts: AssetCharacterStart[]): StartDraft[] {
  return starts.map((start) => ({ title: start.title, situation: start.situation, hour: String(start.hour ?? START_HOUR_DEFAULT) }));
}

/** 0~23 의 정수면 그 수, 아니면 null */
export function hourOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) return null;
  const hour = Number(trimmed);
  return hour <= 23 ? hour : null;
}

/** 시작 상황마다의 문제. 차례(0 부터) → 칸 이름 → 글 */
export function startsHints(starts: StartDraft[]): Record<number, Record<string, string>> {
  const hints: Record<number, Record<string, string>> = {};
  starts.forEach((start, index) => {
    const found: Record<string, string> = {};
    const title = start.title.trim();
    if (title === '') found.title = '제목을 적어 주세요.';
    else if (title.length > START_TITLE_MAX) found.title = `제목은 ${START_TITLE_MAX}자까지입니다.`;
    if (start.situation.trim() === '') found.situation = '상황을 적어 주세요.';
    else if (start.situation.length > SITUATION_MAX) found.situation = `상황은 ${SITUATION_MAX}자까지입니다.`;
    if (hourOf(start.hour) === null) found.hour = '0~23 사이의 정수입니다.';
    if (Object.keys(found).length > 0) hints[index] = found;
  });
  return hints;
}

/** 빈 시작 상황을 끝에 더한다. 가득 찼으면 그대로 */
export function addStart(starts: StartDraft[]): StartDraft[] {
  return starts.length < STARTS_MAX ? [...starts, { title: '', situation: '', hour: String(START_HOUR_DEFAULT) }] : starts;
}

export function removeStart(starts: StartDraft[], index: number): StartDraft[] {
  return starts.filter((_, at) => at !== index);
}

export function changeStart(starts: StartDraft[], index: number, changes: Partial<StartDraft>): StartDraft[] {
  return starts.map((start, at) => (at === index ? { ...start, ...changes } : start));
}

/** 한 칸 앞으로. 맨 앞이면 그대로 */
export function moveStartUp(starts: StartDraft[], index: number): StartDraft[] {
  if (index <= 0 || index >= starts.length) return starts;
  const moved = [...starts];
  [moved[index - 1], moved[index]] = [moved[index] as StartDraft, moved[index - 1] as StartDraft];
  return moved;
}

/** 시작 상황 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 제목만 다듬는다 */
export function toStartsBody(starts: StartDraft[]): AssetCharacterUpdate {
  return {
    starts: starts.map((start) => ({ title: start.title.trim(), situation: start.situation, hour: hourOf(start.hour) ?? START_HOUR_DEFAULT })),
  };
}
