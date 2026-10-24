// web/apps/web/src/pages/trpg/room/round/roundView.ts
// 라운드를 화면에 보일 글로 바꾼다. 순수한 함수다. 값은 모두 서버가 준 것이다. 화면이 판정을 계산하지 않는다.
// 행동은 "종류 · 무엇을, 누구에게"로, 결과는 서버가 적어 준 것(눈, 합, 물건, 장소, 회복)을 한 줄로 적는다.

import type { Declaration, DeclaredAction, Round, Ruleset, TableDetail } from '../../../../api/types';
import { amountLabel, type Currency } from '../money';
import { ACTION_LABELS } from './action/actionLabels';

type Outcome = NonNullable<Declaration['outcome']>;

const ROUND_STATUS: Record<Round['status'], string> = {
  open: '선언을 받는 중',
  closing: '결과를 서술하는 중',
  closed: '끝난 라운드',
};

const FATES: Record<Round['death_saves'][number]['fate'], string> = {
  dying: '아직 위태롭다',
  stable: '고비를 넘겼다',
  dead: '죽었다',
};

export function roundStatusLabel(status: Round['status']): string {
  return ROUND_STATUS[status];
}

/** "판정 · 근력, 보통", "건네기 · 약초 ×2 → 미아", "가기 · 부엌". 이름을 찾지 못하면 종류만 */
export function actionLabel(action: DeclaredAction, table: TableDetail): string {
  const label = ACTION_LABELS[action.kind];
  const detail = actionDetail(action, table);
  return detail ? `${label} · ${detail}` : label;
}

function actionDetail(action: DeclaredAction, table: TableDetail): string | null {
  switch (action.kind) {
    case 'check':
      return checkDetail(action, table);
    case 'treat':
      return nameOfInjury(table.rules, action.injury);
    case 'name':
      return `"${action.name}"`;
    case 'use':
      return itemName(table, action.item);
    case 'give':
      return `${itemName(table, action.item)} ×${action.count} → ${memberName(table, action.target)}`;
    case 'take':
    case 'put_down':
      return `${itemName(table, action.item)} ×${action.count}`;
    case 'steal':
    case 'loot':
      return itemName(table, action.item);
    case 'move':
      return table.map?.places.find((place) => place.entry_id === action.place)?.name ?? null;
    case 'rest':
      return action.length === 'long' ? '길게' : '짧게';
    case 'wait':
      return `${action.minutes}분`;
    case 'buy':
    case 'sell':
      return `${itemName(table, action.item)} ×${action.count}`;
    case 'pay':
      return `${amountLabel(table.currency, action.amount)} → ${memberName(table, action.target)}`;
    default:
      return null;
  }
}

function checkDetail(action: Extract<DeclaredAction, { kind: 'check' }>, table: TableDetail): string {
  const rules = table.rules;
  const ability = rules.abilities.find((entry) => entry.key === action.ability)?.name ?? action.ability;
  const key = action.difficulty ?? rules.default_difficulty;
  const difficulty = rules.difficulties.find((entry) => entry.key === key)?.name ?? key;
  const purpose = action.harm ? (action.lethal ? ', 죽이려는 공격' : ', 공격') : action.recover ? ', 회복' : '';
  return `${ability}, ${difficulty}${purpose}${gearDetail(action, table)}`;
}

/** 타격의 무기와 노린 부위(#276). ", 장검, 몸을 노림" */
function gearDetail(action: Extract<DeclaredAction, { kind: 'check' }>, table: TableDetail): string {
  const weapon = action.weapon ? `, ${itemName(table, action.weapon)}` : '';
  const slot = action.strike ? (table.rules.equipment_slots.find((entry) => entry.key === action.strike)?.name ?? action.strike) : null;
  return `${weapon}${slot ? `, ${slot} 노림` : ''}`;
}

function itemName(table: TableDetail, entryId: string): string {
  return table.items.find((item) => item.entry_id === entryId)?.name ?? '물건';
}

function memberName(table: TableDetail, userId: string): string {
  return table.members.find((member) => member.user_id === userId)?.character?.name ?? '누군가';
}

function nameOfInjury(rules: Ruleset, key: string): string {
  return rules.injuries.find((injury) => injury.key === key)?.name ?? key;
}

