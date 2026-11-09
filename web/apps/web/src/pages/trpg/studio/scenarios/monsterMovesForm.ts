// web/apps/web/src/pages/trpg/studio/scenarios/monsterMovesForm.ts
// 몬스터 시트의 사냥과 배회(#254)의 입력. 순수한 함수다. 몬스터 시트(monsterForm)가 쓴다.
// 사냥(hunts)은 길의 칸 수(1~5)다. 싸우지 않는 라운드에 그 안에 캐릭터가 있으면 한 칸 다가간다.
// 배회(roams)는 라운드마다의 확률(1~100%)과 처음 자리에서 벗어나는 칸 수(1~5)다. 둘 다 적거나 둘 다 비운다.
// 정하는 것은 서버의 엔진이다(trpg-server/app/rounds/monster_roams.py). 비우면 그 몬스터는 자리를 지킨다.

import { wholeNumber } from '../rulebooks/rulebookForm';
import type { MonsterSheet } from '../../../../api/types';

// 서버의 한도(trpg-server/app/assets/scenarios/schemas.py 의 ROAM_MAX_REACH, Roams)
export const ROAM_MAX_REACH = 5;
export const ROAM_MAX_CHANCE = 100;

export type MovesDraft = { hunts: string; chance: string; reach: string };

export type MovesHints = { hunts?: string; chance?: string; reach?: string };

export function movesDraft(monster: MonsterSheet | undefined): MovesDraft {
  return {
    hunts: monster?.hunts == null ? '' : String(monster.hunts),
    chance: monster?.roams ? String(monster.roams.chance) : '',
    reach: monster?.roams ? String(monster.roams.reach) : '',
  };
}

function rangeHint(text: string, max: number): string | undefined {
  return text.trim() !== '' && wholeNumber(text, 1, max) === null ? `1~${max} 사이의 정수입니다.` : undefined;
}

/** 칸마다 잘못 적었으면 글이 있다. 배회는 확률과 칸 수를 함께 적어야 한다 */
export function movesHints(draft: MovesDraft): MovesHints {
  const hints: MovesHints = {};
  const hunts = rangeHint(draft.hunts, ROAM_MAX_REACH);
  const chance = rangeHint(draft.chance, ROAM_MAX_CHANCE);
  const reach = rangeHint(draft.reach, ROAM_MAX_REACH);
  if (hunts) hints.hunts = hunts;
  if (chance) hints.chance = chance;
  if (reach) hints.reach = reach;
  const half = (draft.chance.trim() === '') !== (draft.reach.trim() === '');
  if (half && !hints.chance && !hints.reach) {
    if (draft.chance.trim() === '') hints.chance = '배회하려면 확률도 적어 주세요.';
    else hints.reach = '배회하려면 칸 수도 적어 주세요.';
  }
  return hints;
}

export function hasMovesHints(hints: MovesHints): boolean {
  return Object.keys(hints).length > 0;
}

/** 보낼 사냥. 힌트가 없을 때만 부른다. 비우면 null 이다 */
export function toHunts(draft: MovesDraft): number | null {
  return draft.hunts.trim() === '' ? null : Number(draft.hunts.trim());
}

/** 보낼 배회. 힌트가 없을 때만 부른다. 둘 다 비우면 null 이다 */
export function toRoams(draft: MovesDraft): MonsterSheet['roams'] {
  if (draft.chance.trim() === '' && draft.reach.trim() === '') return null;
  return { chance: Number(draft.chance.trim()), reach: Number(draft.reach.trim()) };
}

/** 목록의 한 줄에 붙일 것. "사냥 2칸", "배회 30% · 1칸" 이다. 없으면 빈 목록 */
export function movesLine(monster: MonsterSheet): string[] {
  const parts: string[] = [];
  if (monster.hunts != null) parts.push(`사냥 ${monster.hunts}칸`);
  if (monster.roams) parts.push(`배회 ${monster.roams.chance}% · ${monster.roams.reach}칸`);
  return parts;
}
