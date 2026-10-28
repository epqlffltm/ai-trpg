// web/apps/web/src/pages/trpg/studio/scenarios/npcForm.ts
// 인물 시트 하나의 입력과 인물 시트 목록을 바꾸는 것(B9 인물 탭). 순수한 함수다.
// 인물 시트는 붙인 로어북의 인물 항목 하나에 숫자(시트), 처음 태도, 둔한지, 훔치다 들켰을 때, 상인인지,
// 지닌 장비(착용, 떨어질 확률)와 소지품(떨어질 확률), 공격을 준다. 시트는 비울 수 없다. 숫자를 주지 않으려면 시트를 지운다(기본 인물 시트).

import type { NpcAttitude, NpcCaught, NpcSheet, NpcSheetBody, ItemRule, Ruleset } from '../../../../api/types';
import { attitudeLabel } from '../../labels';
import { attackDrafts, attacksHints, toAttacks, type AttackDraft } from './attacksForm';
import { isBlankSheet, sheetDraft, sheetHints, sheetLine, toSheet, type SheetDraft } from './sheetForm';
import { carriedDrafts, carriedHints, toCarried, type StackDraft } from './stacksForm';

export const MAX_NPC_SHEETS = 100;

export const CAUGHT_LABELS: Record<NpcCaught, string> = { hostile: '적대만 한다', fight: '싸움도 붙는다' };

export type NpcDraft = {
  sheet: SheetDraft;
  attitude: NpcAttitude;
  dull: boolean;
  onCaught: NpcCaught;
  merchant: boolean;
  equipment: StackDraft[];
  inventory: StackDraft[];
  attacks: AttackDraft[];
  /** 타고난 저항(#886 ②). 고치는 칸이 아직 없어 받은 대로 지녔다가 보낸다 */
  resistances: NpcSheet['resistances'];
  /** 타고난 피해의 성질(#886 ③). 고르는 칸이 아직 없어 받은 대로 지녔다가 보낸다 */
  nature: string | null;
};

export function npcDraft(npc: NpcSheet | undefined, rules: Ruleset): NpcDraft {
  return {
    sheet: sheetDraft(npc?.sheet, rules),
    attitude: npc?.attitude ?? 'neutral',
    dull: npc?.dull ?? false,
    onCaught: npc?.on_caught ?? 'hostile',
    merchant: npc?.merchant ?? false,
    equipment: carriedDrafts(npc?.equipment ?? []),
    inventory: carriedDrafts(npc?.inventory ?? []),
    attacks: attackDrafts(npc?.attacks ?? []),
    resistances: npc?.resistances ?? [],
    nature: npc?.nature ?? null,
  };
}

export type NpcHints = {
  /** 시트의 칸(능력치의 key, max_hp)과 sheet(시트를 비웠다) */
  sheet: Record<string, string>;
  equipment: Record<number, string>;
  inventory: Record<number, string>;
  attacks: Record<number, string>;
};

export function npcHints(draft: NpcDraft, rules: Ruleset, itemRules: ItemRule[]): NpcHints {
  const sheet = isBlankSheet(draft.sheet)
    ? { sheet: '인물 시트에는 숫자가 있어야 합니다. 숫자를 주지 않으려면 시트를 지우세요(기본 인물 시트를 받습니다).' }
    : sheetHints(draft.sheet, rules);
  return {
    sheet,
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
  };
}

export function hasNpcHints(hints: NpcHints): boolean {
  return [hints.sheet, hints.equipment, hints.inventory, hints.attacks].some((part) => Object.keys(part).length > 0);
}

/** 보낼 인물 시트. 힌트가 없을 때만 부른다. 소지품의 줄에는 착용을 적지 않는다 */
export function toNpcSheet(entryId: string, draft: NpcDraft, rules: Ruleset): NpcSheetBody {
  const sheet = toSheet(draft.sheet, rules);
  if (!sheet) throw new Error('빈 시트는 보내지 않는다(npcHints 가 막는다)');
  return {
    entry_id: entryId,
    sheet,
    attitude: draft.attitude,
    dull: draft.dull,
    on_caught: draft.onCaught,
    merchant: draft.merchant,
    equipment: toCarried(draft.equipment),
    inventory: toCarried(draft.inventory.map((line) => ({ ...line, wear: [] }))),
    attacks: toAttacks(draft.attacks),
    resistances: draft.resistances,
    nature: draft.nature,
  };
}

/** 그 인물의 시트를 넣거나 바꾼다(한 인물에 시트 하나) */
export function withNpcSheet(npcSheets: NpcSheet[], npc: NpcSheetBody): NpcSheetBody[] {
  return npcSheets.some((one) => one.entry_id === npc.entry_id)
    ? npcSheets.map((one) => (one.entry_id === npc.entry_id ? npc : one))
    : [...npcSheets, npc];
}

export function withoutNpcSheet(npcSheets: NpcSheet[], entryId: string): NpcSheetBody[] {
  return npcSheets.filter((one) => one.entry_id !== entryId);
}

/** 목록의 한 줄. "근력 12 · HP 10 · 적대 · 상인 · 공격 2 · 장비 1 · 소지품 3" */
export function npcLine(npc: NpcSheet, rules: Ruleset | null): string {
  const parts = [sheetLine(npc.sheet, rules), attitudeLabel(npc.attitude)];
  if (npc.merchant) parts.push('상인');
  if (npc.dull) parts.push('둔함');
  if (npc.attacks.length > 0) parts.push(`공격 ${npc.attacks.length}`);
  if (npc.equipment.length > 0) parts.push(`장비 ${npc.equipment.length}`);
  if (npc.inventory.length > 0) parts.push(`소지품 ${npc.inventory.length}`);
  return parts.filter(Boolean).join(' · ');
}
