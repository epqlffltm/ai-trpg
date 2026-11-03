// web/apps/web/src/api/shortcuts.ts
// 내 단축어(#981, asset 서버). 계정의 것이고 어느 작품의 대화에서든 "/이름"으로 부른다. 주인만 보고 고친다.
//   - 목록을 통째로 읽고 통째로 바꾼다(적은 차례가 고르는 목록의 차례다). 없으면 빈 목록이다
//   - 규칙은 components/shortcuts/shortcutsForm.ts 와 같다. 어기면 422(같은 이름, 20개 넘음, 길이 넘음)
// 캐릭터와 세계관의 제작자 단축어는 그 초안의 shortcuts 칸이다(api/characters.ts, api/storyWorlds.ts).

import type { components } from './generated/asset';
import { apiRequest } from './http';

export type ShortcutList = components['schemas']['ShortcutList'];

const SHORTCUTS = '/api/v1/asset/shortcuts';

export function fetchMyShortcuts(signal?: AbortSignal): Promise<ShortcutList> {
  return apiRequest<ShortcutList>(SHORTCUTS, signal ? { signal } : {});
}

export function replaceMyShortcuts(body: ShortcutList): Promise<ShortcutList> {
  return apiRequest<ShortcutList>(SHORTCUTS, { method: 'PUT', body });
}
