// web/apps/web/src/pages/chat/studio/characters/characterPaths.ts
// 캐릭터 만들기(C6)의 주소. /chat/studio/characters(내 캐릭터), /new(만들기), /:characterId?tab=(고치기).

import type { CharacterTab } from './characterTabs';

export const CHARACTERS_PATH = '/chat/studio/characters';
export const NEW_CHARACTER_PATH = `${CHARACTERS_PATH}/new`;

export function characterPath(characterId: string, tab?: CharacterTab): string {
  return tab ? `${CHARACTERS_PATH}/${characterId}?tab=${tab}` : `${CHARACTERS_PATH}/${characterId}`;
}
