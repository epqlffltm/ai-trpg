// web/apps/web/src/pages/story/studio/worldItemsForm.ts
// 세계관의 물건 탭(물건과 그림)의 입력. 순수한 함수다. 상한은 서버와 같다(asset-server/app/worlds/models.py, 이름과 설명은 캐릭터와 같다).
//
//   - 물건의 id 는 화면이 붙인다(keys.ts). 쓰면 하나 없어지는가(consumable). 건네는 것과 호감도는 인물의 선물 규칙이 정한다
//   - 물건을 지우면 그 물건의 시작 소지품도 지워 함께 보낸다(가장 최근에 받은 세계관의 소지품에서)
//   - 시작 소지품은 진행 탭에서 고른다

import type { StoryWorldDetail, StoryWorldItem, StoryWorldUpdate } from '../../../api/storyWorlds';
import { ITEM_DESCRIPTION_MAX, ITEM_NAME_MAX } from '../../chat/studio/characters/itemsForm';

export { ITEM_DESCRIPTION_MAX, ITEM_NAME_MAX };
export const WORLD_ITEMS_MAX = 100;

export function addWorldItem(items: StoryWorldItem[], id: string): StoryWorldItem[] {
  if (items.length >= WORLD_ITEMS_MAX) return items;
  return [...items, { id, name: '', description: '', consumable: false, image_id: null }];
}

export function changeWorldItem(items: StoryWorldItem[], id: string, changes: Partial<Omit<StoryWorldItem, 'id'>>): StoryWorldItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...changes } : item));
}

export function removeWorldItem(items: StoryWorldItem[], id: string): StoryWorldItem[] {
  return items.filter((item) => item.id !== id);
}

/** 물건마다(id → 칸 → 글)의 문제 */
export function worldItemsHints(items: StoryWorldItem[]): Record<string, Record<string, string>> {
  const hints: Record<string, Record<string, string>> = {};
  for (const item of items) {
    const found: Record<string, string> = {};
    const name = item.name.trim();
    if (name === '') found.name = '이름을 적어 주세요.';
    else if (name.length > ITEM_NAME_MAX) found.name = `이름은 ${ITEM_NAME_MAX}자까지입니다.`;
    if (item.description.trim().length > ITEM_DESCRIPTION_MAX) found.description = `설명은 ${ITEM_DESCRIPTION_MAX}자까지입니다.`;
    if (Object.keys(found).length > 0) hints[item.id] = found;
  }
  return hints;
}

/** 물건 탭의 칸만 보낸다. 지운 물건의 시작 소지품이 있었으면 소지품도 함께 보낸다 */
export function toWorldItemsBody(items: StoryWorldItem[], latest: Pick<StoryWorldDetail, 'start_items'>): StoryWorldUpdate {
  const kept = new Set(items.map((item) => item.id));
  const body: StoryWorldUpdate = { items: items.map((item) => ({ ...item, name: item.name.trim(), description: item.description.trim() })) };
  const starts = latest.start_items.filter((start) => kept.has(start.item));
  return starts.length === latest.start_items.length ? body : { ...body, start_items: starts };
}
