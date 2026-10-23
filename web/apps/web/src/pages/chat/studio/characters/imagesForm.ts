// web/apps/web/src/pages/chat/studio/characters/imagesForm.ts
// 캐릭터의 그림 탭(대표 그림, 장소의 배경, 물건의 그림)의 입력. 순수한 함수다.
//
// 그림 탭은 그림 칸만 고친다. 장소와 물건의 다른 칸(이름, 설명, 길 …)은 지도·물건 탭의 것이다.
// 그래서 보낼 때 장소와 물건의 목록은 가장 최근에 받은 캐릭터(latest)의 것을 쓰고, 그림 칸만 이 탭의 것으로 바꾼다.
// 이 탭을 연 뒤에 지도 탭에서 장소를 더하거나 이름을 고쳐 저장했어도 그것을 되돌리지 않는다.
// 장소의 배경은 기본(image_id) 하나와 시간대마다(backgrounds)다. 그 시간대의 것이 없으면 기본을 쓴다(chat).

import type { AssetCharacterDetail, AssetCharacterUpdate, TimeOfDay } from '../../../../api/types';

export const TIMES_OF_DAY: TimeOfDay[] = ['dawn', 'morning', 'day', 'evening', 'night'];

const TIME_LABELS: Record<TimeOfDay, string> = { dawn: '새벽', morning: '아침', day: '낮', evening: '저녁', night: '밤' };

export function timeLabel(time: TimeOfDay): string {
  return TIME_LABELS[time];
}

export type Backgrounds = Partial<Record<TimeOfDay, string>>;
export type PlaceImages = { image_id: string | null; backgrounds: Backgrounds };

/** 이 탭에서 고친 것만 담는다. 고치지 않은 장소와 물건은 받은 그대로 보낸다 */
export type ImagesDraft = {
  imageId: string | null;
  places: Record<string, PlaceImages>;
  items: Record<string, string | null>;
};

export function imagesDraft(character: AssetCharacterDetail): ImagesDraft {
  return { imageId: character.image_id ?? null, places: {}, items: {} };
}

/** 그 장소의 그림 칸. 이 탭에서 고쳤으면 그것, 아니면 받은 것 */
export function placeImages(draft: ImagesDraft, character: AssetCharacterDetail, placeId: string): PlaceImages {
  const edited = draft.places[placeId];
  if (edited) return edited;
  const place = character.places.find((one) => one.id === placeId);
  return { image_id: place?.image_id ?? null, backgrounds: (place?.backgrounds ?? {}) as Backgrounds };
}

/** 그 물건의 그림. 이 탭에서 고쳤으면 그것, 아니면 받은 것 */
export function itemImage(draft: ImagesDraft, character: AssetCharacterDetail, itemId: string): string | null {
  if (itemId in draft.items) return draft.items[itemId] ?? null;
  return character.items.find((one) => one.id === itemId)?.image_id ?? null;
}

export function setPlaceDefault(draft: ImagesDraft, character: AssetCharacterDetail, placeId: string, imageId: string | null): ImagesDraft {
  const current = placeImages(draft, character, placeId);
  return { ...draft, places: { ...draft.places, [placeId]: { ...current, image_id: imageId } } };
}

/** 시간대의 배경을 붙이거나(id) 뗀다(null) */
export function setPlaceBackground(
  draft: ImagesDraft,
  character: AssetCharacterDetail,
  placeId: string,
  time: TimeOfDay,
  imageId: string | null,
): ImagesDraft {
  const current = placeImages(draft, character, placeId);
  const backgrounds: Backgrounds = { ...current.backgrounds };
  if (imageId === null) delete backgrounds[time];
  else backgrounds[time] = imageId;
  return { ...draft, places: { ...draft.places, [placeId]: { ...current, backgrounds } } };
}

export function setItemImage(draft: ImagesDraft, itemId: string, imageId: string | null): ImagesDraft {
  return { ...draft, items: { ...draft.items, [itemId]: imageId } };
}

/** 그림 탭의 칸을 보낸다. 장소와 물건은 latest 의 목록에 이 탭의 그림 칸만 얹는다 */
export function toImagesBody(draft: ImagesDraft, latest: AssetCharacterDetail): AssetCharacterUpdate {
  return {
    image_id: draft.imageId,
    places: latest.places.map((place) => {
      const edited = draft.places[place.id];
      return edited ? { ...place, image_id: edited.image_id, backgrounds: edited.backgrounds } : place;
    }),
    items: latest.items.map((item) => (item.id in draft.items ? { ...item, image_id: draft.items[item.id] ?? null } : item)),
  };
}
