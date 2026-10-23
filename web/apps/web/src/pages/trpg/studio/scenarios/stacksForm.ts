// web/apps/web/src/pages/trpg/studio/scenarios/stacksForm.ts
// 소지품의 줄들(시작 소지품, 프리젠의 소지품, 인물과 몬스터가 지닌 물건)의 입력. 줄마다 물건 하나, 개수, 착용. 순수한 함수다.
// 인물과 몬스터가 지닌 줄(CarriedItem)에는 처음 쓰러졌을 때 떨어질 확률(chance, 1~100%)이 더 있다.
//
// 서버의 검사(ItemStack, 게시의 starting_wear_invalid)를 따른다:
//   - 같은 물건은 한 줄에 개수로(1~99)
//   - 착용은 그 물건의 규칙이 정한 칸 중에서, 차지하는 칸의 수만큼. 비우면 착용하지 않고 시작한다
//   - 한 목록 안에서 두 줄이 한 칸에 겹치지 않는다(시작 소지품과 한 프리젠의 것을 합친 겹침은 게시 점검이 본다)

import type { CarriedItem, CarriedItemBody, ItemRule, ItemStack, ItemStackBody } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';

export const STACK_MAX = 99;
export const MAX_STARTING_ITEMS = 20;
export const DROP_CHANCE_MAX = 100;
export const MAX_CARRIED_EQUIPMENT = 5;
export const MAX_CARRIED_INVENTORY = 10;

/** chance 는 지닌 물건의 줄에만 있다(떨어질 확률, %) */
export type StackDraft = { entryId: string; count: string; wear: string[]; chance?: string };

export function stackDrafts(stacks: ItemStack[]): StackDraft[] {
  return stacks.map((stack) => ({ entryId: stack.entry_id, count: String(stack.count), wear: stack.wear }));
}

/** 새 줄. 아직 고르지 않은 첫 물건으로 채운다. 고를 것이 없으면 빈 칸. withChance 면 늘 떨어지는(100%) 줄 */
export function newStack(drafts: StackDraft[], entryIds: string[], withChance = false): StackDraft {
  const unused = entryIds.find((id) => !drafts.some((draft) => draft.entryId === id));
  const draft = { entryId: unused ?? '', count: '1', wear: [] };
  return withChance ? { ...draft, chance: String(DROP_CHANCE_MAX) } : draft;
}

/** 물건을 바꾸면 착용을 비운다(칸이 그 물건의 것이었다) */
export function withEntry(draft: StackDraft, entryId: string): StackDraft {
  return { ...draft, entryId, wear: [] };
}

/** 그 물건의 규칙(없으면 착용하지 않는 장비) */
function ruleOf(itemRules: ItemRule[], entryId: string): ItemRule | undefined {
  return itemRules.find((rule) => rule.entry_id === entryId);
}

/** 그 물건이 착용할 수 있는 칸들. 규칙이 없거나 칸이 없으면 빈 목록 */
export function wearableSlots(itemRules: ItemRule[], entryId: string): string[] {
  return ruleOf(itemRules, entryId)?.slots ?? [];
}

/** 줄마다의 문제. 차례(0 부터) → 글 */
export function stacksHints(drafts: StackDraft[], itemRules: ItemRule[]): Record<number, string> {
  const hints: Record<number, string> = {};
  const usedSlots = new Map<string, number>();
  drafts.forEach((draft, index) => {
    if (draft.entryId === '') {
      hints[index] = '물건을 골라 주세요.';
      return;
    }
    if (drafts.findIndex((other) => other.entryId === draft.entryId) !== index) {
      hints[index] = '같은 물건이 위에 있습니다. 한 줄에 개수로 적어 주세요.';
      return;
    }
    if (wholeNumber(draft.count, 1, STACK_MAX) === null) {
      hints[index] = `개수는 1~${STACK_MAX} 사이의 정수입니다.`;
      return;
    }
    const rule = ruleOf(itemRules, draft.entryId);
    if (draft.wear.length > 0 && draft.wear.length !== (rule?.slot_count ?? 1)) {
      hints[index] = `이 물건은 ${rule?.slot_count ?? 1}칸을 차지합니다. 착용할 칸을 그만큼 골라 주세요.`;
      return;
    }
    const clash = draft.wear.find((slot) => usedSlots.has(slot));
    if (clash) hints[index] = '다른 줄이 착용한 칸과 겹칩니다.';
    for (const slot of draft.wear) usedSlots.set(slot, index);
  });
  return hints;
}

/** 보낼 줄들. 힌트가 없을 때만 부른다 */
export function toStacks(drafts: StackDraft[]): ItemStackBody[] {
  return drafts.map((draft) => ({ entry_id: draft.entryId, count: Number(draft.count.trim()), wear: draft.wear }));
}

/** 줄 하나를 바꾸거나 지운다 */
export function changeStack(drafts: StackDraft[], index: number, draft: StackDraft): StackDraft[] {
  return drafts.map((one, at) => (at === index ? draft : one));
}

export function removeStack(drafts: StackDraft[], index: number): StackDraft[] {
  return drafts.filter((_, at) => at !== index);
}

/** 인물·몬스터가 지닌 줄들의 입력 */
export function carriedDrafts(lines: CarriedItem[]): StackDraft[] {
  return lines.map((line) => ({ entryId: line.entry_id, count: String(line.count), wear: line.wear, chance: String(line.chance) }));
}

/**
 * 지닌 줄들의 문제. 소지품과 같은 검사에 더해 떨어질 확률(1~100)과,
 * 다른 목록(장비라면 소지품, 소지품이라면 장비)에 같은 물건이 있는지를 본다(서버의 reject_items_in_both)
 */
export function carriedHints(drafts: StackDraft[], itemRules: ItemRule[], other: StackDraft[]): Record<number, string> {
  const hints = stacksHints(drafts, itemRules);
  drafts.forEach((draft, index) => {
    if (hints[index]) return;
    if (wholeNumber(draft.chance ?? '', 1, DROP_CHANCE_MAX) === null) hints[index] = `떨어질 확률은 1~${DROP_CHANCE_MAX} 사이의 정수입니다.`;
    else if (other.some((line) => line.entryId === draft.entryId)) hints[index] = '장비와 소지품에 같은 물건이 있습니다. 한쪽에만 적어 주세요.';
  });
  return hints;
}

/** 보낼 지닌 줄들. 힌트가 없을 때만 부른다 */
export function toCarried(drafts: StackDraft[]): CarriedItemBody[] {
  return drafts.map((draft) => ({
    entry_id: draft.entryId,
    count: Number(draft.count.trim()),
    chance: Number((draft.chance ?? String(DROP_CHANCE_MAX)).trim()),
    wear: draft.wear,
  }));
}
