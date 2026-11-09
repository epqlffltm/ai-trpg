// web/apps/web/src/pages/trpg/studio/scenarios/monsterMovesForm.test.ts
// 몬스터 시트의 사냥과 배회(#254)의 입력, 조우의 순찰 경로의 검사. 순수한 함수다.

import { describe, expect, it } from 'vitest';
import type { MonsterSheet } from '../../../../api/types';
import { patrolHint, withPatrolPlace, PATROL_MAX_PLACES } from './encountersForm';
import { hasMovesHints, movesDraft, movesHints, movesLine, toHunts, toRoams } from './monsterMovesForm';

const sheet = (fields: Partial<MonsterSheet>) => fields as MonsterSheet;

describe('사냥과 배회의 입력', () => {
  it('비우면 보내지 않고, 받은 값은 그대로 돌아간다', () => {
    const empty = movesDraft(undefined);
    expect([toHunts(empty), toRoams(empty), hasMovesHints(movesHints(empty))]).toEqual([null, null, false]);
    const filled = movesDraft(sheet({ hunts: 3, roams: { chance: 40, reach: 2 } }));
    expect([toHunts(filled), toRoams(filled)]).toEqual([3, { chance: 40, reach: 2 }]);
  });

  it('범위를 보고, 배회는 둘을 함께 적는다', () => {
    expect(movesHints({ hunts: '0', chance: '101', reach: '6' })).toEqual({
      hunts: '1~5 사이의 정수입니다.',
      chance: '1~100 사이의 정수입니다.',
      reach: '1~5 사이의 정수입니다.',
    });
    expect(movesHints({ hunts: '5', chance: '100', reach: '5' })).toEqual({});
    expect(movesHints({ hunts: '', chance: '', reach: '2' }).chance).toBe('배회하려면 확률도 적어 주세요.');
    expect(movesHints({ hunts: '', chance: '20', reach: '' }).reach).toBe('배회하려면 칸 수도 적어 주세요.');
  });

  it('목록의 줄', () => {
    expect(movesLine(sheet({ hunts: 2, roams: { chance: 30, reach: 1 } }))).toEqual(['사냥 2칸', '배회 30% · 1칸']);
    expect(movesLine(sheet({ hunts: null, roams: null }))).toEqual([]);
  });
});

describe('순찰 경로', () => {
  it('고르지 않은 줄과 잇달아 같은 장소를 막는다(처음 자리로 돌아오는 끝도)', () => {
    expect(patrolHint('a', [])).toBeNull();
    expect(patrolHint('a', ['b', 'c'])).toBeNull();
    expect(patrolHint('a', ['b', ''])).toBe('순찰할 장소를 골라 주세요.');
    expect(patrolHint('a', ['a'])).toMatch(/잇달아/);
    expect(patrolHint('a', ['b', 'b'])).toMatch(/잇달아/);
    expect(patrolHint('a', ['b', 'a'])).toMatch(/잇달아/);
  });

  it('줄을 더하고 바꾸고 뺀다. 한도에서 더하지 않는다', () => {
    expect(withPatrolPlace(['b'], null, null)).toEqual(['b', '']);
    expect(withPatrolPlace(['b', ''], 1, 'c')).toEqual(['b', 'c']);
    expect(withPatrolPlace(['b', 'c'], 0, null)).toEqual(['c']);
    const full = Array.from({ length: PATROL_MAX_PLACES }, (_, index) => String(index));
    expect(withPatrolPlace(full, null, null)).toHaveLength(PATROL_MAX_PLACES);
  });
});
