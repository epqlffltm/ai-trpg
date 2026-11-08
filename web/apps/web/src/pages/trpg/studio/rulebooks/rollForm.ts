// web/apps/web/src/pages/trpg/studio/rulebooks/rollForm.ts
// 룰북의 판정 방식(#404) 입력. 주사위의 면 수(die), 개수, 성공을 가르는 쪽(over, under), 난이도마다 기량에 더하는 값.
// 화면을 그리지 않는 순수한 함수다. 서버의 규칙(trpg-server/app/engine/ruleset.py 의 Roll)과 같은 범위로 본다.
//
//   - 난이도는 템플릿에서 온다. 고칠 수 없고, under 의 기량에 더하는 값의 이름표로만 쓴다
//   - over 면 기량에 더하는 값을 보내지 않는다(빈 것). under 면 난이도마다 하나씩 보낸다
//   - under 는 방어 규칙과 함께 쓰지 못한다(서버가 422 roll). 보내기 전에 알린다
//   - 죽음의 굴림과 되살아나기의 목표에 닿는지는 서버가 본다(422 die, roll)

import type { Difficulty, Roll, RollStyle, Ruleset } from '../../../../api/types';

export type ShiftDraft = { key: string; name: string; value: string };

export type RollDraft = { die: string; count: string; style: RollStyle; shifts: ShiftDraft[] };

// 서버의 한도(app/engine/ruleset.py 의 RULESET_MIN_DIE, RULESET_MAX_DIE, RULESET_MAX_DICE, RULESET_MAX_NUMBER)
export const DIE_MIN = 2;
export const DIE_MAX = 100;
export const COUNT_MAX = 10;
const SHIFT_MAX = 1000;

export const ROLL_STYLES: RollStyle[] = ['over', 'under'];

/** 규칙의 굴림을 고칠 거리로. 난이도마다 칸이 하나 있다(over 면 0 으로 채워 둔다) */
export function rollDraft(rules: Pick<Ruleset, 'die' | 'roll' | 'difficulties'>): RollDraft {
  return {
    die: String(rules.die),
    count: String(rules.roll.count),
    style: rules.roll.style,
    shifts: rules.difficulties.map((difficulty: Difficulty) => ({
      key: difficulty.key,
      name: difficulty.name,
      value: String(rules.roll.shifts[difficulty.key] ?? 0),
    })),
  };
}

/** 칸의 글을 부호가 있을 수 있는 정수로. 정수가 아니거나 범위 밖이면 null */
export function signedNumber(value: string, min: number, max: number): number | null {
  if (!/^[-+]?\d+$/.test(value.trim())) return null;
  const number = Number(value.trim());
  return number >= min && number <= max ? number : null;
}

function whole(value: string, min: number, max: number): number | null {
  const number = signedNumber(value, min, max);
  return number !== null && !value.trim().startsWith('-') ? number : null;
}

/** 보내기 전에 알릴 것. 칸 이름 → 글. armored 는 방어 규칙을 쓰는가(under 와 함께 쓰지 못한다) */
export function rollHints(draft: RollDraft, armored: boolean): Record<string, string> {
  const hints: Record<string, string> = {};
  if (whole(draft.die, DIE_MIN, DIE_MAX) === null) hints.die = `주사위의 면 수를 ${DIE_MIN}~${DIE_MAX} 사이의 정수로 적어 주세요.`;
  if (whole(draft.count, 1, COUNT_MAX) === null) hints.roll_count = `주사위의 개수를 1~${COUNT_MAX} 사이의 정수로 적어 주세요.`;
  if (draft.style !== 'under') return hints;
  if (armored) hints.roll_style = '눈이 기량 이하인 방식은 아직 방어 규칙과 함께 쓰지 못합니다. 방어 규칙을 "방어구가 막지 않음"으로 바꿔 주세요.';
  draft.shifts.forEach((shift) => {
    if (signedNumber(shift.value, -SHIFT_MAX, SHIFT_MAX) === null) {
      hints[`shift.${shift.key}`] = `-${SHIFT_MAX}~${SHIFT_MAX} 사이의 정수로 적어 주세요.`;
    }
  });
  return hints;
}

/** 보낼 주사위의 면 수. 검사(rollHints)를 지난 뒤에 부른다 */
export function toDie(draft: RollDraft): number {
  return whole(draft.die, DIE_MIN, DIE_MAX) ?? DIE_MIN;
}

/** 보낼 굴림. over 면 기량에 더하는 값이 빈 것이다. 검사(rollHints)를 지난 뒤에 부른다 */
export function toRoll(draft: RollDraft): Roll {
  const count = whole(draft.count, 1, COUNT_MAX) ?? 1;
  if (draft.style !== 'under') return { count, style: 'over', shifts: {} };
  const shifts = Object.fromEntries(draft.shifts.map((shift) => [shift.key, signedNumber(shift.value, -SHIFT_MAX, SHIFT_MAX) ?? 0]));
  return { count, style: 'under', shifts };
}

/** 굴리는 주사위의 이름. "d20", "2d6". 칸이 아직 틀렸으면 null */
export function diceName(draft: RollDraft): string | null {
  const die = whole(draft.die, DIE_MIN, DIE_MAX);
  const count = whole(draft.count, 1, COUNT_MAX);
  if (die === null || count === null) return null;
  return `${count === 1 ? '' : count}d${die}`;
}
