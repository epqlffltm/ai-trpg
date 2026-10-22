// web/apps/web/src/pages/trpg/room/character/characterPure.test.ts
// 캐릭터 정하기(B5)의 순수한 함수. 서버의 검사(characters.py, point_buy.py, score_roll.py, creation.py)와 같은 답을 내는지 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../../api/errors';
import type { TableDetail, TableMember } from '../../../../api/types';
import { ME, member, OTHER, roll, RULES, tableDetail } from '../../../../test/tableFixtures';
import {
  draftHints,
  freshRoll,
  initialDraft,
  maxHpPreview,
  mayRoll,
  placedScores,
  placeSlot,
  pointsSpent,
  slotsFor,
  toCharacterUpdate,
  type CharacterDraft,
} from './characterForm';
import { describeCharacterProblem } from './characterProblem';
import { startingNumbers } from './CharacterPanel';

const TABLE = tableDetail('t1') as unknown as TableDetail;
const rules = TABLE.rules;

function me(extra: Record<string, unknown> = {}): TableMember {
  return member(ME, extra) as unknown as TableMember;
}

function draft(changes: Partial<CharacterDraft> = {}): CharacterDraft {
  return { ...initialDraft(TABLE, me()), name: '렌', ...changes };
}

describe('points and rolls', () => {
  it('점수제의 값을 더한다. 값표에 없는 점수가 있으면 null', () => {
    expect(pointsSpent(RULES.point_buy, { str: 14, dex: 10, con: 8 })).toBe(9);
    expect(pointsSpent(RULES.point_buy, { str: 15, dex: 10, con: 8 })).toBeNull();
  });

  it('지난 캐릭터를 위해 굴린 것은 쓰지 못한다. 굴리는 것은 한 번, 방장이 주면 한 번 더', () => {
    expect(freshRoll(me({ roll: roll([15, 12, 9]) }))).not.toBeNull();
    expect(freshRoll(me({ roll: roll([15, 12, 9], { character_number: 2 }) }))).toBeNull();
    expect(mayRoll(me())).toBe(true);
    expect(mayRoll(me({ roll: roll([15, 12, 9]) }))).toBe(false);
    expect(mayRoll(me({ roll: roll([15, 12, 9], { reroll_granted: true }) }))).toBe(true);
  });

  it('굴린 점수를 남김없이 한 번씩 놓아야 점수가 된다. 다시 굴리면 놓은 것을 버린다', () => {
    const rolled = roll([15, 12, 12]) as NonNullable<TableMember['roll']>;
    let current = draft({ mode: 'rolled' });
    current = { ...current, ...placeSlot(current, rolled, 'str', 0) };
    current = { ...current, ...placeSlot(current, rolled, 'dex', 1) };
    expect(placedScores(current, rules, rolled)).toBeNull();
    current = { ...current, ...placeSlot(current, rolled, 'con', 2) };
    expect(placedScores(current, rules, rolled)).toEqual({ str: 15, dex: 12, con: 12 });
    expect(placedScores({ ...current, slots: { str: 0, dex: 1, con: 1 } }, rules, rolled)).toBeNull();
    expect(placedScores(current, rules, { ...rolled, times_rolled: 2 })).toBeNull();
  });

  it('정해 둔 점수를 굴린 자리로 되돌린다. 같은 점수는 앞의 자리부터', () => {
    expect(slotsFor(rules, { str: 12, dex: 15, con: 12 }, [15, 12, 12])).toEqual({ str: 1, dex: 0, con: 2 });
  });

  it('최대 HP 의 어림은 기준값에 건강의 보정을 더하고, 1 이상 상한 이하다', () => {
    const hp = { base: 8, cap: 20 };
    expect(maxHpPreview(rules, hp, { str: 10, dex: 10, con: 14 })).toBe(10);
    expect(maxHpPreview(rules, hp, { str: 10, dex: 10, con: 9 })).toBe(7);
    expect(maxHpPreview(rules, { base: 8, cap: 9 }, { str: 10, dex: 10, con: 18 })).toBe(9);
    expect(maxHpPreview(rules, { base: 1, cap: 9 }, { str: 10, dex: 10, con: 3 })).toBe(1);
    expect(maxHpPreview(rules, null, { str: 10, dex: 10, con: 10 })).toBeNull();
    expect(maxHpPreview(rules, hp, { str: 10, dex: 10, con: Number.NaN })).toBeNull();
  });
});

