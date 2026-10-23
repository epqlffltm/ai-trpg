// web/apps/web/src/pages/chat/studio/characters/lorebooksForm.ts
// 캐릭터의 로어북 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/characters/schemas.py 의 lorebooks).
//
//   - 붙이는 것은 내 로어북의 id 이고 3 개까지, 겹치지 않는다. 내 것이 아니면 서버가 422 lorebook_not_owned 로 막는다
//   - 차례가 뜻이 있다. chat 은 로어북의 차례, 그 안의 항목의 차례로 읽는다(chat-server/app/lore/texts.py)
//   - 캐릭터를 게시할 때 로어북마다 마지막 판을 복사한다. 게시하지 않은 로어북이나 지워진 로어북이 있으면 게시가 막힌다
//   - 저장은 붙인 목록을 통째로 보낸다

import type { AssetCharacterDetail, AssetCharacterUpdate, AssetLorebookSummary } from '../../../../api/types';

export const LOREBOOKS_MAX = 3;

/** 붙인 로어북 한 줄. 고르기 목록에서 찾지 못하면 summary 가 null 이다(지워졌거나 최근 100 개 밖) */
export type AttachedLorebook = { id: string; summary: AssetLorebookSummary | null };

export function lorebookIds(character: AssetCharacterDetail): string[] {
  return [...character.lorebooks];
}

export function attachLorebook(ids: string[], id: string): string[] {
  if (id === '' || ids.includes(id) || ids.length >= LOREBOOKS_MAX) return ids;
  return [...ids, id];
}

export function detachLorebook(ids: string[], id: string): string[] {
  return ids.filter((current) => current !== id);
}

/** 한 칸 앞으로. 맨 앞이면 그대로 */
export function moveLorebookUp(ids: string[], index: number): string[] {
  if (index <= 0 || index >= ids.length) return ids;
  const next = [...ids];
  [next[index - 1], next[index]] = [next[index] as string, next[index - 1] as string];
  return next;
}

/** 붙인 것마다 고르기 목록의 한 줄을 찾아 붙인다 */
export function attachedLorebooks(ids: string[], mine: AssetLorebookSummary[]): AttachedLorebook[] {
  const byId = new Map(mine.map((lorebook) => [lorebook.id, lorebook]));
  return ids.map((id) => ({ id, summary: byId.get(id) ?? null }));
}

/** 아직 붙이지 않은 내 로어북. 고르는 칸의 목록이다 */
export function lorebookChoices(ids: string[], mine: AssetLorebookSummary[]): AssetLorebookSummary[] {
  return mine.filter((lorebook) => !ids.includes(lorebook.id));
}

export function toLorebooksBody(ids: string[]): AssetCharacterUpdate {
  return { lorebooks: ids };
}
