// web/apps/web/src/pages/story/storyMapView.ts
// 지도(D3)에 보일 것. 세션의 세계관 칸(view)과 상태만 받는 순수한 함수다.
// 거기 있는 인물은 서버가 정한다(가 본 곳, 만난 적 있는 인물, 제작자의 지도 보이기를 통과한 인물). 화면은 받은 것만 그린다.
// 도착 시각은 화면이 셈한다. 시각의 셈은 엔진(story-server/app/engine/clock.py)과 같다: 첫 시간대 전은 마지막 시간대다.

import type { StoryState, StoryView } from '../../api/story';
import { castName, placeName } from './storyWorld';

const MINUTES_PER_DAY = 1440;

/** 그 시각(1일째 0시부터의 분)의 며칠째와 시간대의 id */
export function clockAt(view: Pick<StoryView, 'slots'>, minutes: number): { day: number; slot: string | null } {
  const day = Math.floor(minutes / MINUTES_PER_DAY) + 1;
  const hour = Math.floor((minutes % MINUTES_PER_DAY) / 60);
  const ordered = [...view.slots].sort((a, b) => a.start_hour - b.start_hour);
  const slot = [...ordered].reverse().find((entry) => entry.start_hour <= hour) ?? ordered.at(-1);
  return { day, slot: slot?.id ?? null };
}

/** 그 길로 가면 언제 닿는가. "저녁 → 밤", 날이 바뀌면 "저녁 → 4일째 아침", 시간대가 그대로면 "저녁 그대로" */
export function arrivalText(view: Pick<StoryView, 'slots'>, state: Pick<StoryState, 'minutes'>, minutes: number): string {
  const now = clockAt(view, state.minutes);
  const then = clockAt(view, state.minutes + minutes);
  const name = (slot: string | null) => (slot ? (view.slots.find((entry) => entry.id === slot)?.name ?? slot) : '');
  if (then.day !== now.day) return `${name(now.slot)} → ${then.day}일째 ${name(then.slot)}`;
  return then.slot === now.slot ? `${name(now.slot)} 그대로` : `${name(now.slot)} → ${name(then.slot)}`;
}

export type KnownPlace = { id: string; name: string; here: boolean; visited: boolean; cast: string[] };

/** 지도의 아는 장소들(서버가 보낸 차례). 지금 있는 곳 표시, 가 본 곳, 거기 보이는 인물의 이름 */
export function knownPlaces(view: StoryView, state: Pick<StoryState, 'place'>): KnownPlace[] {
  return view.map.map((entry) => ({
    id: entry.id,
    name: placeName(view, entry.id),
    here: entry.id === state.place,
    visited: entry.visited,
    cast: entry.cast.map((id) => castName(view, id)),
  }));
}

/** 함께 다니는 인물의 이름 */
export function companionNames(view: StoryView, state: Pick<StoryState, 'companions'>): string[] {
  return state.companions.map((id) => castName(view, id));
}
