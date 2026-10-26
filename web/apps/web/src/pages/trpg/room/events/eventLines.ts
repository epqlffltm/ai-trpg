// web/apps/web/src/pages/trpg/room/events/eventLines.ts
// 일어난 일(이벤트) 하나를 한 줄 글로. 순수한 함수다. 종류마다 서버가 앉은 사람에게 보이는 칸만 싣는다
// (trpg-server/app/events/responses.py 의 VISIBLE). 그 칸만 읽고, 없으면 그 부분을 빼고 적는다.
//
// - 종류마다 하나씩 빠짐없이 적는다(DESCRIBE 가 EventType 의 모든 값을 갖는다. 서버에 종류가 늘면 타입 검사가 알린다)
// - 라운드의 기록(GM 의 서술, 선언, 판정)은 라운드 화면에 있어 여기서 뺀다(null)
// - 서술을 막거나 사람과 캐릭터를 잃는 일은 important 다. 기록에서 두드러지고, 일부는 방 위의 알림이 된다(roomNotices.ts)
// 글은 "누가: 무엇" 꼴이다. 이름 뒤의 조사를 고르지 않아도 되게.

import type { TableDetail, TableEvent } from '../../../../api/types';
import { NARRATION_STYLE_VALUES, attitudeLabel, durationLabel, narrationStyleLabel } from '../../labels';
import { dayLabel, stepName } from '../../models/modelChoice';
import { amountLabel } from '../money';
import { blowLine, type Blow } from '../round/roundView';
import { clockTimeLabel, injuryName, questStatusLabel } from '../status/statusView';

export type EventType = TableEvent['type'];
type Payload = Record<string, unknown>;

export type EventLine = { text: string; important: boolean };

export type EventContext = {
  /** 판의 규칙(부상과 칸의 이름)과 화폐. 떠난 테이블처럼 모르면 rules 가 null 이고 이름표를 그대로 적는다 */
  table: Pick<TableDetail, 'currency'> & { rules: TableDetail['rules'] | null };
  /** 사람(user_id)의 보일 이름. 캐릭터의 이름이 먼저다 */
  nameOfMember: (userId: string) => string;
  /** 서술 모델의 이름표를 보일 이름으로. 모르면 이름표 그대로 */
  modelName: (slug: string) => string;
};

type Describe = (payload: Payload, ctx: EventContext, event: TableEvent) => string | null;

// --- 칸 읽기. 서버가 싣지 않았거나 모양이 다르면 null ---

function text(payload: Payload, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' ? value : null;
}

function count(payload: Payload, key: string): number | null {
  const value = payload[key];
  return typeof value === 'number' ? value : null;
}

function flag(payload: Payload, key: string): boolean {
  return payload[key] === true;
}

function part(payload: Payload, key: string): Payload | null {
  const value = payload[key];
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Payload) : null;
}

function listSize(payload: Payload, key: string): number {
  const value = payload[key];
  return Array.isArray(value) ? value.length : 0;
}

// --- 칸을 글로 ---

/** 장소({entry_id, name})의 이름 */
function placeOf(payload: Payload, key: string): string | null {
  const place = part(payload, key);
  return place ? text(place, 'name') : null;
}

/** 캐릭터의 이름이 있으면 그것, 없으면 사람(user_id, 없으면 행한 사람)의 이름 */
function who(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const named = text(payload, 'character_name');
  if (named) return named;
  const userId = text(payload, 'user_id') ?? event.actor_id;
  return userId ? ctx.nameOfMember(userId) : '누군가';
}

/** 캐릭터 또는 인물. 인물이면 장면의 호칭(name) */
function subject(payload: Payload, ctx: EventContext, event: TableEvent): string {
  return text(payload, 'character_name') ?? text(payload, 'name') ?? who(payload, ctx, event);
}

function member(payload: Payload, ctx: EventContext, key = 'user_id'): string {
  const userId = text(payload, key);
  return userId ? ctx.nameOfMember(userId) : '누군가';
}

