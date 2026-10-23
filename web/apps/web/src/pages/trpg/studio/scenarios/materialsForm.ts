// web/apps/web/src/pages/trpg/studio/scenarios/materialsForm.ts
// 시나리오의 재료 탭(룰북, 세계관, 로어북, 몬스터 모음)의 입력. 순수한 함수다.
// 룰북과 세계관은 하나(비우면 null 로 뗀다), 로어북과 몬스터 모음은 10 개까지이고 목록을 통째로 보낸다.

import type { AssetSummary, ScenarioDetail, ScenarioUpdate } from '../../../../api/types';

export const MAX_LOREBOOKS = 10;
export const MAX_BESTIARIES = 10;

export type MaterialsDraft = { rulebookId: string; worldId: string; lorebookIds: string[]; bestiaryIds: string[] };

export function materialsDraft(scenario: ScenarioDetail): MaterialsDraft {
  return {
    rulebookId: scenario.rulebook_id ?? '',
    worldId: scenario.world_id ?? '',
    lorebookIds: scenario.lorebook_ids,
    bestiaryIds: scenario.bestiary_ids,
  };
}

/** 하나를 넣거나 뺀다. 이미 있으면 빼고, 없으면 max 보다 적을 때만 넣는다. 넣은 차례를 지킨다 */
export function toggleId(ids: string[], id: string, max: number): string[] {
  if (ids.includes(id)) return ids.filter((one) => one !== id);
  return ids.length < max ? [...ids, id] : ids;
}

/** 재료 탭의 칸만 보낸다. 비운 룰북과 세계관은 null 로 뗀다 */
export function toMaterialsBody(draft: MaterialsDraft): ScenarioUpdate {
  return {
    rulebook_id: draft.rulebookId || null,
    world_id: draft.worldId || null,
    lorebook_ids: draft.lorebookIds,
    bestiary_ids: draft.bestiaryIds,
  };
}

/**
 * 고를 거리. 내 재료의 목록에 고른 것 중 목록에 없는 것(한 번에 읽는 100 개 밖)을 더한다.
 * 그런 것은 제목을 몰라 "목록에 없는 재료"로 보인다
 */
export function withChosen(choices: AssetSummary[], chosen: string[]): { id: string; title: string | null }[] {
  const listed = choices.map((asset) => ({ id: asset.id, title: asset.title as string | null }));
  const unlisted = chosen.filter((id) => !choices.some((asset) => asset.id === id)).map((id) => ({ id, title: null }));
  return [...listed, ...unlisted];
}
