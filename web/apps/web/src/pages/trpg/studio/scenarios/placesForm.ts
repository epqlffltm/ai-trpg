// web/apps/web/src/pages/trpg/studio/scenarios/placesForm.ts
// 지도 탭의 장소(B9). 장소는 붙인 로어북의 장소 항목이고, 맵의 장소는 시작 장소, 길의 끝, 명소다. 순수한 함수다.
// 장소 하나의 창에서 명소인지, 커버(1~10), 그 장소에 처음 있는 인물들, 놓인 물건을 고친다.
// 저장하면 명소, 커버, 인물의 자리, 놓인 물건을 함께 보낸다.
// 놓인 물건: 물건, 개수(1~99), 보이는가(보임, 숨김). 숨긴 물건만 찾는 판정이 있다. 같은 물건은 같은 보이기로 한 줄이다.
// 인물 하나는 한 곳에만 있다. 다른 장소에 있던 인물을 고르면 이 장소로 옮긴다(서버의 reject_duplicate_npc_places).

import type { PlaceItemVisibility, ScenarioDetail, ScenarioUpdate } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { COMBAT_NUMBER_MAX } from './itemRuleForm';
import { STACK_MAX } from './stacksForm';
import type { EntryChoice } from './useLoreEntries';

/** 맵의 장소들(시작 장소, 길의 끝, 명소) */
export function mapPlaces(scenario: Pick<ScenarioDetail, 'start_place' | 'routes' | 'landmarks'>): Set<string> {
  const places = new Set<string>(scenario.landmarks);
  if (scenario.start_place) places.add(scenario.start_place);
  for (const route of scenario.routes) {
    places.add(route.from_place);
    places.add(route.to_place);
  }
  return places;
}

/** 장소 목록의 한 줄. "시작 · 길 3 · 명소 · 커버 5 · 인물 2", 맵에 없으면 "맵 밖" */
export function placeLine(scenario: ScenarioDetail, placeId: string): string {
  const parts: string[] = [];
  if (scenario.start_place === placeId) parts.push('시작');
  const routes = scenario.routes.filter((route) => route.from_place === placeId || route.to_place === placeId).length;
  if (routes > 0) parts.push(`길 ${routes}`);
  if (scenario.landmarks.includes(placeId)) parts.push('명소');
  if (!mapPlaces(scenario).has(placeId)) parts.push('맵 밖');
  const cover = scenario.covers.find((rule) => rule.place_id === placeId);
  if (cover) parts.push(`커버 ${cover.cover}`);
  const people = scenario.npc_places.filter((place) => place.place_id === placeId).length;
  if (people > 0) parts.push(`인물 ${people}`);
  const items = scenario.place_items.filter((item) => item.place_id === placeId);
  if (items.length > 0) {
    const hidden = items.filter((item) => item.visibility === 'hidden').length;
    parts.push(hidden > 0 ? `물건 ${items.length}(숨김 ${hidden})` : `물건 ${items.length}`);
  }
  return parts.join(' · ');
}

export const MAX_PLACE_ITEMS = 100;

export type PlaceItemDraft = { entryId: string; count: string; visibility: PlaceItemVisibility; findAbility: string; findDifficulty: string };

export type PlaceDraft = { landmark: boolean; cover: string; people: string[]; items: PlaceItemDraft[] };

export function placeDraft(scenario: ScenarioDetail, placeId: string): PlaceDraft {
  const cover = scenario.covers.find((rule) => rule.place_id === placeId);
  return {
    landmark: scenario.landmarks.includes(placeId),
    cover: cover ? String(cover.cover) : '',
    people: scenario.npc_places.filter((place) => place.place_id === placeId).map((place) => place.entry_id),
    items: scenario.place_items
      .filter((item) => item.place_id === placeId)
      .map((item) => ({
        entryId: item.entry_id,
        count: String(item.count),
        visibility: item.visibility,
        findAbility: item.find?.ability ?? '',
        findDifficulty: item.find?.difficulty ?? '',
      })),
  };
}