function model(payload: Payload, ctx: EventContext, key = 'narration_model'): string {
  const slug = text(payload, key);
  return slug ? ctx.modelName(slug) : '서버의 기본 모델';
}

function thing(payload: Payload): string {
  return `${text(payload, 'name') ?? '물건'} ×${count(payload, 'count') ?? '?'}`;
}

function roundOf(payload: Payload): string {
  return `라운드 ${count(payload, 'round') ?? '?'}`;
}

function onOff(value: boolean): string {
  return value ? '켬' : '끔';
}

function stepsText(payload: Payload): string {
  const input = count(payload, 'input_step');
  const output = count(payload, 'output_step');
  if (input === null || output === null) return '';
  return `(기억 ${stepName(input)} · 장면 ${stepName(output)})`;
}

function styleText(payload: Payload): string {
  const style = NARRATION_STYLE_VALUES.find((value) => value === text(payload, 'narration_style'));
  return style ? narrationStyleLabel(style) : '시나리오의 추천';
}

function questText(payload: Payload): string {
  const status = text(payload, 'status');
  const known = status === 'hidden' || status === 'active' || status === 'succeeded' || status === 'failed';
  return `퀘스트 「${text(payload, 'name') ?? ''}」: ${known ? questStatusLabel(status) : (status ?? '')}`;
}


/** 인물과 몬스터의 피해와 회복. HP 의 숫자는 보이지 않는다(서버가 싣지 않는다) */
function changeText(payload: Payload, fallback: string): string {
  const amount = count(payload, 'amount');
  const kind = text(payload, 'kind') === 'recovery' ? '회복' : '피해';
  const status = text(payload, 'status');
  const fate = status === 'dead' ? ' · 죽음' : status === 'downed' ? ' · 쓰러짐' : '';
  return `${text(payload, 'name') ?? fallback}: ${kind}${amount === null ? '' : ` ${amount}`}${fate}`;
}

/**
 * 몬스터와 인물의 공격. "고블린: 할퀴기 → 렌 맞힘", 장비가 들었으면 뒤에 괄호로 타격 줄(roundView 의 blowLine)
 * "고블린: 할퀴기 → 렌 맞힘 (몸 · 방어 5 · 아머 세이브 10 + 5 → 막음)"
 */
function attackText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const hit = flag(payload, 'success') ? '맞힘' : '빗나감';
  const blow = blowOf(payload);
  const gear = blow ? blowLine(blow) : null;
  return `${text(payload, 'name') ?? '누군가'}: ${attackName(payload)} → ${who(payload, ctx, event)} ${hit}${gear ? ` (${gear})` : ''}`;
}

/** 공격의 이름. 서버는 공격을 {name, ability, difficulty, harm} 로 싣는다. 글 하나로 와도 읽는다 */
function attackName(payload: Payload): string {
  const attack = part(payload, 'attack');
  return (attack ? text(attack, 'name') : text(payload, 'attack')) ?? '공격';
}

/** 공격에 장비가 든 것(blow). 타격 줄이 읽는 칸의 모양이 맞을 때만, 아니면 null(줄을 깨지 않는다) */
function blowOf(payload: Payload): Blow | null {
  const blow = part(payload, 'blow');
  if (!blow || typeof blow.aimed !== 'boolean' || typeof blow.defense !== 'number') return null;
  if (!nullOr(blow.mode, 'string') || !nullOr(blow.location_name, 'string')) return null;
  const weapon = part(blow, 'weapon');
  if (blow.weapon != null && (!weapon || text(weapon, 'name') === null || count(weapon, 'bonus') === null)) return null;
  const pierce = part(blow, 'pierce');
  if (blow.pierce != null && (!pierce || typeof pierce.pierced !== 'boolean')) return null;
  const save = part(blow, 'save');
  if (blow.save != null && (!save || !saveShaped(save))) return null;
  return blow as Blow;
}