describe('draftHints', () => {
  it('프리젠은 고를 수 있는 것을 골라야 한다. 남의 것과 죽은 것은 안 된다', () => {
    expect(draftHints(draft({ mode: 'pregen', pregenIndex: 0 }), TABLE, ME, null)).toEqual({});
    expect(draftHints(draft({ mode: 'pregen', pregenIndex: 1 }), TABLE, ME, null).pregen).toBeDefined();
    expect(draftHints(draft({ mode: 'pregen', pregenIndex: 2 }), TABLE, ME, null).pregen).toBeDefined();
    expect(draftHints(draft({ mode: 'pregen', pregenIndex: 1 }), TABLE, OTHER, null)).toEqual({});
  });

  it('이름은 빈칸을 뺀 1~50자, 설명은 1000자까지', () => {
    expect(draftHints(draft({ mode: 'custom', name: '  ' }), TABLE, ME, null).name).toBe('이름을 적어 주세요.');
    expect(draftHints(draft({ mode: 'custom', name: 'ㄱ'.repeat(51) }), TABLE, ME, null).name).toBeDefined();
    expect(draftHints(draft({ mode: 'custom', description: 'ㄱ'.repeat(1001) }), TABLE, ME, null).description).toBeDefined();
    expect(draftHints(draft({ mode: 'custom' }), TABLE, ME, null)).toEqual({});
  });

  it('직접 적기는 범위 안의 정수만', () => {
    const ok = draft({ mode: 'manual', manual: { str: 18, dex: 3, con: 10 } });
    expect(draftHints(ok, TABLE, ME, null)).toEqual({});
    expect(draftHints({ ...ok, manual: { str: 19, dex: 3, con: 10 } }, TABLE, ME, null).abilities).toBeDefined();
    expect(draftHints({ ...ok, manual: { str: Number.NaN, dex: 3, con: 10 } }, TABLE, ME, null).abilities).toBeDefined();
    expect(draftHints({ ...ok, manual: { str: 10.5, dex: 3, con: 10 } }, TABLE, ME, null).abilities).toBeDefined();
  });

  it('점수제는 총점을 넘지 않아야 한다(다 쓰지 않아도 된다)', () => {
    expect(draftHints(draft({ mode: 'point_buy', bought: { str: 8, dex: 8, con: 8 } }), TABLE, ME, null)).toEqual({});
    const over = draftHints(draft({ mode: 'point_buy', bought: { str: 14, dex: 12, con: 8 } }), TABLE, ME, null);
    expect(over.abilities).toBe('총점 10을 넘었습니다(11).');
  });

  it('주사위는 먼저 굴려야 하고, 굴린 점수를 다 놓아야 한다', () => {
    const rolled = roll([15, 12, 9]) as NonNullable<TableMember['roll']>;
    expect(draftHints(draft({ mode: 'rolled' }), TABLE, ME, null).abilities).toBe('먼저 주사위를 굴려 주세요.');
    expect(draftHints(draft({ mode: 'rolled' }), TABLE, ME, rolled).abilities).toBeDefined();
    const placed = draft({ mode: 'rolled', slots: { str: 0, dex: 1, con: 2 }, slotsOf: 1 });
    expect(draftHints(placed, TABLE, ME, rolled)).toEqual({});
  });
});

