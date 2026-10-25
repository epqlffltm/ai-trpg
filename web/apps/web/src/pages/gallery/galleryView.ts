// web/apps/web/src/pages/gallery/galleryView.ts
// 갤러리(C7)의 칸을 짓는다. 순수한 함수다.
// 연 기록을 캐릭터마다 묶고(최근에 연 캐릭터가 먼저), 캐릭터의 판에서 해금 대상인 씬마다 칸 하나. 연 칸에는 연 때가 있다.

import type { ChatUnlock, EventSceneDocument } from '../../api/types';

/** 캐릭터 → (씬 → 연 때). 캐릭터의 차례는 가장 최근에 연 것이 먼저다(서버가 최근 것부터 준다) */
export function groupUnlocks(unlocks: ChatUnlock[]): Map<string, Map<string, string>> {
  const groups = new Map<string, Map<string, string>>();
  for (const unlock of unlocks) {
    const scenes = groups.get(unlock.character_id) ?? new Map<string, string>();
    if (!scenes.has(unlock.scene_id)) scenes.set(unlock.scene_id, unlock.unlocked_at);
    groups.set(unlock.character_id, scenes);
  }
  return groups;
}

export type SceneCell = { id: string; title: string; imageId: string; unlockedAt: string | null };

/** 판의 해금 대상 씬마다 칸 하나. 판의 차례대로 */
export function sceneCells(scenes: EventSceneDocument[], unlocked: Map<string, string>): SceneCell[] {
  return scenes
    .filter((scene) => scene.collectible)
    .map((scene) => ({ id: scene.id, title: scene.title, imageId: scene.image_id, unlockedAt: unlocked.get(scene.id) ?? null }));
}

/** "3 / 5 열림" */
export function openedLabel(cells: SceneCell[]): string {
  return `${cells.filter((cell) => cell.unlockedAt !== null).length} / ${cells.length} 열림`;
}