function nullOr(value: unknown, type: 'string' | 'number'): boolean {
  return value == null || typeof value === type;
}

function saveShaped(save: Payload): boolean {
  return text(save, 'kind') !== null && count(save, 'roll') !== null && count(save, 'value') !== null && typeof save.saved === 'boolean';
}

/** 얻은 곳. 몬스터나 인물에게서, 장소에서 주움, 찾음 */
function gainedFrom(payload: Payload): string {
  const from = text(payload, 'monster_name') ?? text(payload, 'npc_name');
  if (from) return ` · ${from}에게서`;
  const place = placeOf(payload, 'place');
  if (text(payload, 'source') === 'search') return place ? ` · ${place}에서 찾음` : ' · 찾음';
  return place ? ` · ${place}에서` : '';
}

function injuryOf(payload: Payload, ctx: EventContext): string {
  const key = text(payload, 'injury') ?? '';
  return ctx.table.rules ? injuryName(ctx.table.rules, key) : key;
}

function roundOpenedText(payload: Payload): string {
  const clock = part(payload, 'clock');
  const day = clock ? count(clock, 'day') : null;
  const hour = clock ? count(clock, 'hour') : null;
  const minute = clock ? count(clock, 'minute') : null;
  const when = day !== null && hour !== null && minute !== null ? ` · ${clockTimeLabel({ day, hour, minute })}` : '';
  return `라운드 ${count(payload, 'number') ?? '?'}: 열림${when}`;
}

function searchedText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const ways = listSize(payload, 'found');
  const items = listSize(payload, 'items');
  const where = placeOf(payload, 'place') ?? '이곳';
  if (ways + items === 0) return `${who(payload, ctx, event)}: ${where}에서 찾은 것이 없습니다.`;
  return `${who(payload, ctx, event)}: ${where}에서 길 ${ways}개, 물건 ${items}가지를 찾았습니다.`;
}

function stealText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const from = text(payload, 'monster_name') ?? text(payload, 'npc_name') ?? '대상';
  if (flag(payload, 'stolen')) return `${who(payload, ctx, event)}: ${from}에게서 ${text(payload, 'name') ?? '물건'} 훔침`;
  return `${who(payload, ctx, event)}: ${from}에게서 훔치지 못했습니다${flag(payload, 'fight') ? '. 싸움이 붙었습니다' : ''}.`;
}

function movedText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const carried = text(payload, 'carried_by');
  const by = carried ? `(업은 사람 ${ctx.nameOfMember(carried)})` : '';
  return `${who(payload, ctx, event)}: ${placeOf(payload, 'from') ?? '?'} → ${placeOf(payload, 'to') ?? '?'}${by}`;
}

/** 무작위 조우(#283). 길에서 만났는지 쉬는 중에 덮쳤는지 */
function wanderText(payload: Payload): string {
  const monster = part(payload, 'monster');
  const name = monster ? text(monster, 'name') : null;
  const how = text(payload, 'cause') === 'rest' ? '쉬는 중에 덮쳤습니다' : '나타났습니다';
  return `조우: ${placeOf(payload, 'place') ?? '?'} · ${name ?? '?'} ${count(payload, 'count') ?? '?'}마리가 ${how}`;
}

/** 문을 다룬 것(#281). 해낸 것만 이벤트로 온다 */
const DOOR_ACTS: Record<string, string> = {
  lock: '잠갔습니다',
  unlock: '열었습니다',
  pick: '땄습니다',
  force: '부쉈습니다',
  repair: '고쳤습니다',
  replace: '새것으로 바꿨습니다',
};

/** 무엇을 다뤘는지. 자물쇠 바꾸기는 문이 아니라 문의 자물쇠다 */
function doorObject(payload: Payload): string {
  if (text(payload, 'act') === 'replace') return '문의 자물쇠를';
  return text(payload, 'device') === 'bar' ? '빗장을' : '문을';
}

