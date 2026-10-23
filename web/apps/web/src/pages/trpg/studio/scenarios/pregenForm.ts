// web/apps/web/src/pages/trpg/studio/scenarios/pregenForm.ts
// 프리젠 하나의 입력(이름, 설명, 시트)과 프리젠 목록을 바꾸는 것. 순수한 함수다.
// 프리젠은 창에서 저장하면 목록을 통째로 보낸다(PATCH pregens). 소지품과 더 받는 돈은 물건·돈의 탭이 고치므로 그대로 둔다.
// 이름은 앞뒤 공백을 떼고 1~50자, 대소문자만 달라도 같은 이름이다(서버의 reject_duplicate_names).

import type { PregenBody, Ruleset, ScenarioPregen, ScenarioUpdate } from '../../../../api/types';
import { sheetDraft, sheetHints, toSheet, type SheetDraft } from './sheetForm';

export const MAX_PREGENS = 8;
export const PREGEN_NAME_MAX = 50;
export const PREGEN_DESCRIPTION_MAX = 1000;

export type PregenDraft = { name: string; description: string; sheet: SheetDraft | null };

/** 창의 처음 값. 룰북이 없으면 시트의 칸이 없다(sheet null, 저장할 때 원래 시트를 둔다) */
export function pregenDraft(pregen: ScenarioPregen | null, rules: Ruleset | null): PregenDraft {
  return {
    name: pregen?.name ?? '',
    description: pregen?.description ?? '',
    sheet: rules ? sheetDraft(pregen?.sheet, rules) : null,
  };
}

/** 보내기 전에 알릴 것. others 는 이 프리젠 말고 다른 프리젠의 이름들. 시트의 칸은 sheet.<칸> */
export function pregenHints(draft: PregenDraft, rules: Ruleset | null, others: string[]): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > PREGEN_NAME_MAX) hints.name = `이름은 ${PREGEN_NAME_MAX}자까지입니다.`;
  else if (others.some((other) => other.toLowerCase() === name.toLowerCase())) hints.name = '같은 이름의 프리젠이 있습니다.';
  if (draft.description.length > PREGEN_DESCRIPTION_MAX) hints.description = `설명은 ${PREGEN_DESCRIPTION_MAX}자까지입니다.`;
  if (rules && draft.sheet) {
    for (const [field, text] of Object.entries(sheetHints(draft.sheet, rules))) hints[`sheet.${field}`] = text;
  }
  return hints;
}

/** 보낼 프리젠. 원래 프리젠의 소지품과 돈은 그대로 둔다. 룰북이 없어 시트의 칸이 없으면 원래 시트를 둔다 */
export function toPregen(draft: PregenDraft, rules: Ruleset | null, original: ScenarioPregen | null): PregenBody {
  const sheet = rules && draft.sheet ? toSheet(draft.sheet, rules) : (original?.sheet ?? null);
  return {
    name: draft.name.trim(),
    description: draft.description,
    sheet,
    items: original?.items ?? [],
    money: original?.money ?? 0,
  };
}

/** 프리젠 목록에서 at 번째를 바꾼다. at 이 null 이면 끝에 더한다 */
export function withPregen(pregens: ScenarioPregen[], at: number | null, pregen: PregenBody): PregenBody[] {
  if (at === null) return [...pregens, pregen];
  return pregens.map((one, index) => (index === at ? pregen : one));
}

export function withoutPregen(pregens: ScenarioPregen[], at: number): PregenBody[] {
  return pregens.filter((_, index) => index !== at);
}

export function toPregensBody(pregens: PregenBody[]): ScenarioUpdate {
  return { pregens };
}

/** 다른 프리젠의 이름들(at 번째를 뺀다) */
export function otherNames(pregens: ScenarioPregen[], at: number | null): string[] {
  return pregens.filter((_, index) => index !== at).map((pregen) => pregen.name);
}

/** 목록 한 줄의 덧붙임. 물건·돈의 탭에서 정하는 것이 있으면 "소지품 2줄 · 돈 30" */
export function pregenExtras(pregen: ScenarioPregen): string | null {
  const parts = [];
  if (pregen.items.length > 0) parts.push(`소지품 ${pregen.items.length}줄`);
  if (pregen.money > 0) parts.push(`돈 ${pregen.money}`);
  return parts.length > 0 ? parts.join(' · ') : null;
}