/** 결과 한 줄. 결과가 없으면 null(열려 있는 라운드). 돈의 단위는 테이블의 화폐(없으면 숫자만) */
export function outcomeLine(outcome: Outcome | null, rules: Ruleset, currency: Currency | null = null): string | null {
  if (!outcome) return null;
  if ('turn_lost' in outcome) return '행동하지 못했습니다.';
  if ('target_gone' in outcome) return '대상이 이미 없어 행동하지 못했습니다.';
  if ('roll' in outcome && 'total' in outcome && 'success' in outcome) return checkLine(outcome, rules);
  return otherLine(outcome) ?? moneyLine(outcome, currency) ?? '결과는 일어난 일에 적힙니다.';
}

/** 사고팔지 못하거나 돈을 건네지 못한 까닭(trpg-server/app/rounds/trades.py 의 Reason) */
const TRADE_REASONS: Record<string, string> = {
  unavailable: '상인이 거래할 수 없었습니다',
  out_of_stock: '상인의 재고가 모자랐습니다',
  not_enough_money: '돈이 모자랐습니다',
  not_held: '그만큼 가지고 있지 않았습니다',
  full: '더 가질 수 없었습니다',
  too_much_money: '돈을 더 가질 수 없었습니다',
  target_gone: '받을 사람이 없었습니다',
};

function reasonText(reason: string | null | undefined, fallback: string): string {
  return `${(reason ? TRADE_REASONS[reason] : undefined) ?? fallback}.`;
}

/** 사기, 팔기, 돈 건네기의 결과(#278) */
function moneyLine(outcome: Outcome, currency: Currency | null): string | null {
  if ('trade' in outcome) {
    const trade = outcome.trade;
    const buying = trade.side !== 'sell';
    if (!trade.traded) return `${buying ? '사지' : '팔지'} 못했습니다: ${reasonText(trade.reason, '까닭을 모릅니다')}`;
    const what = `${trade.name} ×${trade.count}`;
    const price = amountLabel(currency, trade.price);
    const left = amountLabel(currency, trade.money);
    return buying ? `${what} 샀습니다(낸 돈 ${price}, 남은 돈 ${left})` : `${what} 팔았습니다(받은 돈 ${price}, 가진 돈 ${left})`;
  }
  if ('pay' in outcome) {
    const pay = outcome.pay;
    if (!pay.paid) return `건네지 못했습니다: ${reasonText(pay.reason, '까닭을 모릅니다')}`;
    return `${amountLabel(currency, pay.amount)} → ${pay.target.character_name ?? '누군가'}(남은 돈 ${amountLabel(currency, pay.remaining)})`;
  }
  return null;
}

type CheckResult = Extract<Outcome, { roll: number; total: number }>;

function checkLine(outcome: CheckResult, rules: Ruleset): string {
  const modifier = outcome.modifier >= 0 ? `+${outcome.modifier}` : String(outcome.modifier);
  const parts = [`눈 ${outcome.roll}, 보정 ${modifier}, 합 ${outcome.total} / 목표 ${outcome.target}`];
  if (outcome.hindrance?.disadvantage) parts.push('불리함');
  if (outcome.called_shot) parts.push('노려 치기');
  parts.push(outcome.success ? '성공' : '실패');
  return [...parts, ...checkEffects(outcome, rules)].join(' · ');
}

/** 판정이 바꾼 것. 사람의 HP, 인물과 몬스터의 피해나 회복, 치료, 떨어진 물건 */
function checkEffects(outcome: CheckResult, rules: Ruleset): string[] {
  const parts: string[] = [];
  if (outcome.effect) parts.push(`${outcome.effect.character_name} HP ${outcome.effect.before} → ${outcome.effect.after}`);
  const other = outcome.npc_effect ?? outcome.monster_effect;
  if (other) parts.push(`${other.name} ${other.kind === 'damage' ? '피해' : '회복'} ${other.amount}`);
  if (outcome.treatment) {
    const injury = nameOfInjury(rules, outcome.treatment.injury);
    parts.push(outcome.treatment.treated ? `${injury} 치료함` : `${injury} 치료하지 못함`);
  }
  if (outcome.drop && outcome.drop.items.length > 0) parts.push('떨어뜨린 물건이 있음');
  const blow = blowLine(outcome.blow);
  return blow ? [blow, ...parts] : parts;
}