function doorText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const act = DOOR_ACTS[text(payload, 'act') ?? ''] ?? '다뤘습니다';
  return `${who(payload, ctx, event)}: ${placeOf(payload, 'from') ?? '?'} ↔ ${placeOf(payload, 'to') ?? '?'} ${doorObject(payload)} ${act}`;
}

function givenText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  if (!flag(payload, 'given')) return `${who(payload, ctx, event)}: 건네지 못했습니다.`;
  const target = part(payload, 'target');
  const to = target ? (text(target, 'character_name') ?? member(target, ctx)) : '누군가';
  return `${who(payload, ctx, event)}: ${thing(payload)} → ${to}`;
}

/** 치료에 붙여 쓴 물건(#277). " (의료 키트 +2)". 쓰지 않았거나 쓰지 못했으면 빈 글 */
function aidText(payload: Payload): string {
  const aid = part(payload, 'aid');
  if (!aid || !flag(aid, 'used')) return '';
  return ` (${aidUse(aid)})`;
}

/** 판정에 붙여 쓴 물건(#802, aid_used). "락픽 +2 씀, 부러짐", "밧줄 씀" */
function aidUsed(payload: Payload): string {
  const bonus = count(payload, 'bonus');
  return `${text(payload, 'name') ?? '물건'}${bonus ? ` +${bonus}` : ''} 씀${flag(payload, 'broken') ? ', 부러짐' : ''}`;
}

/** 붙여 쓴 물건(#802) 하나. "락픽 +2, 부러짐", "밧줄". 보정이 0 이면 숫자를 적지 않는다 */
function aidUse(aid: Payload): string {
  const bonus = count(aid, 'bonus');
  return `${text(aid, 'name') ?? '물건'}${bonus ? ` +${bonus}` : ''}${flag(aid, 'broken') ? ', 부러짐' : ''}`;
}

/** 물건을 던짐(#277). 맞았는지는 뒤의 판정과 변화의 줄이 적는다 */
function thrownText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const item = text(payload, 'name') ?? '물건';
  if (!flag(payload, 'thrown')) return `${who(payload, ctx, event)}: ${item} 던지지 못함`;
  const target = part(payload, 'target');
  return `${who(payload, ctx, event)}: ${item} 던짐 → ${(target && text(target, 'name')) ?? '누군가'}`;
}

/** 돈. 판의 화폐 단위를 붙인다("12닢"). 화폐가 없는 판이면 숫자만 */
function moneyOf(amount: number | null, ctx: EventContext): string {
  return amount === null ? '?' : amountLabel(ctx.table.currency, amount);
}

function tradeText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const buying = text(payload, 'side') !== 'sell';
  const merchant = text(payload, 'npc_name') ?? '상인';
  if (!flag(payload, 'traded')) return `${who(payload, ctx, event)}: ${buying ? '사지' : '팔지'} 못했습니다(${merchant}).`;
  const price = moneyOf(count(payload, 'price'), ctx);
  const left = moneyOf(count(payload, 'money'), ctx);
  return buying
    ? `${who(payload, ctx, event)}: ${thing(payload)} 삼 · ${merchant}에게 ${price}(남은 돈 ${left})`
    : `${who(payload, ctx, event)}: ${thing(payload)} 팖 · ${merchant}에게서 ${price}(가진 돈 ${left})`;
}

function paidText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  if (!flag(payload, 'paid')) return `${who(payload, ctx, event)}: 돈을 건네지 못했습니다.`;
  const target = part(payload, 'target');
  const to = target ? (text(target, 'character_name') ?? member(target, ctx)) : '누군가';
  return `${who(payload, ctx, event)}: ${moneyOf(count(payload, 'amount'), ctx)} → ${to}`;
}

/** 칸의 이름표들을 규칙의 이름으로("주손·보조손"). 규칙에 없는 이름표는 그대로 */
function slotsOf(payload: Payload, ctx: EventContext): string {
  const value = payload['slots'];
  const keys = Array.isArray(value) ? value.filter((key): key is string => typeof key === 'string') : [];
  const names = new Map((ctx.table.rules?.equipment_slots ?? []).map((slot) => [slot.key, slot.name]));
  return keys.map((key) => names.get(key) ?? key).join('·');
}

