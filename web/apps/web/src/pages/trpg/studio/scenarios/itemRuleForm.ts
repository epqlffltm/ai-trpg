// web/apps/web/src/pages/trpg/studio/scenarios/itemRuleForm.ts
// 물건 규칙 하나의 입력과 물건 규칙 목록을 바꾸는 것. 순수한 함수다(서버의 ItemRule 검사를 따른다).
//
// - 규칙이 없는 물건은 장비(gear)이고 보통(normal)이다. 규칙을 지우면 그렇게 돌아간다
// - 회복의 양(heals)은 소모품만, 룰북의 등급(magnitudes)에서 고른다
// - 칸(slots)은 장비만. 차지하는 칸의 수는 칸의 수보다 많지 않다. 공격·방어(attack, defense, guard, ap, ward)는 칸이 있는 물건만
// - 관통력(ap)은 공격 보정(attack)이 있는 무기만. 수치는 1~10, 값은 1~1,000,000(비우면 사고팔 수 없다)
// - 자물쇠(lock, #281)는 장비만. 입력과 검사는 itemLockForm.ts. 소모품으로 바꾸면 보내지 않는다

import type { ItemKind, ItemRarity, ItemRule, ItemRuleBody, Ruleset } from '../../../../api/types';
import { itemKindLabel, rarityLabel } from '../../labels';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { itemLockDraft, toItemLock, type ItemLockDraft } from './itemLockForm';

export const COMBAT_NUMBER_MAX = 10;
export const MONEY_MAX = 1_000_000;
export const MAX_ITEM_RULES = 100;

/** 공격과 방어의 수치 칸. 차례가 곧 화면의 차례다 */
export const COMBAT_FIELDS = ['attack', 'ap', 'defense', 'guard', 'ward'] as const;
export type CombatField = (typeof COMBAT_FIELDS)[number];

export const COMBAT_LABELS: Record<CombatField, string> = {
  attack: '공격 보정',
  ap: '관통력',
  defense: '방어(차지한 부위)',
  guard: '모든 부위의 방어',
  ward: '불굴 세이브',
};

export type ItemRuleDraft = {
  kind: ItemKind;
  rarity: ItemRarity;
  heals: string;
  price: string;
  slots: string[];
  slotCount: string;
  combat: Record<CombatField, string>;
  lock: ItemLockDraft;
};

function numberText(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

export function itemRuleDraft(rule: ItemRule | undefined): ItemRuleDraft {
  return {
    kind: rule?.kind ?? 'gear',
    rarity: rule?.rarity ?? 'normal',
    heals: rule?.heals ?? '',
    price: numberText(rule?.price),
    slots: rule?.slots ?? [],
    slotCount: String(rule?.slot_count ?? 1),
    combat: {
      attack: numberText(rule?.attack),
      ap: numberText(rule?.ap),
      defense: numberText(rule?.defense),
      guard: numberText(rule?.guard),
      ward: numberText(rule?.ward),
    },
    lock: itemLockDraft(rule?.lock),
  };
}

/** 칸 하나를 넣거나 뺀다. 룰북의 칸 차례를 지킨다 */
export function toggleSlot(slots: string[], slot: string, order: string[]): string[] {
  const next = slots.includes(slot) ? slots.filter((one) => one !== slot) : [...slots, slot];
  return order.filter((one) => next.includes(one));
}

/** 이 물건이 착용하는 물건인가(장비이고 칸이 있다). 아니면 공격·방어의 칸을 보이지 않고 보내지 않는다 */
export function isWorn(draft: ItemRuleDraft): boolean {
  return draft.kind === 'gear' && draft.slots.length > 0;
}

/** 보내기 전에 알릴 것. 칸 이름 → 글 */
export function itemRuleHints(draft: ItemRuleDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.price.trim() !== '' && wholeNumber(draft.price, 1, MONEY_MAX) === null) hints.price = `1~${MONEY_MAX.toLocaleString('ko-KR')} 사이의 정수입니다. 비우면 사고팔 수 없습니다.`;
  if (isWorn(draft)) {
    if (wholeNumber(draft.slotCount, 1, draft.slots.length) === null) hints.slot_count = `1~${draft.slots.length} 사이의 정수입니다(고른 칸의 수까지).`;
    for (const field of COMBAT_FIELDS) {
      const text = draft.combat[field];
      if (text.trim() !== '' && wholeNumber(text, 1, COMBAT_NUMBER_MAX) === null) hints[field] = `1~${COMBAT_NUMBER_MAX} 사이의 정수입니다.`;
    }
    if (draft.combat.ap.trim() !== '' && draft.combat.attack.trim() === '') hints.ap = '관통력은 공격 보정이 있는 무기에만 적습니다.';
  }
  return hints;
}

