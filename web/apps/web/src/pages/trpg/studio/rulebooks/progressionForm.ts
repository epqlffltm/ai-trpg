// web/apps/web/src/pages/trpg/studio/rulebooks/progressionForm.ts
// 룰북의 성장(#286, rules.progression)의 입력. 레벨표다. 순수한 함수다(서버의 Progression, LevelStep,
// trpg-server/app/engine/ruleset.py 를 따른다).
//
// - 끄면(null) 캐릭터가 성장하지 않는 규칙이다. 켜면 레벨 2 부터 한 줄씩 적는다. 레벨 20 까지(19줄)
// - 줄마다 그 레벨이 되는 누적 경험치(1~1,000,000), 오를 때 최대 HP 에 더하는 양(0~99), 받는 능력치 점수(0~10)
// - 경험치는 줄마다 커야 한다(서버가 거절한다). 보내기 전에 알린다
// 숫자 칸은 고치는 동안 글로 둔다. 보낼 때 정수로 바꾼다.

import type { LevelStep, Progression } from '../../../../api/types';

// 서버의 한도(trpg-server/app/engine/ruleset.py 의 RULESET_MAX_LEVEL, PROGRESSION_MAX_XP, LEVEL_MAX_HP_GAIN, LEVEL_MAX_POINTS)
export const MAX_LEVEL = 20;
export const MAX_LEVEL_ROWS = MAX_LEVEL - 1;
export const LEVEL_XP_MAX = 1_000_000;
export const LEVEL_HP_MAX = 99;
export const LEVEL_POINTS_MAX = 10;
const FIRST_XP = 100;

export type LevelDraft = { xp: string; maxHp: string; points: string };

export type ProgressionDraft = {
  /** 캐릭터가 성장하는 규칙인가. 끄면 표는 남겨 두되 보내지 않는다(null) */
  on: boolean;
  levels: LevelDraft[];
};

/** 칸의 글을 정수로. 정수가 아니거나 범위 밖이면 null(rulebookForm.ts 의 것과 같다. 서로 가져오지 않게 둔다) */
function wholeNumber(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const number = Number(value.trim());
  return number >= min && number <= max ? number : null;
}

function levelDraft(level: LevelStep): LevelDraft {
  return { xp: String(level.xp), maxHp: String(level.max_hp ?? 0), points: String(level.points ?? 0) };
}

/** 서버의 성장을 고칠 거리로. 없으면 꺼진 빈 표 */
export function progressionDraft(progression: Progression | null | undefined): ProgressionDraft {
  return progression ? { on: true, levels: progression.levels.map(levelDraft) } : { on: false, levels: [] };
}

/** 새 줄 하나. 앞 줄 경험치의 두 배(앞 줄이 없거나 읽을 수 없으면 100), 최대 HP 0, 점수 1 */
export function newLevelDraft(levels: LevelDraft[]): LevelDraft {
  const previous = levels[levels.length - 1];
  const last = previous ? wholeNumber(previous.xp, 1, LEVEL_XP_MAX) : null;
  const xp = last === null ? FIRST_XP : Math.min(last * 2, LEVEL_XP_MAX);
  return { xp: String(xp), maxHp: '0', points: '1' };
}

/** 켠다. 표가 비었으면 첫 줄을 둔다(켠 채로 빈 표는 보낼 수 없다) */
export function turnedOn(draft: ProgressionDraft, on: boolean): ProgressionDraft {
  if (!on || draft.levels.length > 0) return { ...draft, on };
  return { on, levels: [newLevelDraft([])] };
}

/** 그 줄이 되는 레벨. 첫 줄이 레벨 2 다 */
export function levelOf(index: number): number {
  return index + 2;
}

function rowHints(level: LevelDraft, index: number): Record<string, string> {
  const hints: Record<string, string> = {};
  if (wholeNumber(level.xp, 1, LEVEL_XP_MAX) === null) hints[`level.${index}.xp`] = `1~${LEVEL_XP_MAX.toLocaleString('ko-KR')} 사이의 정수입니다.`;
  if (wholeNumber(level.maxHp, 0, LEVEL_HP_MAX) === null) hints[`level.${index}.max_hp`] = `0~${LEVEL_HP_MAX} 사이의 정수입니다.`;
  if (wholeNumber(level.points, 0, LEVEL_POINTS_MAX) === null) hints[`level.${index}.points`] = `0~${LEVEL_POINTS_MAX} 사이의 정수입니다.`;
  return hints;
}

/** 앞 줄보다 경험치가 크지 않은 첫 줄. 읽을 수 없는 칸은 rowHints 가 알리므로 건너뛴다 */
function firstNotRising(levels: LevelDraft[]): number | null {
  const needed = levels.map((level) => wholeNumber(level.xp, 1, LEVEL_XP_MAX));
  for (let index = 1; index < needed.length; index += 1) {
    const earlier = needed[index - 1];
    const later = needed[index];
    if (earlier != null && later != null && later <= earlier) return index;
  }
  return null;
}

/** 보내기 전에 알릴 것. 칸 이름(level.<줄>.<칸>, progression) → 글. 꺼져 있으면 없다 */
export function progressionHints(draft: ProgressionDraft): Record<string, string> {
  if (!draft.on) return {};
  const hints: Record<string, string> = {};
  if (draft.levels.length === 0) hints.progression = '레벨을 한 줄은 적어 주세요. 성장하지 않으려면 끄세요.';
  if (draft.levels.length > MAX_LEVEL_ROWS) hints.progression = `레벨 ${MAX_LEVEL}까지(${MAX_LEVEL_ROWS}줄) 적을 수 있습니다.`;
  draft.levels.forEach((level, index) => Object.assign(hints, rowHints(level, index)));
  const wrong = firstNotRising(draft.levels);
  if (wrong !== null && !hints[`level.${wrong}.xp`]) hints[`level.${wrong}.xp`] = `레벨 ${levelOf(wrong - 1)}의 경험치보다 커야 합니다.`;
  return hints;
}

/** 보낼 성장. 꺼져 있으면 null. 검사(progressionHints)를 지난 뒤에 부른다 */
export function toProgression(draft: ProgressionDraft): Progression | null {
  if (!draft.on) return null;
  return {
    levels: draft.levels.map((level) => ({ xp: Number(level.xp.trim()), max_hp: Number(level.maxHp.trim()), points: Number(level.points.trim()) })),
  };
}
