// web/apps/web/src/pages/story/storyWorld.ts
// 세션의 세계관 칸(view)에서 화면에 보일 이름과 머리의 줄을 찾는다. 순수한 함수다.
// view 는 서버가 이 가지에 맞춰 보여도 되는 것만 고른 것이다. 만나지 않은 숨김 인물과 못 본 엔딩의 이름은 오지 않는다.
// 모르는 id 면 인물은 "???", 그 밖은 id 그대로다(판이 바뀌어도 화면이 깨지지 않게). 상태는 서버의 값이고 모델이 쓴 글로 바꾸지 않는다.

import type { StoryState, StoryView, StoryViewCast } from '../../api/story';

type Named = { id: string; name: string | null };

function nameIn(list: Named[], id: string): string {
  return list.find((entry) => entry.id === id)?.name || id;
}

export function castOf(view: StoryView, castId: string): StoryViewCast | undefined {
  return view.cast.find((entry) => entry.id === castId);
}

/** 인물의 이름. 실루엣이거나 모르는 인물이면 "???" */
export function castName(view: StoryView, castId: string): string {
  return castOf(view, castId)?.name || '???';
}

export function placeName(view: Pick<StoryView, 'places'>, placeId: string): string {
  return nameIn(view.places, placeId);
}

export function slotName(view: Pick<StoryView, 'slots'>, slotId: string): string {
  return nameIn(view.slots, slotId);
}

/** 엔딩의 이름. 본 엔딩만 이름이 온다 */
export function endingName(view: StoryView, endingId: string): string {
  return nameIn(view.endings, endingId);
}

export function itemName(view: StoryView, itemId: string): string {
  return nameIn(view.items, itemId);
}

export function eventName(view: StoryView, eventId: string): string {
  return nameIn(view.events, eventId);
}

/** 말 조각의 말한 이. 서술(null)은 이름이 없다 */
export function speakerName(view: StoryView, speaker: string | null): string | null {
  return speaker === null ? null : castName(view, speaker);
}

/** 기한까지 남은 날. 기한이 없으면 null. 마지막 날이 D-0 이다 */
export function daysLeft(deadline: number | null | undefined, day: number): number | null {
  return typeof deadline === 'number' ? Math.max(0, deadline - day) : null;
}

/** 머리의 한 줄. "3일째 · 저녁 · 학교 · D-97" 또는 엔딩을 봤으면 "엔딩: ○○" 이 붙는다 */
export function stateLine(view: StoryView, state: StoryState): string {
  const left = daysLeft(view.deadline_days, state.day);
  return [
    `${state.day}일째`,
    slotName(view, state.slot),
    placeName(view, state.place),
    left !== null && state.ending === null ? `D-${left}` : null,
    state.ending !== null ? `엔딩: ${endingName(view, state.ending)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** 엔딩 뒤에 이어 가는 세계관(후일담)인가. 아니면 엔딩을 보면 끝이다 */
export function hasEpilogue(view: Pick<StoryView, 'after_ending'>): boolean {
  return view.after_ending === 'epilogue';
}

/** 끝난 세션(엔딩을 봤고 후일담이 없다). 말과 행동을 받지 않는다 */
export function isEnded(view: Pick<StoryView, 'after_ending'>, state: Pick<StoryState, 'ending'>): boolean {
  return state.ending !== null && !hasEpilogue(view);
}

/** 계정에 남는 엔딩의 수(엔딩 n/m 의 m) */
export function countedEndings(view: Pick<StoryView, 'endings'>): number {
  return view.endings.filter((ending) => ending.unlock).length;
}
