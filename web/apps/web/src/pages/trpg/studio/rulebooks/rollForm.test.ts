// web/apps/web/src/pages/trpg/studio/rulebooks/rollForm.test.ts
// 룰북의 판정 방식(#404) 입력. 처음 값, 검사(면 수, 개수, under 의 기량에 더하는 값, 방어 규칙과 함께 쓰지 못함), 보내는 굴림.

import { describe, expect, it } from 'vitest';
import type { Ruleset } from '../../../../api/types';
import { diceName, rollDraft, rollHints, signedNumber, toDie, toRoll } from './rollForm';

const RULES = {
  die: 20,
  roll: { count: 1, style: 'over', shifts: {} },
  difficulties: [
    { key: 'easy', name: '쉬움', target: 10 },
    { key: 'hard', name: '어려움', target: 20 },
  ],
} as unknown as Ruleset;

describe('판정 방식의 입력', () => {
  it('규칙의 것으로 채운다. 난이도마다 칸이 있고 over 면 0 이다', () => {
    const draft = rollDraft(RULES);
    expect(draft).toEqual({
      die: '20',
      count: '1',
      style: 'over',
      shifts: [
        { key: 'easy', name: '쉬움', value: '0' },
        { key: 'hard', name: '어려움', value: '0' },
      ],
    });
    const under = rollDraft({ ...RULES, roll: { count: 1, style: 'under', shifts: { easy: 10, hard: -20 } } });
    expect(under.shifts.map((shift) => shift.value)).toEqual(['10', '-20']);
  });

  it('면 수는 2~100, 개수는 1~10 의 정수다', () => {
    const draft = rollDraft(RULES);
    expect(rollHints(draft, true)).toEqual({});
    expect(Object.keys(rollHints({ ...draft, die: '1' }, false))).toEqual(['die']);
    expect(Object.keys(rollHints({ ...draft, die: '101' }, false))).toEqual(['die']);
    expect(Object.keys(rollHints({ ...draft, count: '11' }, false))).toEqual(['roll_count']);
    expect(Object.keys(rollHints({ ...draft, count: '-1' }, false))).toEqual(['roll_count']);
  });

  it('under 는 방어 규칙과 함께 쓰지 못하고, 기량에 더하는 값은 부호가 있는 정수다', () => {
    const draft = { ...rollDraft(RULES), die: '100', style: 'under' as const };
    expect(Object.keys(rollHints(draft, true))).toEqual(['roll_style']);
    expect(rollHints(draft, false)).toEqual({});
    const wrong = { ...draft, shifts: [{ key: 'easy', name: '쉬움', value: '1.5' }, { key: 'hard', name: '어려움', value: '-20' }] };
    expect(Object.keys(rollHints(wrong, false))).toEqual(['shift.easy']);
    expect(signedNumber(' -20 ', -1000, 1000)).toBe(-20);
    expect(signedNumber('+5', -1000, 1000)).toBe(5);
    expect(signedNumber('1001', -1000, 1000)).toBeNull();
  });

  it('보내는 굴림. over 면 기량에 더하는 값이 빈 것, under 면 난이도마다 하나다', () => {
    const draft = { ...rollDraft(RULES), die: '6', count: '2' };
    expect([toDie(draft), toRoll(draft)]).toEqual([6, { count: 2, style: 'over', shifts: {} }]);
    expect(diceName(draft)).toBe('2d6');
    const under = { ...draft, die: '100', count: '1', style: 'under' as const, shifts: [{ key: 'easy', name: '쉬움', value: '10' }, { key: 'hard', name: '어려움', value: '-20' }] };
    expect(toRoll(under)).toEqual({ count: 1, style: 'under', shifts: { easy: 10, hard: -20 } });
    expect(diceName(under)).toBe('d100');
    expect(diceName({ ...under, die: '' })).toBeNull();
  });
});