function equipmentText(payload: Payload, ctx: EventContext, event: TableEvent): string {
  const verb = text(payload, 'change') === 'take_off' ? '벗음' : '착용';
  return `${who(payload, ctx, event)}: ${text(payload, 'name') ?? '물건'} ${verb} (${slotsOf(payload, ctx)})`;
}

function creditsShortText(payload: Payload, ctx: EventContext): string {
  const what = text(payload, 'reason') === 'gold_required' ? '골드가' : '크레딧이';
  return `${member(payload, ctx)}: ${what} 모자라 서술하지 못합니다. 충전하거나, 방장이 그 사람을 내보내거나 모델을 바꾸면 서술합니다.`;
}

function retiringText(payload: Payload, ctx: EventContext): string {
  const day = text(payload, 'retires_on');
  return `서술 모델 ${model(payload, ctx)}: ${day ? `${dayLabel(day)}에 ` : ''}끝납니다(${count(payload, 'days_left') ?? '?'}일 남음).`;
}

const DESCRIBE: Record<EventType, Describe> = {
  // 사람과 테이블
  table_created: () => '테이블을 만들었습니다.',
  member_joined: (p, ctx, e) => `${who(p, ctx, e)}: 들어왔습니다.`,
  member_left: (p, ctx, e) => `${who(p, ctx, e)}: 나갔습니다.`,
  member_kicked: (p, ctx, e) => `${who(p, ctx, e)}: 방장이 내보냈습니다.`,
  host_changed: (p, ctx) => `${member(p, ctx)}: 방장이 되었습니다.`,
  member_dropped: (p, ctx, e) => `${who(p, ctx, e)}: 크레딧이 모자라 자리에서 빠졌습니다.`,
  abilities_rolled: (p, ctx, e) => {
    const scores = Array.isArray(p.scores) ? `(${p.scores.join(', ')})` : '';
    return `${who(p, ctx, e)}: 능력치를 굴렸습니다${scores}.`;
  },
  reroll_granted: (p, ctx) => `${member(p, ctx)}: 한 번 더 굴릴 수 있습니다.`,
  whisper_sent: (p, ctx, e) => `${who(p, ctx, e)} → ${text(p, 'recipient_character_name') ?? member(p, ctx, 'recipient_id')}: 쪽지`,
  table_started: () => '테이블을 시작했습니다.',
  table_ended: (p) => `테이블이 끝났습니다${text(p, 'by') === 'operator' ? '(운영자)' : ''}.`,

  // 방장의 설정
  narration_style_changed: (p) => `서술 문체: ${styleText(p)}`,
  round_time_limit_changed: (p) => `라운드 시간 제한: ${durationLabel(count(p, 'round_time_limit'))}`,
  narration_tier_changed: (p) => `서술 등급: ${text(p, 'narration_tier') ?? '?'}`,
  narration_model_changed: (p, ctx) => `서술 모델: ${model(p, ctx)}${stepsText(p)}`,
  credit_wait_changed: (p) =>
    `크레딧 기다림: ${durationLabel(count(p, 'credit_wait_seconds'))}${flag(p, 'remove_short_payers') ? ' 뒤 빼기' : ' · 빼지 않음'}`,
  whisper_notice_changed: (p) => `쪽지 알림: ${onOff(flag(p, 'whisper_notice'))}`,
  references_changed: (p) => `참고 자료: ${onOff(flag(p, 'references_enabled'))}`,
  ledger_drafts_changed: (p) => `장부 초안: ${onOff(flag(p, 'ledger_drafts'))}`,
  clock_step_changed: (p) => `라운드마다 흐르는 시간: ${count(p, 'next_step_minutes') ?? '?'}분`,

  // 라운드와 서술. 서술, 선언, 판정은 라운드 화면에 있다
  gm_narration: () => null,
  player_action: () => null,
  check_rolled: () => null,
  round_opened: (p) => roundOpenedText(p),
  round_closed: (p) => `라운드 ${count(p, 'number') ?? '?'}: 마감`,
  narration_failed: (p) => `${roundOf(p)}: 서술에 실패했습니다(${text(p, 'reason') ?? '까닭 모름'}).`,
  narration_abandoned: (p) => `${roundOf(p)}: ${count(p, 'failures') ?? '?'}번 실패해 서술을 그만두었습니다. 엔진의 결과로 이어 갑니다.`,
  narration_credits_short: (p, ctx) => creditsShortText(p, ctx),
  narration_credits_released: (p) => `${roundOf(p)}: 서술 값을 돌려주었습니다.`,
  narration_model_not_for_sale: (p, ctx) => `서술 모델 ${model(p, ctx)}: 지금 팔지 않아 서술하지 못합니다. 방장이 모델을 바꾸면 서술합니다.`,
  narration_model_retiring: (p, ctx) => retiringText(p, ctx),
  narration_model_replaced: (p, ctx) => `서술 모델을 바꿨습니다: ${model(p, ctx, 'from')} → ${model(p, ctx)}(앞의 모델이 끝남)`,
  narration_model_unavailable: (p, ctx) => `서술 모델 ${model(p, ctx)}: 쓸 수 없습니다. 방장이 모델을 고를 때까지 서술하지 못합니다.`,
  happening_occurred: (p) => `일어난 일: ${text(p, 'name') ?? '?'}`,
  monsters_appeared: (p) => wanderText(p),

  // 몸
  hp_changed: (p, ctx, e) =>
    `${who(p, ctx, e)}: HP ${count(p, 'before') ?? '?'} → ${count(p, 'after') ?? '?'}${flag(p, 'downed') ? ' · 쓰러짐' : ''}`,
  npc_changed: (p) => changeText(p, '인물'),
  monster_changed: (p) => changeText(p, '몬스터'),
  npc_attitude_changed: (p) => `${text(p, 'name') ?? '인물'}: 태도 ${attitudeLabel(text(p, 'attitude') ?? '') ?? '?'}`,
  monster_attacked: (p, ctx, e) => attackText(p, ctx, e),
  npc_attacked: (p, ctx, e) => attackText(p, ctx, e),
  injury_gained: (p, ctx, e) => `${subject(p, ctx, e)}: ${injuryOf(p, ctx)} 입음`,
  injury_ended: (p, ctx, e) => `${subject(p, ctx, e)}: ${injuryOf(p, ctx)} 풀림`,
  injury_treated: (p, ctx, e) => {
    if (flag(p, 'died')) return `${subject(p, ctx, e)}: ${injuryOf(p, ctx)} 치료에 실패해 죽었습니다.`;
    return `${subject(p, ctx, e)}: ${injuryOf(p, ctx)} ${flag(p, 'treated') ? '치료함' : '치료하지 못함'}${aidText(p)}`;
  },
  death_save_rolled: (p, ctx, e) =>
    `${who(p, ctx, e)}: 죽음의 굴림 ${count(p, 'roll') ?? '?'}(목표 ${count(p, 'target') ?? '?'}) ${flag(p, 'success') ? '성공' : '실패'}`,
  character_died: (p, ctx, e) => `${who(p, ctx, e)}: 죽었습니다.`,
  character_revived: (p, ctx, e) =>
    flag(p, 'success') ? `${who(p, ctx, e)}: 일어났습니다(HP ${count(p, 'hp') ?? '?'}).` : `${who(p, ctx, e)}: 일어나지 못했습니다.`,
  character_joined: (p, ctx, e) => `${who(p, ctx, e)}: 새 캐릭터로 들어왔습니다.`,
  character_rested: (p, ctx, e) =>
    flag(p, 'rested')
      ? `${who(p, ctx, e)}: 쉬었습니다(HP ${count(p, 'before') ?? '?'} → ${count(p, 'after') ?? '?'}).`
      : `${who(p, ctx, e)}: 쉬지 못했습니다.`,
  naming_resolved: (p, ctx, e) =>
    flag(p, 'correct') ? `${who(p, ctx, e)}: 맞혔습니다. ${text(p, 'name') ?? ''}` : `${who(p, ctx, e)}: "${text(p, 'guess') ?? ''}" 틀림`,

  // 물건, 퀘스트, 장소
  items_gained: (p, ctx, e) => `${who(p, ctx, e)}: ${thing(p)} 얻음(지금 ${count(p, 'total') ?? '?'})${gainedFrom(p)}`,
  items_lost: (p, ctx, e) => `${who(p, ctx, e)}: ${thing(p)} 잃음(남은 ${count(p, 'total') ?? '?'})`,
  item_used: (p, ctx, e) => `${who(p, ctx, e)}: ${text(p, 'name') ?? '물건'} ${flag(p, 'used') ? '씀' : '쓰지 못함'}`,
  item_given: (p, ctx, e) => givenText(p, ctx, e),
  item_thrown: (p, ctx, e) => thrownText(p, ctx, e),
  aid_used: (p, ctx, e) => `${who(p, ctx, e)}: ${aidUsed(p)}`,
  item_put_down: (p, ctx, e) => {
    if (!flag(p, 'put')) return `${who(p, ctx, e)}: 내려놓지 못했습니다.`;
    const place = placeOf(p, 'place');
    return `${who(p, ctx, e)}: ${thing(p)} 내려놓음${place ? `(${place})` : ''}`;
  },
  steal_attempted: (p, ctx, e) => stealText(p, ctx, e),
  item_traded: (p, ctx, e) => tradeText(p, ctx, e),
  money_paid: (p, ctx, e) => paidText(p, ctx, e),
  equipment_changed: (p, ctx, e) => equipmentText(p, ctx, e),
  quest_changed: (p) => questText(p),
  character_moved: (p, ctx, e) => movedText(p, ctx, e),
  place_searched: (p, ctx, e) => searchedText(p, ctx, e),
  door_changed: (p, ctx, e) => doorText(p, ctx, e),
};

