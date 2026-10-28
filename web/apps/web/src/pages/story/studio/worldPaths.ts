// web/apps/web/src/pages/story/studio/worldPaths.ts
// 세계관 만들기(D7)의 주소. /story/studio/worlds(내 세계관), /new(만들기), /:worldId?tab=(고치기).

import type { WorldTab } from './worldTabs';

export const WORLDS_PATH = '/story/studio/worlds';
export const NEW_WORLD_PATH = `${WORLDS_PATH}/new`;

export function worldPath(worldId: string, tab?: WorldTab): string {
  return tab ? `${WORLDS_PATH}/${worldId}?tab=${tab}` : `${WORLDS_PATH}/${worldId}`;
}
