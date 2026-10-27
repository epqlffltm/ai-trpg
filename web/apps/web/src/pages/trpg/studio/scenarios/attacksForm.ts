// web/apps/web/src/pages/trpg/studio/scenarios/attacksForm.ts
// 인물(과 몬스터) 시트의 공격들의 입력. 순수한 함수다. 5 개까지, 이름(30자)이 겹치지 않는다(서버의 reject_duplicate_attacks).
// 능력치, 난이도, 피해의 양은 룰북의 이름표에서 고른다. 무기는 장비 줄의 물건이고 비우면 맨몸의 공격이다.
// 장비에서 그 물건을 빼면 무기가 맞지 않게 된다. 저장 전에 알린다(서버의 reject_unknown_weapons).
// 비용(cost, #805 ③-a)과 효과(effects, #805 ③-b)는 아직 고르는 칸이 없다. 받은 그대로 지녔다가 보낸다(저장할 때 지워지지 않게).
// 효과가 있는 공격은 피해의 양을 비울 수 있다(효과만 있는 공격).

import type { SheetAttack, SheetAttackBody } from '../../../../api/types';

export const MAX_ATTACKS = 5;
export const ATTACK_NAME_MAX = 30;

export type AttackDraft = {
  name: string;
  ability: string;
  difficulty: string;
  harm: string;
  weapon: string;
  cost: SheetAttack['cost'];
  effects: SheetAttack['effects'];
};

export function attackDrafts(attacks: SheetAttack[]): AttackDraft[] {
  return attacks.map((attack) => ({
    name: attack.name,
    ability: attack.ability,
    difficulty: attack.difficulty,
    harm: attack.harm ?? '',
    weapon: attack.weapon ?? '',
    cost: attack.cost ?? null,
    effects: attack.effects ?? [],
  }));
}

/** 새 공격. 룰북의 첫 능력치, 기본 난이도, 첫 양으로 채운다(룰북이 없으면 빈 칸) */
export function newAttack(first: { ability: string; difficulty: string; harm: string }): AttackDraft {
  return { name: '', ...first, weapon: '', cost: null, effects: [] };
}

/** 공격마다의 문제. 차례 → 글. equipment 는 장비 줄의 물건들 */
export function attacksHints(drafts: AttackDraft[], equipment: string[]): Record<number, string> {
  const hints: Record<number, string> = {};
  drafts.forEach((draft, index) => {
    const name = draft.name.trim();
    if (name === '') hints[index] = '공격의 이름을 적어 주세요(물어뜯기, 칼 휘두르기).';
    else if (name.length > ATTACK_NAME_MAX) hints[index] = `이름은 ${ATTACK_NAME_MAX}자까지입니다.`;
    else if (drafts.findIndex((other) => other.name.trim() === name) !== index) hints[index] = '같은 이름의 공격이 위에 있습니다.';
    else if (draft.ability === '' || draft.difficulty === '' || (draft.harm === '' && draft.effects.length === 0))
      hints[index] = '능력치, 난이도, 피해의 양을 골라 주세요.';
    else if (draft.weapon !== '' && !equipment.includes(draft.weapon)) hints[index] = '무기는 장비에 적은 물건이어야 합니다.';
  });
  return hints;
}

export function toAttacks(drafts: AttackDraft[]): SheetAttackBody[] {
  return drafts.map((draft) => ({
    name: draft.name.trim(),
    ability: draft.ability,
    difficulty: draft.difficulty,
    harm: draft.harm || null,
    weapon: draft.weapon || null,
    cost: draft.cost,
    effects: draft.effects,
  }));
}
