// web/apps/web/src/pages/trpg/studio/scenarios/defendsForm.ts
// 몬스터와 인물 시트의 방어하는 때(#254)의 입력. 순수한 함수다. 몬스터 시트(monsterForm)와 인물 시트(npcForm)가 함께 쓴다.
// 방어하는 때는 둘 중 하나 이상이다. HP 가 최대 HP 의 몇 % 이하이면(below, 1~99) 늘 방어하고,
// 아니면 라운드마다 몇 %의 확률로(chance, 1~100) 방어한다. 둘 다 비우면 방어하지 않는다(null 을 보낸다).
// 정하는 것은 서버의 엔진이다(trpg-server/app/rounds/foe_guards.py). 방어하는 차례에는 치지 않고, 그를 노린 공격은 불리하다.

import { wholeNumber } from '../rulebooks/rulebookForm';
import type { MonsterSheet } from '../../../../api/types';

/** 서버의 방어하는 때(Defends). 몬스터 시트와 인물 시트에서 같은 모양이다 */
export type Defends = NonNullable<MonsterSheet['defends']>;

// 서버의 한도(trpg-server/app/assets/scenarios/schemas.py 의 Defends)
export const BELOW_MAX = 99;
export const CHANCE_MAX = 100;

export type DefendsDraft = { below: string; chance: string };

export type DefendsHints = { below?: string; chance?: string };

export function defendsDraft(defends: Defends | null | undefined): DefendsDraft {
  return { below: defends?.below == null ? '' : String(defends.below), chance: defends?.chance == null ? '' : String(defends.chance) };
}

function percentHint(text: string, max: number): string | undefined {
  return text.trim() !== '' && wholeNumber(text, 1, max) === null ? `1~${max} 사이의 정수입니다.` : undefined;
}

/** 칸마다 잘못 적었으면 글이 있다. 둘 다 비운 것은 괜찮다(방어하지 않는다) */
export function defendsHints(draft: DefendsDraft): DefendsHints {
  const hints: DefendsHints = {};
  const below = percentHint(draft.below, BELOW_MAX);
  const chance = percentHint(draft.chance, CHANCE_MAX);
  if (below) hints.below = below;
  if (chance) hints.chance = chance;
  return hints;
}

export function hasDefendsHints(hints: DefendsHints): boolean {
  return Object.keys(hints).length > 0;
}

/** 보낼 방어하는 때. 힌트가 없을 때만 부른다. 둘 다 비우면 null 이다 */
export function toDefends(draft: DefendsDraft): Defends | null {
  const below = draft.below.trim();
  const chance = draft.chance.trim();
  if (below === '' && chance === '') return null;
  return { below: below === '' ? null : Number(below), chance: chance === '' ? null : Number(chance) };
}

/** 목록의 한 줄에 붙일 것. "방어 HP 30% 이하, 25%" 다. 없으면 null */
export function defendsLine(defends: Defends | null | undefined): string | null {
  if (!defends) return null;
  const parts: string[] = [];
  if (defends.below != null) parts.push(`HP ${defends.below}% 이하`);
  if (defends.chance != null) parts.push(`${defends.chance}%`);
  return parts.length > 0 ? `방어 ${parts.join(', ')}` : null;
}
