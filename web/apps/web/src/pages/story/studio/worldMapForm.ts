// web/apps/web/src/pages/story/studio/worldMapForm.ts
// 세계관의 지도 탭(장소, 장소의 그림, 길)의 입력. 순수한 함수다. 상한은 서버와 같다(asset-server/app/worlds/models.py).
//
//   - 장소의 id 는 화면이 붙인다(keys.ts). 그림은 기본 배경과, 시간대마다의 배경(열쇠가 그 세계관의 시간대 id)이다
//   - 보낼 때 가장 최근에 받은 세계관(latest)의 시간대에 없는 배경은 뗀다(진행 탭에서 시간대를 지웠을 수 있다)
//   - 장소를 지우면 그 장소를 잇는 길을 지운다. 시작 장소였으면 시작 장소를 비워 함께 보낸다
//   - 길은 서로 다른 두 장소를 잇고, 같은 두 장소 사이에는 하나다(차례는 가리지 않는다). 시간은 0~1440 분

import type { StoryWorldDetail, StoryWorldPlace, StoryWorldUpdate } from '../../../api/storyWorlds';
import { minutesOf, PATH_MAX_MINUTES, PLACE_DESCRIPTION_MAX, PLACE_NAME_MAX, type PathDraft } from '../../chat/studio/characters/mapForm';

export { PLACE_DESCRIPTION_MAX, PLACE_NAME_MAX };
export const WORLD_PLACES_MAX = 50;
export const WORLD_PATHS_MAX = 150;

export type WorldMapDraft = { places: StoryWorldPlace[]; paths: PathDraft[] };

export function worldMapDraft(world: StoryWorldDetail): WorldMapDraft {
  return { places: world.places, paths: world.paths.map((path) => ({ a: path.a, b: path.b, minutes: String(path.minutes) })) };
}

export function addWorldPlace(draft: WorldMapDraft, id: string): WorldMapDraft {
  if (draft.places.length >= WORLD_PLACES_MAX) return draft;
  return { ...draft, places: [...draft.places, { id, name: '', description: '', image_id: null, backgrounds: {} }] };
}

export function changeWorldPlace(draft: WorldMapDraft, id: string, changes: Partial<Pick<StoryWorldPlace, 'name' | 'description' | 'image_id'>>): WorldMapDraft {
  return { ...draft, places: draft.places.map((place) => (place.id === id ? { ...place, ...changes } : place)) };
}

/** 장소의 그 시간대 배경을 붙이거나(id) 뗀다(null) */
export function setBackground(draft: WorldMapDraft, placeId: string, slotId: string, imageId: string | null): WorldMapDraft {
  return {
    ...draft,
    places: draft.places.map((place) => {
      if (place.id !== placeId) return place;
      const backgrounds = { ...place.backgrounds };
      if (imageId === null) delete backgrounds[slotId];
      else backgrounds[slotId] = imageId;
      return { ...place, backgrounds };
    }),
  };
}

export function worldPathsTouching(draft: WorldMapDraft, id: string): number {
  return draft.paths.filter((path) => path.a === id || path.b === id).length;
}

/** 장소를 지운다. 그 장소를 잇는 길도 지운다 */
export function removeWorldPlace(draft: WorldMapDraft, id: string): WorldMapDraft {
  return { places: draft.places.filter((place) => place.id !== id), paths: draft.paths.filter((path) => path.a !== id && path.b !== id) };
}

export function addWorldPath(draft: WorldMapDraft): WorldMapDraft {
  if (draft.paths.length >= WORLD_PATHS_MAX) return draft;
  return { ...draft, paths: [...draft.paths, { a: '', b: '', minutes: '10' }] };
}

export function changeWorldPath(draft: WorldMapDraft, index: number, changes: Partial<PathDraft>): WorldMapDraft {
  return { ...draft, paths: draft.paths.map((path, at) => (at === index ? { ...path, ...changes } : path)) };
}

export function removeWorldPath(draft: WorldMapDraft, index: number): WorldMapDraft {
  return { ...draft, paths: draft.paths.filter((_, at) => at !== index) };
}

function placeHint(place: StoryWorldPlace): Record<string, string> {
  const found: Record<string, string> = {};
  const name = place.name.trim();
  if (name === '') found.name = '이름을 적어 주세요.';
  else if (name.length > PLACE_NAME_MAX) found.name = `이름은 ${PLACE_NAME_MAX}자까지입니다.`;
  if ((place.description ?? '').trim().length > PLACE_DESCRIPTION_MAX) found.description = `설명은 ${PLACE_DESCRIPTION_MAX}자까지입니다.`;
  return found;
}

function pathHint(path: PathDraft, earlier: PathDraft[]): string | undefined {
  if (path.a === '' || path.b === '') return '두 장소를 골라 주세요.';
  if (path.a === path.b) return '서로 다른 두 장소를 골라 주세요.';
  if (minutesOf(path.minutes) === null) return `시간은 0~${PATH_MAX_MINUTES} 사이의 정수(분)입니다.`;
  const same = (other: PathDraft) => (other.a === path.a && other.b === path.b) || (other.a === path.b && other.b === path.a);
  return earlier.some(same) ? '같은 두 장소를 잇는 길이 이미 있습니다.' : undefined;
}

export type WorldMapHints = { places: Record<string, Record<string, string>>; paths: Record<number, string> };

export function worldMapHints(draft: WorldMapDraft): WorldMapHints {
  const places: Record<string, Record<string, string>> = {};
  for (const place of draft.places) {
    const found = placeHint(place);
    if (Object.keys(found).length > 0) places[place.id] = found;
  }
  const paths: Record<number, string> = {};
  draft.paths.forEach((path, index) => {
    const found = pathHint(path, draft.paths.slice(0, index));
    if (found) paths[index] = found;
  });
  return { places, paths };
}

export function hasWorldMapHints(hints: WorldMapHints): boolean {
  return Object.keys(hints.places).length > 0 || Object.keys(hints.paths).length > 0;
}

/** 지도 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 지운 장소가 시작 장소였으면 시작 장소를 비운다(null) */
export function toWorldMapBody(draft: WorldMapDraft, latest: Pick<StoryWorldDetail, 'slots' | 'start_place'>): StoryWorldUpdate {
  const slots = new Set(latest.slots.map((slot) => slot.id));
  const places = draft.places.map((place) => ({
    ...place,
    name: place.name.trim(),
    description: (place.description ?? '').trim(),
    backgrounds: Object.fromEntries(Object.entries(place.backgrounds).filter(([slot]) => slots.has(slot))),
  }));
  const body: StoryWorldUpdate = { places, paths: draft.paths.map((path) => ({ a: path.a, b: path.b, minutes: minutesOf(path.minutes) ?? 0 })) };
  const startGone = latest.start_place !== null && !places.some((place) => place.id === latest.start_place);
  return startGone ? { ...body, start_place: null } : body;
}
