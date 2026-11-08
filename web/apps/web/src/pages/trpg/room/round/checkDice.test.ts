// web/apps/web/src/pages/trpg/room/round/checkDice.test.ts
// 판정의 숫자를 보일 글(#404). over 와 under, 주사위 여럿, 방식이 없는 옛 결과.

import { describe, expect, it } from 'vitest';
import { checkDice, checkShort } from './checkDice';

const OVER = { roll: 8, modifier: 1, total: 9, target: 15, success: false };

describe('판정의 숫자', () => {
  it('over 는 눈, 보정, 합, 목표. 방식이 없는 옛 결과도 같다', () => {
    expect(checkDice({ ...OVER, style: 'over', faces: [8] })).toBe('눈 8, 보정 +1, 합 9 / 목표 15');
    expect(checkDice({ ...OVER, modifier: -2, total: 6 })).toBe('눈 8, 보정 -2, 합 6 / 목표 15');
    expect(checkShort(OVER)).toBe('판정 9 / 15');
  });

  it('주사위를 여럿 굴렸으면 눈들을 붙인다', () => {
    expect(checkDice({ ...OVER, roll: 7, total: 8, faces: [3, 4] })).toBe('눈 3+4=7, 보정 +1, 합 8 / 목표 15');
  });

  it('under 는 눈과 기량을 견준다', () => {
    const under = { roll: 34, modifier: 0, total: 34, target: 45, success: true, style: 'under', faces: [34] };
    expect(checkDice(under)).toBe('눈 34 ≤ 기량 45');
    expect(checkDice({ ...under, roll: 46, total: 46, success: false })).toBe('눈 46 > 기량 45');
    expect(checkShort(under)).toBe('눈 34 ≤ 기량 45');
  });
});
