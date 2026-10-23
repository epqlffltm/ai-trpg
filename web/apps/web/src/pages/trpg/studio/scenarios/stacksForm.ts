// web/apps/web/src/pages/trpg/studio/scenarios/stacksForm.ts
// 소지품의 줄들(시작 소지품, 프리젠의 소지품)의 입력. 줄마다 물건 하나, 개수, 시작할 때의 착용. 순수한 함수다.
//
// 서버의 검사(ItemStack, 게시의 starting_wear_invalid)를 따른다:
//   - 같은 물건은 한 줄에 개수로(1~99)
//   - 착용은 그 물건의 규칙이 정한 칸 중에서, 차지하는 칸의 수만큼. 비우면 착용하지 않고 시작한다
//   - 한 목록 안에서 두 줄이 한 칸에 겹치지 않는다(시작 소지품과 한 프리젠의 것을 합친 겹침은 게시 점검이 본다)

import type { ItemRule, ItemStack, ItemStackBody } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';

export const STACK_MAX = 99;
export const MAX_STARTING_ITEMS = 20;

export type StackDraft = { entryId: string; count: string; wear: string[] };

export function stackDrafts(stacks: ItemStack[]): StackDraft[] {
  return stacks.map((stack) => ({ entryId: stack.entry_id, count: String(stack.count), wear: stack.wear }));
}

/** 새 줄. 아직 고르지 않은 첫 물건으로 채운다. 고를 것이 없으면 빈 칸 */
export function newStack(drafts: StackDraft[], entryIds: string[]): StackDraft {
  const unused = entryIds.find((id) => !drafts.some((draft) => draft.entryId === id));
  return { entryId: unused ?? '', count: '1', wear: [] };
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
