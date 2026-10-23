// web/apps/web/src/pages/chat/studio/characters/itemsForm.ts
// 캐릭터의 물건 탭(물건, 시작 소지품)의 입력. 순수한 함수다. 상한은 서버와 같다(asset-server/app/characters/models.py).
//
//   - 물건의 id 는 화면이 붙인다(keys.ts). 그림(image_id)은 그림 단계의 것이라 그대로 들고 있다가 보낸다
//   - 옷(clothing)은 건네면 상대의 차림에 들어간다. 쓰면 없어지는가(consumable), 상대가 줄 수 있는가(giftable)
//   - 물건을 지우면 그 물건의 시작 소지품도 지운다
//   - 시작 소지품은 물건마다 한 줄이고 수는 1~99 다

import type { AssetCharacterDetail, AssetCharacterUpdate, AssetItem } from '../../../../api/types';

export const ITEMS_MAX = 50;
export const ITEM_NAME_MAX = 30;
export const ITEM_DESCRIPTION_MAX = 500;
export const START_ITEMS_MAX = 20;
export const START_ITEM_MAX_COUNT = 99;

/** 수는 글로 들고 있다가 보낼 때 바꾼다. 물건을 고르지 않았으면 빈 글이다 */
export type StartItemDraft = { item: string; count: string };

export type ItemsDraft = { items: AssetItem[]; startItems: StartItemDraft[] };

export function itemsDraft(character: AssetCharacterDetail): ItemsDraft {
  return {
    items: character.items,
    startItems: character.start_items.map((start) => ({ item: start.item, count: String(start.count ?? 1) })),
  };
}

export function addItem(draft: ItemsDraft, id: string): ItemsDraft {
  if (draft.items.length >= ITEMS_MAX) return draft;
  const item: AssetItem = { id, name: '', description: '', kind: 'thing', consumable: false, giftable: false, image_id: null };
  return { ...draft, items: [...draft.items, item] };
}

export type ItemChanges = Partial<Pick<AssetItem, 'name' | 'description' | 'kind' | 'consumable' | 'giftable'>>;

export function changeItem(draft: ItemsDraft, id: string, changes: ItemChanges): ItemsDraft {
  return { ...draft, items: draft.items.map((item) => (item.id === id ? { ...item, ...changes } : item)) };
}

/** 그 물건이 시작 소지품에 있는가. 지우기 전에 알린다 */
export function isStartItem(draft: ItemsDraft, id: string): boolean {
  return draft.startItems.some((start) => start.item === id);
}

/** 물건을 지운다. 그 물건의 시작 소지품도 지운다 */
export function removeItem(draft: ItemsDraft, id: string): ItemsDraft {
  return { items: draft.items.filter((item) => item.id !== id), startItems: draft.startItems.filter((start) => start.item !== id) };
}

export function addStartItem(draft: ItemsDraft): ItemsDraft {
  if (draft.startItems.length >= START_ITEMS_MAX) return draft;
  return { ...draft, startItems: [...draft.startItems, { item: '', count: '1' }] };
}

export function changeStartItem(draft: ItemsDraft, index: number, changes: Partial<StartItemDraft>): ItemsDraft {
  return { ...draft, startItems: draft.startItems.map((start, at) => (at === index ? { ...start, ...changes } : start)) };
}

export function removeStartItem(draft: ItemsDraft, index: number): ItemsDraft {
  return { ...draft, startItems: draft.startItems.filter((_, at) => at !== index) };
}

/** 1~99 의 정수면 그 수, 아니면 null */
export function countOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) return null;
  const count = Number(trimmed);
  return count >= 1 ? count : null;
}

function itemHint(item: AssetItem): Record<string, string> {
  const found: Record<string, string> = {};
  const name = item.name.trim();
  if (name === '') found.name = '이름을 적어 주세요.';
  else if (name.length > ITEM_NAME_MAX) found.name = `이름은 ${ITEM_NAME_MAX}자까지입니다.`;
  if ((item.description ?? '').trim().length > ITEM_DESCRIPTION_MAX) found.description = `설명은 ${ITEM_DESCRIPTION_MAX}자까지입니다.`;
  return found;
}

function startItemHint(start: StartItemDraft, earlier: StartItemDraft[]): string | undefined {
  if (start.item === '') return '물건을 골라 주세요.';
  if (countOf(start.count) === null) return `수는 1~${START_ITEM_MAX_COUNT} 사이의 정수입니다.`;
  if (earlier.some((other) => other.item === start.item)) return '같은 물건이 이미 있습니다. 한 줄에 수로 적어 주세요.';
  return undefined;
}

export type ItemsHints = { items: Record<string, Record<string, string>>; startItems: Record<number, string> };

/** 물건마다(id → 칸 → 글), 시작 소지품마다(차례 → 글)의 문제 */
export function itemsHints(draft: ItemsDraft): ItemsHints {
  const items: Record<string, Record<string, string>> = {};
  for (const item of draft.items) {
    const found = itemHint(item);
    if (Object.keys(found).length > 0) items[item.id] = found;
  }
  const startItems: Record<number, string> = {};
  draft.startItems.forEach((start, index) => {
    const found = startItemHint(start, draft.startItems.slice(0, index));
    if (found) startItems[index] = found;
  });
  return { items, startItems };
}

export function hasItemsHints(hints: ItemsHints): boolean {
  return Object.keys(hints.items).length > 0 || Object.keys(hints.startItems).length > 0;
}

/** 물건 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toItemsBody(draft: ItemsDraft): AssetCharacterUpdate {
  return {
    items: draft.items.map((item) => ({ ...item, name: item.name.trim(), description: (item.description ?? '').trim() })),
    start_items: draft.startItems.map((start) => ({ item: start.item, count: countOf(start.count) ?? 1 })),
  };
}