describe('toCharacterUpdate', () => {
  it('프리젠은 번호만, 직접 쓰기는 이름과 설명, 능력치를 정하는 방식은 능력치도 보낸다', () => {
    expect(toCharacterUpdate(draft({ mode: 'pregen', pregenIndex: 0 }), rules, null)).toEqual({ mode: 'pregen', pregen_index: 0 });
    expect(toCharacterUpdate(draft({ mode: 'custom', name: ' 렌 ', description: '검사' }), rules, null)).toEqual({
      mode: 'custom',
      name: '렌',
      description: '검사',
    });
    const bought = { str: 14, dex: 10, con: 8 };
    expect(toCharacterUpdate(draft({ mode: 'point_buy', bought: { ...bought, extra: 3 } }), rules, null)).toEqual({
      mode: 'point_buy',
      name: '렌',
      description: '',
      abilities: bought,
    });
  });
});

describe('initialDraft', () => {
  it('처음이면 허용한 첫 방식, 고를 수 있는 첫 프리젠, 보정 0 의 점수, 가장 싼 점수다', () => {
    const fresh = initialDraft(TABLE, me());
    expect(fresh).toMatchObject({ mode: 'pregen', pregenIndex: 0, name: '' });
    expect(fresh.manual).toEqual({ str: 10, dex: 10, con: 10 });
    expect(fresh.bought).toEqual({ str: 8, dex: 8, con: 8 });
  });

  it('정해 둔 캐릭터로 채운다. 주사위로 정했으면 놓은 자리도', () => {
    const mine = me({
      character: { name: '렌', description: '검사' },
      character_mode: 'rolled',
      abilities: { str: 9, dex: 15, con: 12 },
      roll: roll([15, 12, 9]),
    });
    expect(initialDraft(TABLE, mine)).toMatchObject({
      mode: 'rolled',
      name: '렌',
      description: '검사',
      slots: { str: 2, dex: 0, con: 1 },
      slotsOf: 1,
    });
  });

  it('프리젠을 골라 두었으면 이름 칸은 비운다(프리젠의 이름을 쓴다)', () => {
    const mine = me({ character: { name: '렌', description: '' }, character_mode: 'pregen', pregen_index: 0 });
    expect(initialDraft(TABLE, mine)).toMatchObject({ mode: 'pregen', pregenIndex: 0, name: '' });
  });
});

describe('startingNumbers', () => {
  it('프리젠은 그 시트, 능력치를 정했으면 그 점수와 어림, 직접 쓰기는 기본 시트', () => {
    expect(startingNumbers(TABLE, me({ character_mode: 'pregen', pregen_index: 0 }))).toEqual({
      abilities: { str: 14, dex: 12, con: 10 },
      maxHp: 12,
      estimated: false,
    });
    expect(startingNumbers(TABLE, me({ character_mode: 'manual', abilities: { str: 10, dex: 10, con: 14 } }))).toEqual({
      abilities: { str: 10, dex: 10, con: 14 },
      maxHp: 10,
      estimated: true,
    });
    expect(startingNumbers(TABLE, me({ character_mode: 'custom' }))?.maxHp).toBe(10);
  });
});

describe('describeCharacterProblem', () => {
  it('409 는 까닭마다, 422 는 칸마다 알리고, 테이블이 달라졌으면 다시 읽게 한다', () => {
    const taken = describeCharacterProblem(new ApiError({ status: 409, detail: 'x', code: 'pregen_taken' }));
    expect(taken).toMatchObject({ refresh: true });
    expect(taken.message).toContain('다른 사람이 가져간');
    const abilities = describeCharacterProblem(new ApiError({ status: 422, detail: 'abilities 에 고를 수 없는 값이 있습니다.' }));
    expect(abilities.message).toContain('규칙에 맞지 않습니다');
    expect(describeCharacterProblem(new ApiError({ status: 404, detail: '없다' })).refresh).toBe(true);
  });
});
