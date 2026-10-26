// web/apps/web/src/pages/trpg/room/round/action/friendlyFire.test.ts
// 동료 피해(#803)의 순수한 함수. 고를 수 있는 동료, 던질 쪽, 장난의 노려 치기, 보내는 값, 결과의 줄, 정도의 낮은 쪽을 본다.

import { describe, expect, it } from 'vitest';
import type { Declaration, FriendlyFire, TableDetail, TableMember } from '../../../../../api/types';
import { ME, member, OTHER, RULES, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { lowerFriendlyFire } from '../../../labels';
import { outcomeLine } from '../roundView';
import { emptyActionDraft, toAction } from './actionDraft';
import { aimableInjuries, allyTargets, isPrankToward, throwTargets, useTargets, type ActionContext } from './actionOptions';

const THIRD = '00000000-0000-4000-8000-0000000000e3';
const POTION = { entry_id: 'i1', name: '물약', kind: 'consumable', rarity: 'normal', effects: [{ kind: 'heal', magnitude: 'light' }], aids: [] };
const DAGGER = { entry_id: 'i9', name: '독 단검', kind: 'consumable', rarity: 'normal', effects: [{ kind: 'damage', magnitude: 'light' }], aids: [] };

type Seat = { level: FriendlyFire; place?: string; hp?: number };

/** 나(렌)와 미아, 조. 테이블의 정도와 둘이 받아들인 정도, 선 곳과 HP 를 고른다 */
function context(table: FriendlyFire, other: Seat, third: Seat = { level: 'off' }): ActionContext {
  const detail = tableDetail('t', {
    status: 'playing',
    friendly_fire: table,
    items: [POTION, DAGGER],
    members: [
      member(ME, { character: { name: '렌', description: '' }, sheet: sheet({ place_id: 'p1', items: [{ ...DAGGER, count: 1 }, { ...POTION, count: 1 }] }) }),
      member(OTHER, {
        character: { name: '미아', description: '' },
        friendly_fire: other.level,
        sheet: sheet({ place_id: other.place ?? 'p1', hp: other.hp ?? 12 }),
      }),
      member(THIRD, {
        character: { name: '조', description: '' },
        friendly_fire: third.level,
        sheet: sheet({ place_id: third.place ?? 'p1', hp: third.hp ?? 12 }),
      }),
    ],
  }) as unknown as TableDetail;
  return { table: detail, me: detail.members[0] as TableMember, cast: { round: 1, people: [], monsters: [] } };
}

describe('고를 수 있는 동료', () => {
  it('테이블과 그 사람이 받아들인 것 중 낮은 쪽이 끔이 아니어야 한다', () => {
    expect(allyTargets(context('full', { level: 'prank' }, { level: 'full' }))).toEqual([
      { value: `member:${OTHER}`, label: '미아(동료, 장난만)' },
      { value: `member:${THIRD}`, label: '조(동료, 다 됨)' },
    ]);
    expect(allyTargets(context('off', { level: 'full' }))).toEqual([]);
    expect(allyTargets(context('full', { level: 'off' }))).toEqual([]);
  });

  it('다른 곳에 있거나 쓰러진 동료는 고르지 않는다', () => {
    const ctx = context('full', { level: 'full', place: 'p2' }, { level: 'full', hp: 0 });

    expect(allyTargets(ctx)).toEqual([]);
  });

  it('해로운 물건을 쓰고 던질 쪽은 해칠 수 있는 동료만, 이로운 물건은 같은 곳의 동료 모두다', () => {
    const ctx = context('full', { level: 'full' }, { level: 'off', hp: 0 });

    expect(useTargets(ctx, 'i9').map((choice) => choice.value)).toEqual([`member:${OTHER}`]);
    expect(throwTargets(ctx, 'i9').map((choice) => choice.value)).toEqual([`member:${OTHER}`]);
    expect(throwTargets(ctx, 'i1').map((choice) => choice.value)).toEqual([`member:${OTHER}`, `member:${THIRD}`]);
  });

  it('장난이면 오래 가는 부상과 결손을 노리지 않는다', () => {
    const ctx = context('prank', { level: 'full' });

    expect(isPrankToward(ctx, `member:${OTHER}`)).toBe(true);
    expect(aimableInjuries(ctx, true)).toEqual([]);
    expect(aimableInjuries(ctx).map((choice) => choice.value)).toEqual(['broken_arm', 'lost_eye']);
    expect(RULES.injuries.filter((injury) => injury.aimable).every((injury) => injury.healing !== 'rounds')).toBe(true);
  });
});

describe('보내는 값', () => {
  it('동료를 치면 target 이고 죽이려 하지 않는다', () => {
    const ctx = context('full', { level: 'full' });
    const draft = { ...emptyActionDraft(ctx.table.rules), kind: 'check' as const, purpose: 'harm' as const, target: `member:${OTHER}`, lethal: true };

    expect(toAction(draft, ctx)).toMatchObject({ kind: 'check', harm: 'light', target: OTHER, lethal: false });
  });

  it('동료에게 던지면 target 이다', () => {
    const ctx = context('full', { level: 'full' });
    const draft = { ...emptyActionDraft(ctx.table.rules), kind: 'throw' as const, item: 'i9', target: `member:${OTHER}`, lethal: true };

    expect(toAction(draft, ctx)).toEqual({ kind: 'throw', item: 'i9', lethal: false, target: OTHER });
  });
});

describe('결과와 정도', () => {
  it('장난과 장난이라 입지 않은 부상, 해칠 수 없게 바뀐 것을 적는다', () => {
    const hit = {
      roll: 15, modifier: 0, total: 15, target: 15, success: true, hindrance: null, called_shot: null, npc_effect: null,
      effect: {
        kind: 'damage', magnitude: 'heavy', user_id: OTHER, character_name: '미아', rolls: [6, 6], amount: 12, before: 12, after: 1,
        max_hp: 12, downed: false, prank: true,
        injury_roll: { trigger: 'big_hit', roll: 20, injury: null, ends_after_round: null, spared: 'lost_eye' },
      },
    };
    const gone = { target_gone: { user_id: OTHER, name: '미아', reason: 'friendly_fire_off' } };

    expect(outcomeLine(hit as unknown as Declaration['outcome'], RULES as never)).toBe(
      '눈 15, 보정 +0, 합 15 / 목표 15 · 성공 · 미아 HP 12 → 1(장난) · 장난이라 입지 않음 잃은 눈',
    );
    expect(outcomeLine(gone as unknown as Declaration['outcome'], RULES as never)).toBe('그 동료를 해칠 수 없게 바뀌어 행동하지 못했습니다.');
    expect(outcomeLine({ target_gone: { monster_id: 'm', name: '쥐', reason: 'dead' } } as never, RULES as never)).toBe(
      '대상이 이미 없어 행동하지 못했습니다.',
    );
  });

  it('둘 중 낮은 정도', () => {
    expect(lowerFriendlyFire('full', 'prank')).toBe('prank');
    expect(lowerFriendlyFire('off', 'full')).toBe('off');
    expect(lowerFriendlyFire('prank', 'prank')).toBe('prank');
  });
});