/** 타격에 장비가 든 것(#276). 판정의 결과와 몬스터·인물의 공격 이벤트(eventLines.ts)가 같은 모양이다 */
export type Blow = NonNullable<CheckResult['blow']>;

/** 방어가 한 일(ac, reduce). 세이브는 세이브 줄이 따로 말한다 */
const ARMOR_EFFECTS: Record<string, string> = { ac: '목표값에 더함', reduce: '피해에서 뺌' };
const SAVE_KINDS: Record<string, string> = { armor: '아머', cover: '커버', ward: '불굴' };

/**
 * 타격에 장비가 든 것(#276). 없으면 null.
 * "장검 +2 · 몸(노림) · 방어 5(목표값에 더함)", "볼터 +1 · 몸 · 방어 5 · 관통 못 함 · 아머 세이브 10 + 5 → 막음"
 */
export function blowLine(blow: CheckResult['blow']): string | null {
  if (!blow) return null;
  const parts = [
    blow.weapon ? `${blow.weapon.name} +${blow.weapon.bonus}` : null,
    blow.location_name ? `${blow.location_name}${blow.aimed ? '(노림)' : ''}` : null,
    defensePart(blow),
    blow.pierce ? (blow.pierce.pierced ? '관통함' : '관통 못 함') : null,
    savePart(blow.save),
  ].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(' · ') : null;
}

/** 그 부위의 방어. 관통했거나 세이브 방식이면 방어가 목표값이나 피해를 바꾸지 않았으니 하는 일을 붙이지 않는다 */
function defensePart(blow: Blow): string | null {
  if (!blow.mode || blow.defense <= 0) return null;
  const effect = blow.pierce?.pierced ? undefined : ARMOR_EFFECTS[blow.mode];
  return effect ? `방어 ${blow.defense}(${effect})` : `방어 ${blow.defense}`;
}

/** 세이브 굴림. "아머 세이브 10 + 5 → 막음". 굴리지 않았으면 null */
function savePart(save: Blow['save']): string | null {
  if (!save) return null;
  const kind = SAVE_KINDS[save.kind] ?? save.kind;
  return `${kind} 세이브 ${save.roll} + ${save.value} → ${save.saved ? '막음' : '못 막음'}`;
}

/** 판정이 아닌 행동의 결과 */
function otherLine(outcome: Outcome): string | null {
  if ('naming' in outcome) return outcome.naming.correct ? `맞혔습니다: ${outcome.naming.name ?? outcome.naming.guess}` : '틀렸습니다.';
  if ('item_use' in outcome) return outcome.item_use.used ? `${outcome.item_use.name} 사용(남은 ${outcome.item_use.remaining}개)` : '쓰지 못했습니다.';
  if ('item_give' in outcome) {
    const give = outcome.item_give;
    return give.given ? `${give.name} ×${give.count} → ${give.target.character_name ?? '누군가'}` : '건네지 못했습니다.';
  }
  if ('move' in outcome) return outcome.move.moved ? `${outcome.move.to.name}에 닿았습니다.` : '가지 못했습니다.';
  if ('search' in outcome) return searchLine(outcome.search);
  if ('take' in outcome) return outcome.take.taken > 0 ? `${outcome.take.name} ×${outcome.take.taken} 주웠습니다.` : '줍지 못했습니다.';
  if ('put_down' in outcome) return outcome.put_down.put ? `${outcome.put_down.name} ×${outcome.put_down.count} 내려놓았습니다.` : '내려놓지 못했습니다.';
  if ('steal' in outcome) return outcome.steal.stolen ? `${outcome.steal.name} 훔침` : outcome.steal.fight ? '훔치지 못했고 싸움이 붙었습니다.' : '훔치지 못했습니다.';
  if ('loot' in outcome) return outcome.loot.looted ? `${outcome.loot.name} ×${outcome.loot.count} 가져왔습니다.` : '가져오지 못했습니다.';
  if ('rest' in outcome) return outcome.rest.rested ? `HP ${outcome.rest.before} → ${outcome.rest.after}` : '쉬지 못했습니다.';
  if ('wait' in outcome) return outcome.wait.waited ? `${outcome.wait.minutes}분을 기다렸습니다.` : '기다리지 못했습니다.';
  if ('cover' in outcome) return coverLine(outcome.cover);
  if ('door' in outcome) return doorLine(outcome.door);
  return null;
}

