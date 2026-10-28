// web/apps/web/src/pages/trpg/studio/scenarios/monsterForm.ts
// 몬스터 시트 하나의 입력과 몬스터 시트 목록을 바꾸는 것(B9 몬스터 탭). 순수한 함수다.
// 몬스터 시트는 붙인 모음의 몬스터 하나에 숫자(시트), 공격, 지닌 장비·소지품(떨어질 확률), 둔한지,
// 부위마다 타고난 방어(1~10, 룰북의 장비 칸), 타고난 불굴 세이브(1~10)를 준다. 시트를 적은 몬스터만 판에 들어간다.
// 부상의 성질 가운데 면역과 약함도 준다(#799). 면역은 타입의 성질표에 더하고, 약함은 거기서 뺀다. 둘에 같은 성질은 없다.
// 지닌 물건과 공격의 검사는 인물 시트와 같다(stacksForm, attacksForm).

import type { ItemRule, MonsterSheet, MonsterSheetBody, Ruleset } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { attackDrafts, attacksHints, toAttacks, type AttackDraft } from './attacksForm';
import { COMBAT_NUMBER_MAX } from './itemRuleForm';
import { isBlankSheet, sheetDraft, sheetHints, sheetLine, toSheet, type SheetDraft } from './sheetForm';
import { carriedDrafts, carriedHints, toCarried, type StackDraft } from './stacksForm';

export const MAX_MONSTER_SHEETS = 100;

/** 부상의 성질(서버의 InjuryNature). 룰북의 부상마다 적혀 있다 */
export type InjuryNature = MonsterSheet['immune'][number];

/** 성질의 이름. 화면에 보이는 차례다 */
export const INJURY_NATURES: Record<InjuryNature, string> = {
  poison: '독',
  stun: '기절',
  sense: '감각',
  body: '몸',
  mind: '정신',
};

export type MonsterDraft = {
  sheet: SheetDraft;
  dull: boolean;
  /** 칸(룰북의 장비 칸) → 방어. 빈 글은 타고난 방어가 없다 */
  natural: Record<string, string>;
  ward: string;
  equipment: StackDraft[];
  inventory: StackDraft[];
  attacks: AttackDraft[];
  immune: InjuryNature[];
  vulnerable: InjuryNature[];
  /** 저항(#886 ③). 고르는 칸이 아직 없어 받은 대로 지녔다가 보낸다 */
  resistances: MonsterSheet['resistances'];
};

export function monsterDraft(monster: MonsterSheet | undefined, rules: Ruleset): MonsterDraft {
  const natural: Record<string, string> = {};
  for (const slot of rules.equipment_slots) {
    const armor = monster?.natural_armor.find((one) => one.slot === slot.key);
    natural[slot.key] = armor ? String(armor.defense) : '';
  }
  return {
    sheet: sheetDraft(monster?.sheet, rules),
    dull: monster?.dull ?? false,
    natural,
    ward: monster?.ward ? String(monster.ward) : '',
    equipment: carriedDrafts(monster?.equipment ?? []),
    inventory: carriedDrafts(monster?.inventory ?? []),
    attacks: attackDrafts(monster?.attacks ?? []),
    immune: monster?.immune ?? [],
    vulnerable: monster?.vulnerable ?? [],
    resistances: monster?.resistances ?? [],
  };
}

/** 성질 하나를 켜거나 끈다. 성질표의 차례를 지킨다 */
export function toggledNature(natures: InjuryNature[], nature: InjuryNature, on: boolean): InjuryNature[] {
  const next = new Set(natures);
  if (on) next.add(nature);
  else next.delete(nature);
  return (Object.keys(INJURY_NATURES) as InjuryNature[]).filter((one) => next.has(one));
}

export type MonsterHints = {
  sheet: Record<string, string>;
  /** 칸 → 글, ward 는 불굴 */
  armor: Record<string, string>;
  equipment: Record<number, string>;
  inventory: Record<number, string>;
  attacks: Record<number, string>;
  /** 면역과 약함에 같은 성질을 적었으면 글이 있다 */
  natures: string | null;
};

function natureHint(draft: MonsterDraft): string | null {
  const both = draft.immune.filter((nature) => draft.vulnerable.includes(nature));
  return both.length > 0 ? `${both.map((nature) => INJURY_NATURES[nature]).join(', ')}은(는) 면역과 약함에 함께 둘 수 없습니다.` : null;
}