function optionalNumber(text: string): number | null {
  return text.trim() === '' ? null : Number(text.trim());
}

/** 보낼 규칙. 종류에 맞지 않는 칸(장비의 회복, 소모품의 칸과 자물쇠, 착용하지 않는 물건의 공격·방어)은 비운다 */
export function toItemRule(entryId: string, draft: ItemRuleDraft): ItemRuleBody {
  const worn = isWorn(draft);
  const combat = (field: CombatField) => (worn ? optionalNumber(draft.combat[field]) : null);
  return {
    entry_id: entryId,
    kind: draft.kind,
    rarity: draft.rarity,
    heals: draft.kind === 'consumable' && draft.heals !== '' ? draft.heals : null,
    price: optionalNumber(draft.price),
    slots: draft.kind === 'gear' ? draft.slots : [],
    slot_count: worn ? Number(draft.slotCount.trim()) : 1,
    attack: combat('attack'),
    ap: combat('ap'),
    defense: combat('defense'),
    guard: combat('guard'),
    ward: combat('ward'),
    lock: draft.kind === 'gear' ? toItemLock(draft.lock) : null,
  };
}

/** 그 물건의 규칙을 넣거나 바꾼다(같은 물건의 규칙은 하나) */
export function withItemRule(rules: ItemRule[], rule: ItemRuleBody): ItemRuleBody[] {
  return rules.some((one) => one.entry_id === rule.entry_id)
    ? rules.map((one) => (one.entry_id === rule.entry_id ? rule : one))
    : [...rules, rule];
}

/** 그 물건의 규칙을 지운다. 그 물건은 장비·보통으로 돌아간다 */
export function withoutItemRule(rules: ItemRule[], entryId: string): ItemRuleBody[] {
  return rules.filter((one) => one.entry_id !== entryId);
}

/** 규칙의 한 줄. "장비 · 희귀 · 값 30 · 주손, 보조손 중 2칸 · 공격 +2 · 관통 1 · 새 자물쇠". 규칙이 없으면 null */
export function itemRuleLine(rule: ItemRule | undefined, rules: Ruleset | null): string | null {
  if (!rule) return null;
  const slotName = (key: string) => rules?.equipment_slots.find((slot) => slot.key === key)?.name ?? key;
  const magnitude = rules?.magnitudes.find((entry) => entry.key === rule.heals)?.name ?? rule.heals;
  const parts = [itemKindLabel(rule.kind), rarityLabel(rule.rarity)];
  if (rule.heals) parts.push(`회복 ${magnitude}`);
  if (rule.price !== null && rule.price !== undefined) parts.push(`값 ${rule.price}`);
  if (rule.slots.length > 0) parts.push(`${rule.slots.map(slotName).join(', ')} 중 ${rule.slot_count}칸`);
  if (rule.attack) parts.push(`공격 +${rule.attack}`);
  if (rule.ap) parts.push(`관통 ${rule.ap}`);
  if (rule.defense) parts.push(`방어 ${rule.defense}`);
  if (rule.guard) parts.push(`모든 부위 방어 ${rule.guard}`);
  if (rule.ward) parts.push(`불굴 ${rule.ward}`);
  if (rule.lock) parts.push(rule.lock.pick ? '새 자물쇠(딸 수 있음)' : '새 자물쇠');
  return parts.join(' · ');
}