/** 서술을 막거나 사람과 캐릭터를 잃는 일. 기록에서 두드러진다 */
export const IMPORTANT: ReadonlySet<EventType> = new Set<EventType>([
  'narration_credits_short',
  'narration_model_not_for_sale',
  'narration_model_unavailable',
  'narration_model_retiring',
  'narration_model_replaced',
  'narration_failed',
  'narration_abandoned',
  'member_dropped',
  'character_died',
]);

/** 이벤트 한 줄. 라운드 화면에 있는 것과 모르는 종류는 null */
export function eventLine(event: TableEvent, ctx: EventContext): EventLine | null {
  const describe = DESCRIBE[event.type] as Describe | undefined;
  if (!describe) return null;
  const line = describe(event.payload ?? {}, ctx, event);
  return line ? { text: line, important: IMPORTANT.has(event.type) } : null;
}

/** 그 이벤트가 속한 라운드. 라운드 밖의 일(모집, 설정)이면 null */
export function eventRound(event: TableEvent): number | null {
  const payload: Payload = event.payload ?? {};
  const own = count(payload, 'round');
  if (own !== null) return own;
  return event.type === 'round_opened' || event.type === 'round_closed' ? count(payload, 'number') : null;
}

export type EventRow = { event: TableEvent; line: EventLine };

/** 기록에 보일 줄. 글이 없는 것(라운드 화면에 있는 것)은 빼고, 최근 것이 위 */
export function eventRows(events: TableEvent[], ctx: EventContext): EventRow[] {
  const rows: EventRow[] = [];
  for (const event of events) {
    const line = eventLine(event, ctx);
    if (line) rows.push({ event, line });
  }
  return rows.reverse();
}
