// web/apps/web/src/pages/trpg/room/round/mapOutcome.ts
// 맵의 행동의 결과 한 줄. 가기(지나며 연 문, 넘기 판정과 다친 것, 업기)와 문을 다루는 행동(#281). 순수한 함수다.
// 못 한 까닭은 서버의 이름(trpg-server/app/rounds/schemas.py 의 MoveOut, CarryOut, app/rounds/door_actions.py 의 DoorReason)을 글로 바꾼다.
// 못 한 것은 이벤트로 오지 않아 이 줄에만 보인다. 이름 뒤에는 조사를 붙이지 않는다("종탑 쪽 문: 열었습니다").

import type { Declaration } from '../../../../api/types';

type Outcome = NonNullable<Declaration['outcome']>;
type Move = Extract<Outcome, { move: unknown }>['move'];
type Door = Extract<Outcome, { door: unknown }>['door'];
type Roll = NonNullable<Move['cross']>;

/** 가지 못한 까닭 */
const MOVE_REASONS: Record<string, string> = {
  not_adjacent: '그사이 옮겨져 이어진 길이 없었습니다',
  locked: '잠겨 있었고 열쇠가 없었습니다',
  barred: '빗장이 반대쪽에 걸려 있었습니다',
  cross_failed: '넘지 못했습니다',
};

/** 업지 못한 까닭 */
const CARRY_REASONS: Record<string, string> = {
  not_moved: '가지 못했습니다',
  standing: '그사이 일어났습니다',
  dead: '그사이 죽었습니다',
  elsewhere: '같은 곳에 없었습니다',
};

/** 문을 다룬 행동의 해낸 일과 못 한 일 */
const DOOR_DONE: Record<string, [string, string]> = {
  lock: ['잠갔습니다', '잠그지 못했습니다'],
  unlock: ['열었습니다', '열지 못했습니다'],
  pick: ['땄습니다', '따지 못했습니다'],
  force: ['부쉈습니다', '부수지 못했습니다'],
  repair: ['고쳤습니다', '고치지 못했습니다'],
  replace: ['새 자물쇠로 바꿨습니다', '바꾸지 못했습니다'],
};

/** 문을 다루지 못한 까닭 */
const DOOR_REASONS: Record<string, string> = {
  no_key: '열쇠가 없었습니다',
  wrong_side: '빗장의 반대쪽에 서 있었습니다',
  broken: '문이 부서져 있었습니다',
  already: '이미 그렇게 되어 있었습니다',
  no_tool: '도구가 없었습니다',
  failed: '판정에 실패했습니다',
  no_pick: '앞 차례에 따지 못하는 자물쇠로 바뀌었습니다',
  locked: '자물쇠가 잠겨 있었습니다. 연 뒤에 바꿉니다',
  no_item: '달 자물쇠를 더 지니지 않았습니다',
  used: '이 테이블에서 이미 단 자물쇠입니다',
};

/** 까닭을 괄호로. 모르는 이름이면 그대로, 없으면 빈 글 */
function because(reasons: Record<string, string>, reason: string | null | undefined): string {
  return reason ? `(${reasons[reason] ?? reason})` : '';
}

/** 판의 판정 하나. "눈 8, 보정 +1, 합 9 / 목표 15" */
export function rollText(roll: Roll): string {
  const modifier = roll.modifier >= 0 ? `+${roll.modifier}` : String(roll.modifier);
  return `눈 ${roll.roll}, 보정 ${modifier}, 합 ${roll.total} / 목표 ${roll.target}`;
}

/** 업은 결과. 업으려 하지 않았으면 null */
function carryPart(carry: Move['carry']): string | null {
  if (!carry) return null;
  const who = carry.character_name ?? '떠난 사람';
  return carry.carried ? `${who} 업고 감` : `${who} 업지 못함${because(CARRY_REASONS, carry.reason)}`;
}

/**
 * 가기. "종탑에 닿았습니다 · 열쇠로 자물쇠를 엶 · 30분 걸림 · 렌 업고 감",
 * "가지 못했습니다(넘지 못했습니다) · 넘기 판정 눈 8, … 실패 · 렌 HP 7 → 4"
 */
export function moveLine(move: Move): string {
  const head = move.moved ? `${move.to.name}에 닿았습니다` : `가지 못했습니다${because(MOVE_REASONS, move.reason)}`;
  const parts = [
    head,
    move.unlocked ? '열쇠로 자물쇠를 엶' : null,
    move.unbarred ? '빗장을 풂' : null,
    move.cross ? `넘기 판정 ${rollText(move.cross)} · ${move.cross.success ? '성공' : '실패'}` : null,
    move.effect ? `${move.effect.character_name} HP ${move.effect.before} → ${move.effect.after}` : null,
    move.moved && move.travel_minutes ? `${move.travel_minutes}분 걸림` : null,
    carryPart(move.carry),
  ];
  return parts.filter((part): part is string => part !== null).join(' · ');
}

/** 문을 다룬 행동. "종탑 쪽 빗장: 열었습니다", "종탑 쪽 문: 따지 못했습니다(판정에 실패했습니다) · 눈 8, 보정 +1, 합 9 / 목표 15" */
export function doorLine(door: Door): string {
  const thing = door.act === 'replace' ? '자물쇠' : door.device === 'bar' ? '빗장' : door.device === 'lock' ? '자물쇠' : '문';
  const [done, failed] = DOOR_DONE[door.act] ?? ['다뤘습니다', '다루지 못했습니다'];
  const line = `${door.to.name} 쪽 ${thing}: ${door.done ? done : `${failed}${because(DOOR_REASONS, door.reason)}`}`;
  return door.check ? `${line} · ${rollText(door.check)}` : line;
}
