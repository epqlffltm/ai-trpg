// web/apps/web/src/pages/trpg/room/round/mapOutcome.test.ts
// 가기의 결과 한 줄(지나며 연 문, 넘기 판정과 다친 것, 걸린 시간, 업기, 못 간 까닭)과 문을 다룬 결과. 라운드의 결과 줄(outcomeLine)이 이것을 쓴다.
// 선언의 행동 한 줄(actionLabel)에 다룬 문을 적는다.

import { describe, expect, it } from 'vitest';
import { RULES } from '../../../../test/tableFixtures';
import { doorLine, moveLine } from './mapOutcome';
import { actionLabel, outcomeLine } from './roundView';

const ME = '00000000-0000-4000-8000-0000000000e1';
const GATE = { entry_id: 'g', name: '수도원 문' };
const TOWER = { entry_id: 't', name: '종탑' };
const MOVE = { user_id: ME, character_name: '렌', from: GATE, to: TOWER, moved: true, reason: null, unlocked: false, unbarred: false, traps: [] };
const ROLL = { ability: 'str', difficulty: 'normal', modifier: -1, roll: 8, total: 7, target: 15, success: false };

describe('가기의 결과', () => {
  it('닿은 곳, 열쇠로 연 자물쇠, 푼 빗장, 걸린 시간, 업고 간 사람', () => {
    const carry = { user_id: ME, character_name: '미아', carried: true, reason: null };
    expect(moveLine({ ...MOVE, unlocked: true, unbarred: true, travel_minutes: 30, carry })).toBe(
      '종탑에 닿았습니다 · 열쇠로 자물쇠를 엶 · 빗장을 풂 · 30분 걸림 · 미아 업고 감',
    );
    expect(outcomeLine({ move: MOVE }, RULES as never)).toBe('종탑에 닿았습니다');
  });

  it('못 간 까닭, 넘기 판정과 다친 것, 업지 못한 까닭', () => {
    const effect = { kind: 'damage' as const, magnitude: 'light', user_id: ME, character_name: '렌', rolls: [3], amount: 3, before: 7, after: 4, max_hp: 12, downed: false, prank: false };
    const carry = { user_id: ME, character_name: null, carried: false, reason: 'not_moved' };
    expect(moveLine({ ...MOVE, moved: false, reason: 'cross_failed', cross: ROLL, effect, carry, travel_minutes: 30 })).toBe(
      '가지 못했습니다(넘지 못했습니다) · 넘기 판정 눈 8, 보정 -1, 합 7 / 목표 15 · 실패 · 렌 HP 7 → 4 · 떠난 사람 업지 못함(가지 못했습니다)',
    );
    expect(moveLine({ ...MOVE, moved: false, reason: 'locked' })).toBe('가지 못했습니다(잠겨 있었고 열쇠가 없었습니다)');
    expect(moveLine({ ...MOVE, moved: false, reason: 'teleported' })).toBe('가지 못했습니다(teleported)');
  });
});

describe('넘기에 붙여 쓴 물건(#802)', () => {
  it('쓴 밧줄을 보이고, 굴리지 않았으면 적지 않는다', () => {
    const aid = { entry_id: 'r', name: '밧줄', act: 'cross', bonus: 5, used: true, lost: false, broken: false, reason: null, remaining: 1 };
    const climbed = { ...ROLL, modifier: 5, total: 13, success: false };
    expect(moveLine({ ...MOVE, moved: false, reason: 'cross_failed', cross: climbed, aid })).toBe(
      '가지 못했습니다(넘지 못했습니다) · 넘기 판정 눈 8, 보정 +5, 합 13 / 목표 15 · 실패 · 밧줄 +5 씀',
    );
    expect(moveLine({ ...MOVE, moved: false, reason: 'not_adjacent', aid: { ...aid, used: false, bonus: 0 } })).toBe('가지 못했습니다(그사이 옮겨져 이어진 길이 없었습니다)');
    expect(moveLine({ ...MOVE, aid: { ...aid, bonus: 0, lost: true, broken: false } })).toBe('종탑에 닿았습니다 · 밧줄 씀, 다 씀');
  });
});

describe('들어간 곳에서 터진 덫(#806)', () => {
  it('덫마다 피했는지와 판정, 걸렸으면 HP 를 붙인다', () => {
    const avoid = { ...ROLL, ability: 'dex' };
    const base = { trap_id: 'x', entry_id: 'snare', name: '올가미', set_by: ME, injured: [], resources: [] };
    const effect = { kind: 'damage' as const, magnitude: 'light', user_id: ME, character_name: '렌', rolls: [3], amount: 3, before: 7, after: 4, max_hp: 12, downed: false, prank: false };
    const caught = { ...base, avoid, avoided: false, effect };
    const dodged = { ...base, trap_id: 'y', avoid: { ...avoid, roll: 18, total: 17, success: true }, avoided: true, effect: null };
    expect(moveLine({ ...MOVE, traps: [caught, dodged] })).toBe(
      '종탑에 닿았습니다 · 덫 올가미: 걸림(눈 8, 보정 -1, 합 7 / 목표 15) · 렌 HP 7 → 4 · 덫 올가미: 피함(눈 18, 보정 -1, 합 17 / 목표 15)',
    );
  });
});

describe('문을 다룬 결과', () => {
  it('해낸 일, 못 한 까닭, 판정', () => {
    const door = { user_id: ME, character_name: '렌', from: GATE, to: TOWER, act: 'force', device: null, done: false, reason: 'failed', check: ROLL };
    expect(doorLine(door)).toBe('종탑 쪽 문: 부수지 못했습니다(판정에 실패했습니다) · 눈 8, 보정 -1, 합 7 / 목표 15');
    expect(doorLine({ ...door, act: 'lock', device: 'lock', done: true, reason: null, check: null })).toBe('종탑 쪽 자물쇠: 잠갔습니다');
  });

  it('선언의 행동 한 줄에 다룬 문(장치를 적었으면 장치)을 적는다', () => {
    const table = { rules: RULES, currency: null, map: { places: [{ ...TOWER, entry_id: 't', items: [] }], routes: [] } } as never;
    expect(actionLabel({ kind: 'pick', place: 't' }, table)).toBe('따기 · 종탑 쪽 문');
    expect(actionLabel({ kind: 'unlock', place: 't', device: 'bar' }, table)).toBe('열기 · 종탑 쪽 빗장');
    expect(actionLabel({ kind: 'force', place: 'gone' }, table)).toBe('부수기');
  });
});