/** 문을 다룬 행동(#281)의 해낸 일과 못 한 일. 못 한 것은 이벤트로 오지 않아 여기에만 보인다 */
const DOOR_DONE: Record<string, [string, string]> = {
  lock: ['잠갔습니다', '잠그지 못했습니다'],
  unlock: ['열었습니다', '열지 못했습니다'],
  pick: ['땄습니다', '따지 못했습니다'],
  force: ['부쉈습니다', '부수지 못했습니다'],
  repair: ['고쳤습니다', '고치지 못했습니다'],
};

/** 문을 다루지 못한 까닭(trpg-server/app/rounds/door_actions.py 의 DoorReason) */
const DOOR_REASONS: Record<string, string> = {
  no_key: '열쇠가 없었습니다',
  wrong_side: '빗장의 반대쪽에 서 있었습니다',
  broken: '부서진 문이라 잠그지 못합니다',
  already: '이미 그렇게 되어 있었습니다',
  no_tool: '도구가 없었습니다',
  failed: '판정에 실패했습니다',
};

/** "종탑 쪽 빗장: 열었습니다", "종탑 쪽 문: 따지 못했습니다(판정에 실패했습니다) · 눈 8, 보정 +1, 합 9 / 목표 15" */
export function doorLine(door: Extract<Outcome, { door: unknown }>['door']): string {
  const thing = door.device === 'bar' ? '빗장' : door.device === 'lock' ? '자물쇠' : '문';
  const [done, failed] = DOOR_DONE[door.act] ?? ['다뤘습니다', '다루지 못했습니다'];
  const reason = door.reason ? (DOOR_REASONS[door.reason] ?? door.reason) : null;
  const result = door.done ? done : reason ? `${failed}(${reason})` : failed;
  const line = `${door.to.name} 쪽 ${thing}: ${result}`;
  if (!door.check) return line;
  const modifier = door.check.modifier >= 0 ? `+${door.check.modifier}` : String(door.check.modifier);
  return `${line} · 눈 ${door.check.roll}, 보정 ${modifier}, 합 ${door.check.total} / 목표 ${door.check.target}`;
}

/** 엄폐한 결과(#276). "엄폐: 무너진 담 · 커버 4". 막았는지는 맞은 공격의 타격 줄(커버 세이브)에 있다 */
function coverLine(cover: Extract<Outcome, { cover: unknown }>['cover']): string {
  if (cover.value <= 0) return '숨을 곳이 없어 엄폐하지 못했습니다.';
  return `엄폐: ${cover.place?.name ?? '이곳'} · 커버 ${cover.value}`;
}

function searchLine(search: Extract<Outcome, { search: unknown }>['search']): string {
  const found = [...search.found.map((route) => `${route.to_place.name} 쪽 길`), ...search.items.map((item) => `${item.name} ×${item.count}`)];
  return found.length > 0 ? `찾았습니다: ${found.join(', ')}` : '찾은 것이 없습니다.';
}

/** 죽음의 굴림 한 줄. "렌: 죽음의 굴림 12 / 10 성공 (성공 2, 실패 1) · 아직 위태롭다" */
export function deathSaveLine(save: Round['death_saves'][number]): string {
  const result = save.success ? '성공' : '실패';
  return `${save.character_name}: 죽음의 굴림 ${save.roll} / ${save.target} ${result} (성공 ${save.successes}, 실패 ${save.failures}) · ${FATES[save.fate]}`;
}

/** 지금 라운드를 뺀 최근의 라운드들. 오래된 것부터 */
export function pastRounds(recent: Round[], current: Round | undefined): Round[] {
  if (!current) return recent;
  return recent.filter((round) => round.number < current.number);
}

/** 내 선언. 선언을 받는 동안에도 내 것은 글이 보인다. 내지 않았으면 undefined */
export function myDeclaration(round: Round, myId: string | undefined): Declaration | undefined {
  return round.declarations.find((declaration) => declaration.user_id === myId && declaration.content !== null);
}

/** 마감까지 남은 초. 마감이 없으면 null, 지났으면 0 */
export function remainingSeconds(deadlineAt: string | null, now: number): number | null {
  if (!deadlineAt) return null;
  return Math.max(0, Math.ceil((Date.parse(deadlineAt) - now) / 1000));
}