function combatHint(text: string): string | null {
  return text.trim() !== '' && wholeNumber(text, 1, COMBAT_NUMBER_MAX) === null ? `1~${COMBAT_NUMBER_MAX} 사이의 정수입니다.` : null;
}

export function monsterHints(draft: MonsterDraft, rules: Ruleset, itemRules: ItemRule[]): MonsterHints {
  const armor: Record<string, string> = {};
  for (const [slot, text] of Object.entries(draft.natural)) {
    const hint = combatHint(text);
    if (hint) armor[slot] = hint;
  }
  const ward = combatHint(draft.ward);
  if (ward) armor.ward = ward;
  return {
    sheet: isBlankSheet(draft.sheet) ? { sheet: '몬스터 시트에는 숫자가 있어야 합니다. 이 몬스터를 쓰지 않으려면 시트를 지우세요.' } : sheetHints(draft.sheet, rules),
    armor,
    equipment: carriedHints(draft.equipment, itemRules, draft.inventory),
    inventory: carriedHints(
      draft.inventory.map((line) => ({ ...line, wear: [] })),
      itemRules,
      draft.equipment,
    ),
    attacks: attacksHints(
      draft.attacks,
      draft.equipment.map((line) => line.entryId),
    ),
    natures: natureHint(draft),
  };
}

export function hasMonsterHints(hints: MonsterHints): boolean {
  return hints.natures !== null || [hints.sheet, hints.armor, hints.equipment, hints.inventory, hints.attacks].some((part) => Object.keys(part).length > 0);
}

/** 보낼 몬스터 시트. 힌트가 없을 때만 부른다. 빈 방어 칸은 보내지 않는다 */
export function toMonsterSheet(monsterId: string, draft: MonsterDraft, rules: Ruleset): MonsterSheetBody {
  const sheet = toSheet(draft.sheet, rules);
  if (!sheet) throw new Error('빈 시트는 보내지 않는다(monsterHints 가 막는다)');
  return {
    monster_id: monsterId,
    sheet,
    dull: draft.dull,
    natural_armor: Object.entries(draft.natural)
      .filter(([, text]) => text.trim() !== '')
      .map(([slot, text]) => ({ slot, defense: Number(text.trim()) })),
    ward: draft.ward.trim() === '' ? null : Number(draft.ward.trim()),
    equipment: toCarried(draft.equipment),
    inventory: toCarried(draft.inventory.map((line) => ({ ...line, wear: [] }))),
    attacks: toAttacks(draft.attacks),
    immune: draft.immune,
    vulnerable: draft.vulnerable,
    resistances: draft.resistances,
  };
}

export function withMonsterSheet(sheets: MonsterSheet[], monster: MonsterSheetBody): MonsterSheetBody[] {
  return sheets.some((one) => one.monster_id === monster.monster_id)
    ? sheets.map((one) => (one.monster_id === monster.monster_id ? monster : one))
    : [...sheets, monster];
}

export function withoutMonsterSheet(sheets: MonsterSheet[], monsterId: string): MonsterSheetBody[] {
  return sheets.filter((one) => one.monster_id !== monsterId);
}

/** 목록의 한 줄. "근력 14 · … · HP 9 · 공격 2 · 장비 1 · 타고난 방어 2 · 불굴 3 · 면역 독, 기절 · 약함 정신" */
export function monsterLine(monster: MonsterSheet, rules: Ruleset | null): string {
  const parts = [sheetLine(monster.sheet, rules)];
  if (monster.dull) parts.push('둔함');
  if (monster.attacks.length > 0) parts.push(`공격 ${monster.attacks.length}`);
  if (monster.equipment.length > 0) parts.push(`장비 ${monster.equipment.length}`);
  if (monster.inventory.length > 0) parts.push(`소지품 ${monster.inventory.length}`);
  if (monster.natural_armor.length > 0) parts.push(`타고난 방어 ${monster.natural_armor.length}`);
  if (monster.ward) parts.push(`불굴 ${monster.ward}`);
  if (monster.immune.length > 0) parts.push(`면역 ${monster.immune.map((nature) => INJURY_NATURES[nature]).join(', ')}`);
  if (monster.vulnerable.length > 0) parts.push(`약함 ${monster.vulnerable.map((nature) => INJURY_NATURES[nature]).join(', ')}`);
  return parts.filter(Boolean).join(' · ');
}
