// web/apps/web/src/pages/trpg/room/status/growthPure.test.ts
// 성장(#286)의 순수한 함수. 레벨 한 줄과 막대, 놓을 수 있는 때, 올리고 내리기(남은 점수와 상한), 고른 것의 한 줄, 실패의 글.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../../api/errors';
import type { Round, Ruleset, Sheet, TableDetail, TableMember } from '../../../../api/types';
import { ME, member, RULES, round, sheet as sheetOf, tableDetail } from '../../../../test/tableFixtures';
import { canRaise, canStepUp, levelLine, levelRatio, raisesLine, spent, stepped } from './growthView';
import { describeRaiseProblem } from './raiseProblem';

const LEVELS = [
  { xp: 100, max_hp: 2, points: 1 },
  { xp: 300, max_hp: 2, points: 2 },
];
const GROWING = { ...RULES, progression: { levels: LEVELS } } as unknown as Ruleset;
const STILL = { ...RULES, progression: null } as unknown as Ruleset;

function grown(extra: Record<string, unknown> = {}): Sheet {
  return sheetOf({ xp: 150, level: 2, next_level_xp: 300, points: 2, ...extra }) as unknown as Sheet;
}

describe('레벨의 글', () => {
  it('레벨과 경험치, 다음 레벨. 마지막 레벨이면 그렇다고, 성장이 없으면 그리지 않는다', () => {
    expect(levelLine(grown(), GROWING)).toBe('레벨 2 · 경험치 150 / 300');
    expect(levelLine(grown({ xp: 4200, level: 3, next_level_xp: null }), GROWING)).toBe('레벨 3 · 경험치 4,200 · 마지막 레벨');
    expect(levelLine(grown(), STILL)).toBeNull();
  });

  it('막대는 지금 레벨이 된 경험치부터 다음 레벨까지의 비율', () => {
    expect(levelRatio(grown(), GROWING)).toBe(0.25);
    expect(levelRatio(grown({ xp: 50, level: 1, next_level_xp: 100 }), GROWING)).toBe(0.5);
    expect(levelRatio(grown({ next_level_xp: null }), GROWING)).toBe(1);
  });
});

describe('점수 놓기', () => {
  const playing = tableDetail('t', { status: 'playing' }) as unknown as TableDetail;
  const me = (extra: Record<string, unknown>) => member(ME, { sheet: grown(extra) }) as unknown as TableMember;
  const open = round(2) as unknown as Round;

  it('진행 중이고 선언을 받는 중이고 살아 있고 점수가 있을 때만. 쓰러져도 놓는다', () => {
    expect(canRaise(playing, me({}), open)).toBe(true);
    expect(canRaise(playing, me({ hp: 0 }), open)).toBe(true);
    expect(canRaise(playing, me({ dead: true }), open)).toBe(false);
    expect(canRaise(playing, me({ points: 0 }), open)).toBe(false);
    expect(canRaise(playing, me({}), { ...open, status: 'closing' } as Round)).toBe(false);
    expect(canRaise({ ...playing, status: 'ended' } as TableDetail, me({}), open)).toBe(false);
    expect(canRaise(playing, undefined, open)).toBe(false);
  });

  it('올리기는 남은 점수와 상한까지, 내리기는 0 까지. 0 이 되면 뺀다', () => {
    const sheet = grown({ abilities: { str: 17, dex: 12, con: 10 } });
    let raises = stepped({}, 'str', 1, sheet, GROWING);
    expect(raises).toEqual({ str: 1 });
    expect(canStepUp(raises, 'str', sheet, GROWING)).toBe(false); // 18 이 상한
    expect(stepped(raises, 'str', 1, sheet, GROWING)).toBe(raises);
    raises = stepped(raises, 'con', 1, sheet, GROWING);
    expect(spent(raises)).toBe(2);
    expect(canStepUp(raises, 'dex', sheet, GROWING)).toBe(false); // 점수 2 를 다 썼다
    expect(stepped(raises, 'str', -1, sheet, GROWING)).toEqual({ con: 1 });
    expect(stepped({}, 'dex', -1, sheet, GROWING)).toEqual({});
  });

  it('고른 것을 규칙의 차례로 한 줄에', () => {
    expect(raisesLine({ con: 2, str: 1 }, grown(), GROWING)).toBe('근력 14 → 15, 건강 10 → 12');
  });

  it('실패는 까닭마다 글이 있고 테이블을 다시 읽는다', () => {
    const conflict = (code: string) => describeRaiseProblem(new ApiError({ status: 409, detail: 'x', code }));
    expect(conflict('not_enough_points')).toEqual({ message: '남은 점수가 모자랍니다.', refresh: true });
    expect(conflict('ability_at_max').message).toContain('상한');
    expect(conflict('round_closing').message).toContain('마감하는 중');
    expect(conflict('character_dead').message).toContain('죽은 캐릭터');
    expect(describeRaiseProblem(new ApiError({ status: 422, detail: 'x' }))).toMatchObject({ refresh: true });
  });
});
