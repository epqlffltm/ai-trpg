// web/apps/web/src/pages/trpg/room/round/actionOutcome.ts
// 물건, 훔치기와 빼앗기, 쉬기와 기다리기의 결과 한 줄. 순수한 함수다. 못 한 것과 덜 한 것은 서버의 까닭(reason)을 괄호로 붙인다.
// 까닭의 이름은 서버의 것이다(trpg-server/app/rounds 의 item_actions.py, throws.py, place_item_actions.py, trap_actions.py, steals.py, loots.py, rests.py, waits.py).
// 못 한 것은 이벤트로 오지 않아 이 줄에만 보인다. 이름 뒤에는 조사를 붙이지 않는다.

import type { Declaration, ResourceChange } from '../../../../api/types';
import { because } from './outcomeReason';

type Outcome = NonNullable<Declaration['outcome']>;
type Part<K extends string> = Extract<Outcome, Record<K, unknown>>[K & keyof Extract<Outcome, Record<K, unknown>>];

/** 쓰거나 건네지 못한 까닭(item_actions.py) */
const ITEM_REASONS: Record<string, string> = {
  not_held: '그만큼 가지고 있지 않았습니다',
  target_gone: '받을 사람이 떠났거나 죽었습니다',
  too_many: '받는 쪽이 더 가질 수 없었습니다',
  friendly_fire_off: '그 동료를 해칠 수 없게 바뀌었습니다',
};

/** 줍거나 내려놓지 못한 까닭(place_item_actions.py) */
const PLACE_REASONS: Record<string, string> = {
  gone: '앞사람이 가져가 남은 것이 없었습니다',
  not_enough: '남은 것이 모자라 남은 만큼만',
  full: '더 가질 수 없어 그만큼만',
  not_held: '내려놓을 만큼 가지고 있지 않았습니다',
};

/** 훔치거나 빼앗지 못한 까닭(steals.py, loots.py) */
const TAKE_FROM_REASONS: Record<string, string> = {
  gone: '대상이 그 물건을 더는 지니지 않았습니다',
  full: '더 가질 수 없어 그만큼만',
  awake: '대상이 깨어 있었습니다',
};

/** 쉬기가 깨진 까닭(rests.py) */
const REST_REASONS: Record<string, string> = {
  hurt: '그 라운드에 다쳤습니다',
  downed: '쓰러져 있었습니다',
  dead: '죽어 있었습니다',
  ambushed: '쉬는 중에 몬스터가 덮쳤습니다',
};

/** 기다리기가 깨진 까닭(waits.py) */
const WAIT_REASONS: Record<string, string> = {
  hurt: '누가 다쳐 시간을 건너뛰지 않았습니다',
  not_all: '모두가 기다리지는 않았습니다',
};

export function itemUseLine(use: Part<'item_use'>): string {
  if (!use.used) return `쓰지 못했습니다${because(ITEM_REASONS, use.reason)}`;
  return [`${use.name} 사용(남은 ${use.remaining}개)`, ...shiftParts(use.resources)].join(' · ');
}

/** 바뀐 수치들(#804). "마나 2 → 5/7" */
function shiftParts(shifts: ResourceChange[] | undefined): string[] {
  return (shifts ?? []).map((shift) => `${shift.name} ${shift.before} → ${shift.after}/${shift.max}`);
}

/** 던지지 못한 까닭(throws.py, #277) */
const THROW_REASONS: Record<string, string> = {
  not_held: '그 물건을 더 가지고 있지 않았습니다',
  target_gone: '겨눈 대상이 이미 없었습니다',
};

/** 던지지 못한 것. 던졌으면 판정의 줄이 결과다(물건은 하나 없어졌다) */
export function throwLine(thrown: Part<'item_throw'> | null | undefined): string {
  if (!thrown) return '던지지 못했습니다.';
  return thrown.thrown ? `${thrown.name} 던짐(남은 ${thrown.remaining}개)` : `던지지 못했습니다${because(THROW_REASONS, thrown.reason)}`;
}