/** 새 놓인 물건. 아직 이 장소에 없는 첫 물건, 보이는 것 */
export function newPlaceItem(items: PlaceItemDraft[], entryIds: string[]): PlaceItemDraft {
  const unused = entryIds.find((id) => !items.some((item) => item.entryId === id));
  return { entryId: unused ?? '', count: '1', visibility: 'open', findAbility: '', findDifficulty: '' };
}

/** 칸 이름 → 글. 커버는 cover, 놓인 물건은 item.<차례> */
export function placeHints(draft: PlaceDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.cover.trim() !== '' && wholeNumber(draft.cover, 1, COMBAT_NUMBER_MAX) === null) hints.cover = `1~${COMBAT_NUMBER_MAX} 사이의 정수입니다. 비우면 숨을 곳이 없습니다.`;
  draft.items.forEach((item, index) => {
    const key = `item.${index}`;
    if (item.entryId === '') hints[key] = '물건을 골라 주세요.';
    else if (wholeNumber(item.count, 1, STACK_MAX) === null) hints[key] = `개수는 1~${STACK_MAX} 사이의 정수입니다.`;
    else if (draft.items.findIndex((other) => other.entryId === item.entryId && other.visibility === item.visibility) !== index) hints[key] = '같은 물건이 같은 보이기로 위에 있습니다. 한 줄에 개수로 적어 주세요.';
    else if (item.visibility === 'hidden' && item.findAbility === '') hints[key] = '숨긴 물건은 찾는 판정의 능력치를 골라 주세요.';
  });
  return hints;
}

/** 인물 하나를 넣거나 뺀다 */
export function togglePerson(people: string[], personId: string): string[] {
  return people.includes(personId) ? people.filter((one) => one !== personId) : [...people, personId];
}

/**
 * 이 장소를 고친 명소, 커버, 인물의 자리, 놓인 물건. 다른 장소의 것은 그대로 두고, 고른 인물이 다른 장소에 있었으면 이 장소로 옮긴다.
 * 힌트가 없을 때만 부른다
 */
export function applyPlace(scenario: ScenarioDetail, placeId: string, draft: PlaceDraft): ScenarioUpdate {
  const landmarks = scenario.landmarks.filter((one) => one !== placeId);
  const covers = scenario.covers.filter((rule) => rule.place_id !== placeId);
  const npcPlaces = scenario.npc_places.filter((place) => place.place_id !== placeId && !draft.people.includes(place.entry_id));
  const placeItems = scenario.place_items.filter((item) => item.place_id !== placeId);
  return {
    landmarks: draft.landmark ? [...landmarks, placeId] : landmarks,
    covers: draft.cover.trim() === '' ? covers : [...covers, { place_id: placeId, cover: Number(draft.cover.trim()) }],
    npc_places: [...npcPlaces, ...draft.people.map((entryId) => ({ entry_id: entryId, place_id: placeId }))],
    place_items: [
      ...placeItems,
      ...draft.items.map((item) => ({
        place_id: placeId,
        entry_id: item.entryId,
        count: Number(item.count.trim()),
        visibility: item.visibility,
        find: item.visibility === 'hidden' ? { ability: item.findAbility, difficulty: item.findDifficulty || null } : null,
      })),
    ],
  };
}

/** 인물이 지금 있는 장소(이 장소 말고). 없으면 null */
export function personElsewhere(scenario: ScenarioDetail, personId: string, placeId: string): string | null {
  const place = scenario.npc_places.find((one) => one.entry_id === personId);
  return place && place.place_id !== placeId ? place.place_id : null;
}

/** 장소의 이름을 찾는 함수. 붙인 로어북에 없으면 그렇다고 적는다 */
export function placeNameOf(places: EntryChoice[]): (placeId: string) => string {
  return (placeId) => places.find((place) => place.id === placeId)?.name ?? '(붙인 로어북에 없는 장소)';
}
