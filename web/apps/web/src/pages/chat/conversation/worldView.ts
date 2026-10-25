// web/apps/web/src/pages/chat/conversation/worldView.ts
// 창(소지품, 상대의 차림, 지도)에 보이는 것. 순수한 함수다. 상태(소지품, 차림, 있는 곳, 가 본 곳)는 서버가 가지의 끝에서 준다.
// 이름과 설명, 길과 걸리는 시간은 대화가 가져온 판(character.document)의 것이다. 판에 없는 id 는 받은 그대로 보인다.
// 갈 수 있는 곳은 지금 있는 곳과 길로 바로 이어진 곳이다(길은 양쪽으로). 서버도 같은 규칙으로 막는다(not_connected).

import type { ConversationDetail } from '../../../api/types';

type CharacterDocument = ConversationDetail['character']['document'];
type State = ConversationDetail['state'];

export type InventoryRow = { id: string; name: string; description: string; count: number; consumable: boolean; clothing: boolean };
export type Destination = { id: string; name: string; minutes: number; visited: boolean };

/** 소지품의 줄. 서버가 준 차례대로 */
export function inventoryRows(inventory: State['inventory'], document: Pick<CharacterDocument, 'items'>): InventoryRow[] {
  return inventory.map((holding) => {
    const item = (document.items ?? []).find((entry) => entry.id === holding.item);
    return {
      id: holding.item,
      name: item?.name ?? holding.item,
      description: item?.description ?? '',
      count: holding.count,
      consumable: item?.consumable ?? false,
      clothing: item?.kind === 'clothing',
    };
  });
}

/** 상대가 입은 옷의 이름들. 입은 차례대로 */
export function outfitNames(outfit: State['outfit'], document: Pick<CharacterDocument, 'items'>): string[] {
  return outfit.map((id) => (document.items ?? []).find((item) => item.id === id)?.name ?? id);
}

/** 판에 지도가 있는가. 없으면 지도 창과 이동이 없다 */
export function hasMap(document: Pick<CharacterDocument, 'places'>): boolean {
  return (document.places ?? []).length > 0;
}

/** 지금 있는 곳에서 바로 갈 수 있는 곳. 걸리는 시간이 짧은 것부터 */
export function destinations(document: Pick<CharacterDocument, 'places' | 'paths'>, state: Pick<State, 'place' | 'visited'>): Destination[] {
  const here = state.place;
  if (!here) return [];
  return (document.paths ?? [])
    .filter((path) => path.a === here || path.b === here)
    .map((path) => {
      const id = path.a === here ? path.b : path.a;
      const place = (document.places ?? []).find((entry) => entry.id === id);
      return { id, name: place?.name ?? id, minutes: path.minutes, visited: state.visited.includes(id) };
    })
    .sort((a, b) => a.minutes - b.minutes);
}

/** 가 본 곳의 이름들(지금 있는 곳은 뺀다) */
export function visitedNames(document: Pick<CharacterDocument, 'places'>, state: Pick<State, 'place' | 'visited'>): string[] {
  return state.visited.filter((id) => id !== state.place).map((id) => (document.places ?? []).find((place) => place.id === id)?.name ?? id);
}

/** "15분", "1시간 20분" */
export function minutesLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}분`;
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`;
}