export function giveLine(give: Part<'item_give'>): string {
  if (!give.given) return `건네지 못했습니다${because(ITEM_REASONS, give.reason)}`;
  return `${give.name} ×${give.count} → ${give.target.character_name ?? '누군가'}`;
}

/** 주운 것. 덜 주웠으면 까닭을 붙인다("약초 ×1 주웠습니다(남은 것이 모자라 남은 만큼만)") */
export function takeLine(take: Part<'take'>): string {
  if (take.taken <= 0) return `줍지 못했습니다${because(PLACE_REASONS, take.reason)}`;
  return `${take.name} ×${take.taken} 주웠습니다${because(PLACE_REASONS, take.reason)}`;
}

export function putDownLine(put: Part<'put_down'>): string {
  return put.put ? `${put.name} ×${put.count} 내려놓았습니다` : `내려놓지 못했습니다${because(PLACE_REASONS, put.reason)}`;
}

/** 덫을 놓은 것(#806). "올가미 숨겨 놓음(남은 1개)". 놓지 못했으면 까닭을 붙인다 */
export function trapSetLine(trap: Part<'trap_set'>): string {
  return trap.set ? `${trap.name} 숨겨 놓음(남은 ${trap.remaining}개)` : `덫을 놓지 못했습니다${because(ITEM_REASONS, trap.reason)}`;
}

/** 해제하지 못한 까닭(trap_actions.py 의 DisarmReason) */
const DISARM_REASONS: Record<string, string> = {
  gone: '앞사람이 거뒀거나 덫이 이미 터졌습니다',
  elsewhere: '그 덫이 있는 곳에 없었습니다',
};

/** 덫 해제(#806 ①-b). "올가미 거둠(판정 20 / 20)", "올가미 해제 실패 · 덫이 터짐 · 렌 HP 9 → 7" */
export function disarmLine(disarm: Part<'disarm'>): string {
  if (!disarm.check) return `해제하지 못했습니다${because(DISARM_REASONS, disarm.reason)}`;
  const roll = `판정 ${disarm.check.total} / ${disarm.check.target}`;
  if (disarm.done) return `${disarm.name} 거둠(${roll})${disarm.kept ? '' : ' · 더 가질 수 없어 그 자리에 둠'}`;
  const sprung = disarm.sprung ? ' · 덫이 터짐' : '';
  const hurt = disarm.effect ? ` · ${disarm.effect.character_name} HP ${disarm.effect.before} → ${disarm.effect.after}` : '';
  return `${disarm.name} 해제 실패(${roll})${sprung}${hurt}`;
}

/** 훔치기. 들켰으면 까닭 없이 "훔치지 못했습니다", 싸움이 붙었으면 그것도 적는다 */
export function stealLine(steal: Part<'steal'>): string {
  if (steal.stolen) return `${steal.name} 훔침${because(TAKE_FROM_REASONS, steal.reason)}`;
  if (steal.fight) return '훔치지 못했고 싸움이 붙었습니다';
  return `훔치지 못했습니다${because(TAKE_FROM_REASONS, steal.reason)}`;
}

export function lootLine(loot: Part<'loot'>): string {
  if (!loot.looted) return `가져오지 못했습니다${because(TAKE_FROM_REASONS, loot.reason)}`;
  return `${loot.name} ×${loot.count} 가져왔습니다${because(TAKE_FROM_REASONS, loot.reason)}`;
}

export function restLine(rest: Part<'rest'>): string {
  if (!rest.rested) return `쉬지 못했습니다${because(REST_REASONS, rest.reason)}`;
  return [`HP ${rest.before} → ${rest.after}`, ...shiftParts(rest.resources)].join(' · ');
}

export function waitLine(wait: Part<'wait'>): string {
  return wait.waited ? `${wait.minutes}분을 기다렸습니다` : `기다리지 못했습니다${because(WAIT_REASONS, wait.reason)}`;
}
