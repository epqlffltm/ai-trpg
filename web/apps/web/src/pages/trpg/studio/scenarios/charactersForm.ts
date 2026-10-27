// web/apps/web/src/pages/trpg/studio/scenarios/charactersForm.ts
// 시나리오의 캐릭터 탭(추천 인원, 캐릭터 방식, 다시 굴리기, 기본 시트, 능력치를 정하는 방식의 최대 HP)의 입력. 순수한 함수다.
// 프리젠은 이 폼이 아니라 창에서 따로 저장한다(pregenForm.ts).
//
// - 기본 시트는 "이름과 설명만 쓰기"(custom)가 받는 숫자다. 룰북이 없으면 칸을 만들 수 없어 보내지 않는다(그대로 둔다)
// - 최대 HP(기준값과 상한)는 능력치를 정하는 방식(manual, point_buy, rolled)이 쓴다. 그 방식이 없으면 보내지 않는다

import type { CharacterMode, PlayerMadeHp, Ruleset, ScenarioDetail, ScenarioUpdate } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { sheetDraft, sheetHints, toSheet, withSkills, type SheetDraft } from './sheetForm';

export const MAX_PLAYERS = 4;
export const PLAYER_MADE_HP_MAX = 999;

/** 방식의 차례. 서버가 저장하는 차례와 같다 */
export const CHARACTER_MODES: CharacterMode[] = ['pregen', 'custom', 'manual', 'point_buy', 'rolled'];

const PLAYER_MADE: CharacterMode[] = ['manual', 'point_buy', 'rolled'];

export type CharactersDraft = {
  minPlayers: number;
  maxPlayers: number;
  modes: CharacterMode[];
  reroll: boolean;
  /** 룰북이 없으면 null(시트의 칸을 만들 수 없다) */
  defaultSheet: SheetDraft | null;
  /** 기본 시트가 아는 기술(#805). 고치는 칸이 아직 없어 받은 대로 지녔다가 보낸다 */
  defaultSkills: string[];
  hpBase: string;
  hpCap: string;
};

export function charactersDraft(scenario: ScenarioDetail, rules: Ruleset | null): CharactersDraft {
  return {
    minPlayers: scenario.recommended_players.min,
    maxPlayers: scenario.recommended_players.max,
    modes: scenario.character_modes,
    reroll: scenario.reroll_allowed,
    defaultSheet: rules ? sheetDraft(scenario.default_sheet, rules) : null,
    defaultSkills: scenario.default_sheet?.skills ?? [],
    hpBase: scenario.player_made_hp ? String(scenario.player_made_hp.base) : '',
    hpCap: scenario.player_made_hp ? String(scenario.player_made_hp.cap) : '',
  };
}

/** 방식 하나를 켜거나 끈다. 차례를 지킨다 */
export function toggleMode(modes: CharacterMode[], mode: CharacterMode): CharacterMode[] {
  const next = modes.includes(mode) ? modes.filter((one) => one !== mode) : [...modes, mode];
  return CHARACTER_MODES.filter((one) => next.includes(one));
}

/** 기본 시트를 쓰는 방식이 있는가(이름과 설명만 쓰기) */
export function usesDefaultSheet(modes: CharacterMode[]): boolean {
  return modes.includes('custom');
}

/** 플레이어가 능력치를 정하는 방식이 있는가 */
export function usesPlayerMadeHp(modes: CharacterMode[]): boolean {
  return modes.some((mode) => PLAYER_MADE.includes(mode));
}

/** 룰북에 없어 쓸 수 없는 방식의 알림. 게시 점검도 같은 것을 알린다 */
export function modeWarnings(modes: CharacterMode[], rules: Ruleset | null): string[] {
  if (!rules) return [];
  const warnings: string[] = [];
  if (modes.includes('point_buy') && !rules.point_buy) warnings.push('이 룰북에는 점수제가 없어 "점수로 능력치 사기"를 쓸 수 없습니다.');
  if (modes.includes('rolled') && !rules.score_roll) warnings.push('이 룰북에는 굴리는 법이 없어 "주사위로 굴린 점수 놓기"를 쓸 수 없습니다.');
  return warnings;
}

function hpBlank(draft: CharactersDraft): boolean {
  return draft.hpBase.trim() === '' && draft.hpCap.trim() === '';
}

/** 보내기 전에 알릴 것. 칸 이름 → 글. 기본 시트의 칸은 sheet.<칸> */
export function charactersHints(draft: CharactersDraft, rules: Ruleset | null): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.modes.length === 0) hints.character_modes = '방식을 하나는 골라 주세요. 없으면 아무도 앉을 수 없습니다.';
  if (draft.minPlayers > draft.maxPlayers) hints.recommended_players = '최소 인원이 최대 인원보다 큽니다.';
  if (rules && draft.defaultSheet && usesDefaultSheet(draft.modes)) {
    for (const [field, text] of Object.entries(sheetHints(draft.defaultSheet, rules))) hints[`sheet.${field}`] = text;
  }
  if (usesPlayerMadeHp(draft.modes) && !hpBlank(draft)) {
    const base = wholeNumber(draft.hpBase, 1, PLAYER_MADE_HP_MAX);
    const cap = wholeNumber(draft.hpCap, 1, PLAYER_MADE_HP_MAX);
    if (base === null) hints.hp_base = `1~${PLAYER_MADE_HP_MAX} 사이의 정수입니다.`;
    if (cap === null) hints.hp_cap = `1~${PLAYER_MADE_HP_MAX} 사이의 정수입니다.`;
    if (base !== null && cap !== null && base > cap) hints.hp_cap = '상한이 기준값보다 작습니다.';
  }
  return hints;
}

function toPlayerMadeHp(draft: CharactersDraft): PlayerMadeHp | null {
  return hpBlank(draft) ? null : { base: Number(draft.hpBase.trim()), cap: Number(draft.hpCap.trim()) };
}

/** 캐릭터 탭의 칸만 보낸다. 쓰지 않는 방식의 값(기본 시트, 최대 HP)과 룰북 없이 만들 수 없는 시트는 보내지 않아 그대로 둔다 */
export function toCharactersBody(draft: CharactersDraft, rules: Ruleset | null): ScenarioUpdate {
  const body: ScenarioUpdate = {
    recommended_players: { min: draft.minPlayers, max: draft.maxPlayers },
    character_modes: draft.modes,
    reroll_allowed: draft.modes.includes('rolled') && draft.reroll,
  };
  if (rules && draft.defaultSheet && usesDefaultSheet(draft.modes)) body.default_sheet = withSkills(toSheet(draft.defaultSheet, rules), draft.defaultSkills);
  if (usesPlayerMadeHp(draft.modes)) body.player_made_hp = toPlayerMadeHp(draft);
  return body;
}

/** 최대 HP 를 어떻게 구하는지 한 줄. 룰북의 HP 능력치와 보정의 방법에서 */
export function hpFormulaText(rules: Ruleset | null): string {
  if (!rules) return '최대 HP = 기준값 + 룰북이 정한 능력치의 보정. 상한을 넘지 않습니다.';
  const ability = rules.abilities.find((one) => one.key === rules.hp_ability);
  if (!ability) return '이 룰북에는 HP 에 더하는 능력치가 없어 기준값이 그대로 최대 HP 입니다(상한을 넘지 않음).';
  return `최대 HP = 기준값 + ${ability.name}의 보정((점수 - ${rules.modifier.base}) ÷ ${rules.modifier.step}, 내림). 상한을 넘지 않습니다.`;
}

