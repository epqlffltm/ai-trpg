// web/apps/web/src/pages/chat/studio/characters/mapForm.ts
// 캐릭터의 지도 탭(장소, 길, 처음 있는 장소)의 입력. 순수한 함수다. 상한은 서버와 같다(asset-server/app/characters/models.py).
//
//   - 장소의 id 는 화면이 붙인다(keys.ts). 그림 칸(image_id, backgrounds)은 그림 단계의 것이라 그대로 들고 있다가 보낸다
//   - 장소를 지우면 그 장소를 잇는 길을 지우고, 처음 있는 장소였으면 비운다
//   - 길은 서로 다른 두 장소를 잇고, 같은 두 장소 사이에는 하나다(차례는 가리지 않는다). 시간은 0~1440 분
//   - 장소가 있는데 처음 있는 장소가 없어도 저장은 된다. 게시 점검이 막는다(start_place_missing)

import type { AssetCharacterDetail, AssetCharacterUpdate, AssetPath, AssetPlace } from '../../../../api/types';

export const PLACES_MAX = 30;
export const PLACE_NAME_MAX = 30;
export const PLACE_DESCRIPTION_MAX = 1000;
export const PATHS_MAX = 100;
export const PATH_MAX_MINUTES = 1440;

/** 길의 시간은 글로 들고 있다가 보낼 때 바꾼다. 장소를 고르지 않았으면 빈 글이다 */
export type PathDraft = { a: string; b: string; minutes: string };

export type MapDraft = { places: AssetPlace[]; paths: PathDraft[]; startPlace: string };

export function mapDraft(character: AssetCharacterDetail): MapDraft {
  return {
    places: character.places,
    paths: character.paths.map((path) => ({ a: path.a, b: path.b, minutes: String(path.minutes) })),
    startPlace: character.start_place ?? '',
  };
}

export function addPlace(draft: MapDraft, id: string): MapDraft {
  if (draft.places.length >= PLACES_MAX) return draft;
  return { ...draft, places: [...draft.places, { id, name: '', description: '', image_id: null, backgrounds: {} }] };
}

export function changePlace(draft: MapDraft, id: string, changes: Partial<Pick<AssetPlace, 'name' | 'description'>>): MapDraft {
  return { ...draft, places: draft.places.map((place) => (place.id === id ? { ...place, ...changes } : place)) };
}

/** 그 장소를 잇는 길의 수. 지우기 전에 알린다 */
export function pathsTouching(draft: MapDraft, id: string): number {
  return draft.paths.filter((path) => path.a === id || path.b === id).length;
}

/** 장소를 지운다. 그 장소를 잇는 길도 지우고, 처음 있는 장소였으면 비운다 */
export function removePlace(draft: MapDraft, id: string): MapDraft {
  return {
    places: draft.places.filter((place) => place.id !== id),
    paths: draft.paths.filter((path) => path.a !== id && path.b !== id),
    startPlace: draft.startPlace === id ? '' : draft.startPlace,
  };
}

export function addPath(draft: MapDraft): MapDraft {
  if (draft.paths.length >= PATHS_MAX) return draft;
  return { ...draft, paths: [...draft.paths, { a: '', b: '', minutes: '10' }] };
}

export function changePath(draft: MapDraft, index: number, changes: Partial<PathDraft>): MapDraft {
  return { ...draft, paths: draft.paths.map((path, at) => (at === index ? { ...path, ...changes } : path)) };
}

export function removePath(draft: MapDraft, index: number): MapDraft {
  return { ...draft, paths: draft.paths.filter((_, at) => at !== index) };
}

/** 0~1440 의 정수면 그 수, 아니면 null */
export function minutesOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,4}$/.test(trimmed)) return null;
  const minutes = Number(trimmed);
  return minutes <= PATH_MAX_MINUTES ? minutes : null;
}

function placeHint(place: AssetPlace): Record<string, string> {
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
  if (earlier.some(same)) return '같은 두 장소를 잇는 길이 이미 있습니다.';
  return undefined;
}

export type MapHints = { places: Record<string, Record<string, string>>; paths: Record<number, string> };

/** 장소마다(id → 칸 → 글), 길마다(차례 → 글)의 문제 */
export function mapHints(draft: MapDraft): MapHints {
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

export function hasMapHints(hints: MapHints): boolean {
  return Object.keys(hints.places).length > 0 || Object.keys(hints.paths).length > 0;
}

/** 지도 탭의 칸만 보낸다. 힌트가 없을 때만 부른다. 처음 있는 장소를 고르지 않았으면 null */
export function toMapBody(draft: MapDraft): AssetCharacterUpdate {
  const paths: AssetPath[] = draft.paths.map((path) => ({ a: path.a, b: path.b, minutes: minutesOf(path.minutes) ?? 0 }));
  return {
    places: draft.places.map((place) => ({ ...place, name: place.name.trim(), description: (place.description ?? '').trim() })),
    paths,
    start_place: draft.startPlace === '' ? null : draft.startPlace,
  };
}
