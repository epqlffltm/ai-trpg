// web/apps/web/src/pages/story/storyWorld.ts
// 세션의 판의 문서(WorldDocument)에서 화면에 보일 이름을 찾는다. 순수한 함수다.
// 문서는 서버가 받은 그대로라 모양을 믿지 않고 읽는다. 모르는 id 면 id 그대로다(판이 바뀌어도 화면이 깨지지 않게).
// 상태(날짜, 시간대, 장소, 장면의 인물)는 서버의 값이다. 모델이 쓴 글로 바꾸지 않는다.

import type { StoryState } from '../../api/story';
import type { StoryWorldDocument } from '../../api/storyWorlds';

type Named = { id: string; name: string };

function asDocument(document: Record<string, unknown>): Partial<StoryWorldDocument> {
  return document as Partial<StoryWorldDocument>;
}

function nameIn(list: Named[] | undefined, id: string): string {
  return list?.find((entry) => entry.id === id)?.name || id;
}

/** 인물의 이름. 판의 인물(cast)의 캐릭터 이름 */
export function castName(document: Record<string, unknown>, castId: string): string {
  const member = asDocument(document).cast?.find((entry) => entry.id === castId);
  return member?.character?.name || castId;
}

export function placeName(document: Record<string, unknown>, placeId: string): string {
  return nameIn(asDocument(document).places, placeId);
}

export function slotName(document: Record<string, unknown>, slotId: string): string {
  return nameIn(asDocument(document).slots, slotId);
}

export function endingName(document: Record<string, unknown>, endingId: string): string {
  return nameIn(asDocument(document).endings, endingId);
}

/** 말 조각의 말한 이. 서술(null)은 이름이 없다 */
export function speakerName(document: Record<string, unknown>, speaker: string | null): string | null {
  return speaker === null ? null : castName(document, speaker);
}

/** 기한까지 남은 날. 기한이 없으면 null. 마지막 날이 D-0 이다 */
export function daysLeft(document: Record<string, unknown>, day: number): number | null {
  const deadline = asDocument(document).deadline_days;
  return typeof deadline === 'number' ? Math.max(0, deadline - day) : null;
}

/** 머리의 한 줄. "3일째 · 저녁 · 학교 · D-97" 또는 엔딩을 봤으면 "엔딩: ○○" 이 붙는다 */
export function stateLine(document: Record<string, unknown>, state: StoryState): string {
  const left = daysLeft(document, state.day);
  return [
    `${state.day}일째`,
    slotName(document, state.slot),
    placeName(document, state.place),
    left !== null && state.ending === null ? `D-${left}` : null,
    state.ending !== null ? `엔딩: ${endingName(document, state.ending)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** 엔딩 뒤에 이어 가는 세계관(후일담)인가. 아니면 엔딩을 보면 끝이다 */
export function hasEpilogue(document: Record<string, unknown>): boolean {
  return asDocument(document).after_ending === 'epilogue';
}

/** 끝난 세션(엔딩을 봤고 후일담이 없다). 말과 행동을 받지 않는다 */
export function isEnded(document: Record<string, unknown>, state: StoryState): boolean {
  return state.ending !== null && !hasEpilogue(document);
}
