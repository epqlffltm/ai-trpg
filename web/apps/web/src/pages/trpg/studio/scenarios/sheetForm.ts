// web/apps/web/src/pages/trpg/studio/scenarios/sheetForm.ts
// 시나리오의 시트(기본 시트, 프리젠의 시트)의 입력. 순수한 함수다.
// 시트는 룰북의 능력치마다 점수 하나와 최대 HP 다. 칸은 룰북의 능력치에서 만든다. 룰북을 바꿔 없어진 능력치는 저장할 때 빠진다.
// 모두 비우면 시트 없음(null)이다. 게시 점검이 시트가 없다고 알린다. 일부만 채우면 보내지 않는다.

import type { Ruleset, ScenarioSheet } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';

export const SHEET_MAX_HP = 999;

export type SheetDraft = { abilities: Record<string, string>; maxHp: string };

/** 룰북의 능력치마다 칸 하나. 시트에 그 능력치의 점수가 있으면 채운다 */
export function sheetDraft(sheet: ScenarioSheet | null | undefined, rules: Ruleset): SheetDraft {
  const abilities: Record<string, string> = {};
  for (const ability of rules.abilities) {
    const score = sheet?.abilities[ability.key];
    abilities[ability.key] = score === undefined ? '' : String(score);
  }
  return { abilities, maxHp: sheet ? String(sheet.max_hp) : '' };
}

/** 모든 칸이 비었는가 */
export function isBlankSheet(draft: SheetDraft): boolean {
  return draft.maxHp.trim() === '' && Object.values(draft.abilities).every((score) => score.trim() === '');
}

/**
 * 보내기 전에 알릴 것. 칸 이름(능력치의 key, max_hp) → 글. 다 비었으면 알릴 것이 없다(시트 없음).
 * 점수는 룰북의 범위(score_min~score_max) 안의 정수다
 */
export function sheetHints(draft: SheetDraft, rules: Ruleset): Record<string, string> {
  if (isBlankSheet(draft)) return {};
  const hints: Record<string, string> = {};
  for (const ability of rules.abilities) {
    const score = draft.abilities[ability.key] ?? '';
    if (wholeNumber(score, rules.score_min, rules.score_max) === null) {
      hints[ability.key] = `${rules.score_min}~${rules.score_max} 사이의 정수입니다.`;
    }
  }
  if (wholeNumber(draft.maxHp, 1, SHEET_MAX_HP) === null) hints.max_hp = `1~${SHEET_MAX_HP} 사이의 정수입니다.`;
  return hints;
}

/** 보낼 시트. 다 비었으면 null. 힌트가 없을 때만 부른다 */
export function toSheet(draft: SheetDraft, rules: Ruleset): ScenarioSheet | null {
  if (isBlankSheet(draft)) return null;
  const abilities: Record<string, number> = {};
  for (const ability of rules.abilities) abilities[ability.key] = Number((draft.abilities[ability.key] ?? '').trim());
  return { abilities, max_hp: Number(draft.maxHp.trim()) };
}

/** 목록의 한 줄. "근력 14 · 민첩 12 · HP 12", 시트가 없으면 null */
export function sheetLine(sheet: ScenarioSheet | null | undefined, rules: Ruleset | null): string | null {
  if (!sheet) return null;
  const names = new Map((rules?.abilities ?? []).map((ability) => [ability.key, ability.name]));
  const scores = Object.entries(sheet.abilities).map(([key, score]) => `${names.get(key) ?? key} ${score}`);
  return [...scores, `HP ${sheet.max_hp}`].join(' · ');
}

/** 폼의 힌트 가운데 "sheet.<칸>" 을 시트의 칸 이름으로(SheetFields 에 넘긴다) */
export function sheetFieldHints(hints: Record<string, string>): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const [key, text] of Object.entries(hints)) if (key.startsWith('sheet.')) fields[key.slice('sheet.'.length)] = text;
  return fields;
}
