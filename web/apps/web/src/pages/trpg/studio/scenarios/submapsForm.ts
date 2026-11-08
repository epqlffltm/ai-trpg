// web/apps/web/src/pages/trpg/studio/scenarios/submapsForm.ts
// 지도 탭의 하위 맵(#284). 장소가 품은 하위 맵(마을 안의 건물, 건물의 층)을 장소마다 "어느 장소 안에 있나"로 고친다. 순수한 함수다.
// 서버의 모양은 {place_id: 품은 장소, places: 그 안의 장소들} 의 목록이다. 장소 하나는 한 하위 맵에만 든다.
// 품은 장소들은 서로를 품지 못하고(고를 거리에서 뺀다) 3 겹까지다(서버의 SUBMAP_MAX_DEPTH). 하위 맵 하나에 장소는 100 개까지다.
// 들고 나는 것은 보통의 길로 적는다. 층이 다른 장소끼리도 길을 잇는다.

import type { ScenarioDetail } from '../../../../api/types';

export const SUBMAP_MAX_DEPTH = 3;
export const SUBMAP_MAX_PLACES = 100;
export const MAX_SUBMAPS = 50;

export type Submaps = ScenarioDetail['submaps'];

/** 하위 맵들. 하위 맵이 생기기 전의 응답에는 칸이 없다 */
export function submapsOf(scenario: Pick<ScenarioDetail, 'submaps'>): Submaps {
  return scenario.submaps ?? [];
}

/** 그 장소를 품은 장소. 바깥 맵의 장소면 빈 값 */
export function containerOf(submaps: Submaps, placeId: string): string {
  return submaps.find((submap) => submap.places.includes(placeId))?.place_id ?? '';
}

/** 그 장소 안의 장소들(겹친 것까지). 그 장소를 품게 하면 서로를 품게 되므로 고를 거리에서 뺀다 */
export function insideOf(submaps: Submaps, placeId: string): Set<string> {
  const found = new Set<string>();
  const queue = [placeId];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const place of submaps.find((submap) => submap.place_id === current)?.places ?? []) {
      if (!found.has(place) && place !== placeId) {
        found.add(place);
        queue.push(place);
      }
    }
  }
  return found;
}

/** 그 장소가 품은 장소의 수 */
export function heldCount(submaps: Submaps, placeId: string): number {
  return submaps.find((submap) => submap.place_id === placeId)?.places.length ?? 0;
}

/**
 * 그 장소를 품은 장소를 바꾼다. 빈 값이면 바깥 맵으로 꺼낸다. 비게 된 하위 맵은 지운다.
 * 품은 장소가 새로 품으면 그 하위 맵을 끝에 더한다
 */
export function withContainer(submaps: Submaps, placeId: string, container: string): Submaps {
  const without = submaps.map((submap) => ({ ...submap, places: submap.places.filter((place) => place !== placeId) })).filter((submap) => submap.places.length > 0);
  if (!container) return without;
  if (without.some((submap) => submap.place_id === container)) {
    return without.map((submap) => (submap.place_id === container ? { ...submap, places: [...submap.places, placeId] } : submap));
  }
  return [...without, { place_id: container, places: [placeId] }];
}

/** 하위 맵들 가운데 가장 깊은 것. 바깥 맵의 장소가 품은 것이 1 이다. 서로를 품으면 Infinity */
export function deepest(submaps: Submaps): number {
  const parents = new Map<string, string>(submaps.flatMap((submap) => submap.places.map((place) => [place, submap.place_id] as const)));
  let deepestDepth = 0;
  for (const submap of submaps) {
    let depth = 1;
    let place = submap.place_id;
    const seen = new Set([place]);
    while (parents.has(place)) {
      place = parents.get(place) as string;
      if (seen.has(place)) return Infinity;
      seen.add(place);
      depth += 1;
    }
    deepestDepth = Math.max(deepestDepth, depth);
  }
  return deepestDepth;
}

/** 품은 장소를 바꾼 하위 맵들이 서버가 받는 모양인가. 아니면 그 까닭 */
export function submapsProblem(submaps: Submaps): string | null {
  if (deepest(submaps) > SUBMAP_MAX_DEPTH) return `하위 맵은 ${SUBMAP_MAX_DEPTH} 겹까지 품습니다(바깥 맵 > 마을 > 건물 > 층).`;
  if (submaps.length > MAX_SUBMAPS) return `하위 맵은 ${MAX_SUBMAPS} 개까지입니다.`;
  if (submaps.some((submap) => submap.places.length > SUBMAP_MAX_PLACES)) return `한 장소 안에는 장소를 ${SUBMAP_MAX_PLACES} 개까지 둡니다.`;
  return null;
}
