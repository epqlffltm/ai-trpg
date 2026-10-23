// web/apps/web/src/pages/trpg/room/round/action/actionOptions.ts
// 선언에 붙일 행동의 고를 거리. 순수한 함수다. 무엇을 고를 수 있는지는 서버가 준 값(테이블, 내 시트, 장면)에서 정한다.
// 여기서 거르는 것은 안내다. 맞는지는 서버가 다시 본다(trpg-server/app/rounds/acceptance.py).
//
// 행동의 종류(app/engine/action.py)와 보이는 조건:
//   - 판정, 지목, 기다리기: 늘
//   - 치료: 규칙에 치료(rules.treatment)가 있을 때
//   - 쉬기: 규칙에 휴식(rules.rest)이 있을 때
//   - 물건 쓰기: 소모품을 지녔을 때. 건네기: 물건을 지녔고 살아 있는 다른 사람이 있을 때. 내려놓기: 물건을 지녔고 맵에 서 있을 때
//   - 가기: 아는 길이 있을 때. 찾기: 맵에 서 있을 때. 줍기: 선 곳에 보이게 놓인 물건이 있을 때
//   - 훔치기: 규칙에 훔치기(rules.steal)가 있고 물건을 지닌 산 대상이 있을 때. 빼앗기: 물건을 지닌 쓰러지거나 죽은 대상이 있을 때
// 캐릭터가 쓰러졌거나 죽었으면 행동을 붙이지 못한다(글만 낸다).

import type { DeclaredAction, HeldItem, SceneCast, TableDetail, TableMember } from '../../../../../api/types';
import { waysFrom, type Way } from '../../status/statusView';

export type ActionKind = DeclaredAction['kind'];

export type ActionContext = {
  table: TableDetail;
  me: TableMember;
  /** 장면의 인물과 몬스터. 아직 읽지 못했으면 null(그것이 필요한 행동은 고를 거리가 없다) */
  cast: SceneCast | null;
};

/** 고를 거리 하나. value 는 입력이 들고 있는 값, label 은 보이는 글 */
export type Choice = { value: string; label: string };

/** 대상의 표시. "member:<user_id>", "npc:<id>", "monster:<id>". 빈 글이면 자기 자신(또는 대상 없음) */
export type TargetRef = string;

const ACTION_ORDER: ActionKind[] = [
  'check',
  'treat',
  'name',
  'use',
  'give',
  'move',
  'search',
  'take',
  'put_down',
  'steal',
  'loot',
  'rest',
  'wait',
];

/** 행동을 붙일 수 있는 몸인가. 쓰러졌거나 죽었으면 글만 낸다 */
export function canAttachAction(me: TableMember): boolean {
  return Boolean(me.sheet && !me.sheet.dead && me.sheet.hp > 0);
}

/** 지금 고를 수 있는 행동의 종류. 위의 조건 차례로 */
export function availableKinds(ctx: ActionContext): ActionKind[] {
  if (!canAttachAction(ctx.me)) return [];
  return ACTION_ORDER.filter((kind) => kindAvailable(kind, ctx));
}

function kindAvailable(kind: ActionKind, ctx: ActionContext): boolean {
  const rules = ctx.table.rules;
  switch (kind) {
    case 'treat':
      return rules.treatment !== null;
    case 'rest':
      return rules.rest !== null;
    case 'use':
      return consumables(ctx.me).length > 0;
    case 'give':
      return heldItems(ctx.me).length > 0 && recipients(ctx).length > 0;
    case 'put_down':
      return heldItems(ctx.me).length > 0 && hereId(ctx) !== null;
    case 'move':
      return ways(ctx).length > 0;
    case 'search':
      return hereId(ctx) !== null;
    case 'take':
      return placeItems(ctx).length > 0;
    case 'steal':
      return rules.steal !== null && victims(ctx, 'steal').length > 0;
    case 'loot':
      return victims(ctx, 'loot').length > 0;
    default:
      return true;
  }
}

/** 내가 선 장소. 맵이 없거나 맵에 서 있지 않으면 null */
export function hereId(ctx: ActionContext): string | null {
  return ctx.table.map && ctx.me.sheet?.place_id ? ctx.me.sheet.place_id : null;
}

export function heldItems(me: TableMember): HeldItem[] {
  return me.sheet?.items ?? [];
}

export function consumables(me: TableMember): HeldItem[] {
  return heldItems(me).filter((item) => item.kind === 'consumable');
}

/** 이 물건이 회복하는 소모품인가(판의 물건에 heals 가 있다). 회복하지 않으면 대상이 없다 */
export function itemHeals(table: TableDetail, entryId: string): boolean {
  return Boolean(table.items.find((item) => item.entry_id === entryId)?.heals);
}

/** 내가 지닌 이 물건의 개수 */
export function heldCount(me: TableMember, entryId: string): number {
  return heldItems(me).find((item) => item.entry_id === entryId)?.count ?? 0;
}

function aliveMembers(table: TableDetail): TableMember[] {
  return table.members.filter((member) => member.sheet && !member.sheet.dead && member.character);
}

/** 물건을 받을 사람. 살아 있는 다른 사람 */
export function recipients(ctx: ActionContext): Choice[] {
  return aliveMembers(ctx.table)
    .filter((member) => member.user_id !== ctx.me.user_id)
    .map((member) => ({ value: `member:${member.user_id}`, label: member.character?.name ?? '' }));
}

/** 회복받을 사람(판정의 회복, 물건 쓰기). 나를 뺀 죽지 않은 사람. 나는 빈 값(자기 자신)으로 고른다 */
export function healTargets(ctx: ActionContext, withNpcs: boolean): Choice[] {
  const members = recipients(ctx);
  const npcs = withNpcs ? livingPeople(ctx).map((person) => ({ value: `npc:${person.id}`, label: person.name })) : [];
  return [...members, ...npcs];
}

function livingPeople(ctx: ActionContext) {
  return (ctx.cast?.people ?? []).filter((person) => person.status !== 'dead');
}

function monstersHere(ctx: ActionContext) {
  const here = hereId(ctx);
  return (ctx.cast?.monsters ?? []).filter((monster) => monster.place_id === here);
}

/** 타격할 대상. 장면의 죽지 않은 인물과 내가 선 곳의 죽지 않은 몬스터 */
export function harmTargets(ctx: ActionContext): Choice[] {
  const people = livingPeople(ctx).map((person) => ({ value: `npc:${person.id}`, label: person.name }));
  const monsters = monstersHere(ctx)
    .filter((monster) => monster.status !== 'dead')
    .map((monster) => ({ value: `monster:${monster.id}`, label: `${monster.name}(${monster.condition})` }));
  return [...people, ...monsters];
}

/** 치료받을 쪽. 나(빈 값), 죽지 않은 다른 사람, 장면의 죽지 않은 인물 */
export function patients(ctx: ActionContext): Choice[] {
  return [{ value: '', label: '나' }, ...healTargets(ctx, true)];
}

/** 그 쪽이 입은 치료할 수 있는 부상(오래 가는 것). 규칙의 healing 이 heals 인 것 */
export function treatableInjuries(ctx: ActionContext, patient: TargetRef): Choice[] {
  const keys = injuryKeysOf(ctx, patient);
  return ctx.table.rules.injuries
    .filter((injury) => injury.healing === 'heals' && keys.includes(injury.key))
    .map((injury) => ({ value: injury.key, label: injury.name }));
}

function injuryKeysOf(ctx: ActionContext, patient: TargetRef): string[] {
  const [kind, id] = splitRef(patient);
  if (kind === 'npc') return ctx.cast?.people.find((person) => person.id === id)?.injuries ?? [];
  const member = kind === 'member' ? ctx.table.members.find((entry) => entry.user_id === id) : ctx.me;
  return member?.sheet?.injuries.map((injury) => injury.injury) ?? [];
}

/** 노려 칠 수 있는 부상(규칙의 aimable). 노려 치기는 인물에게만 한다 */
export function aimableInjuries(ctx: ActionContext): Choice[] {
  return ctx.table.rules.injuries.filter((injury) => injury.aimable).map((injury) => ({ value: injury.key, label: injury.name }));
}

/** 피해와 회복의 등급. "가벼움(1d4)" */
export function magnitudes(ctx: ActionContext): Choice[] {
  return ctx.table.rules.magnitudes.map((entry) => ({ value: entry.key, label: `${entry.name}(${entry.count}d${entry.sides})` }));
}

/** 지목할 인물. 장면의 인물 중 진짜 이름이 아직 드러나지 않은 이 */
export function nameablePeople(ctx: ActionContext): Choice[] {
  return (ctx.cast?.people ?? [])
    .filter((person) => !person.named)
    .map((person) => ({ value: person.id, label: person.name }));
}

export function ways(ctx: ActionContext): Way[] {
  return ctx.table.map ? waysFrom(ctx.table.map, hereId(ctx)) : [];
}

/** 함께 업고 갈 수 있는 사람. 나와 같은 곳에 쓰러져 있는(죽지 않은) 다른 사람 */
export function carriable(ctx: ActionContext): Choice[] {
  const here = hereId(ctx);
  return ctx.table.members
    .filter((member) => member.user_id !== ctx.me.user_id && member.sheet?.place_id === here)
    .filter((member) => member.sheet && !member.sheet.dead && member.sheet.hp <= 0)
    .map((member) => ({ value: member.user_id, label: member.character?.name ?? '' }));
}

/** 내가 선 곳에 보이게 놓인 물건 */
export function placeItems(ctx: ActionContext) {
  const here = hereId(ctx);
  return ctx.table.map?.places.find((place) => place.entry_id === here)?.items ?? [];
}

/**
 * 훔치거나(steal) 빼앗을(loot) 대상. 물건을 지닌 것만.
 * 훔치기는 쓰러지지 않은 대상, 빼앗기는 쓰러졌거나 죽은 대상이다. 몬스터는 내가 선 곳의 마리만
 */
export function victims(ctx: ActionContext, kind: 'steal' | 'loot'): Choice[] {
  const wanted = (status: string) => (kind === 'steal' ? status === 'alive' : status !== 'alive');
  const people = (ctx.cast?.people ?? [])
    .filter((person) => wanted(person.status) && person.items.length > 0)
    .map((person) => ({ value: `npc:${person.id}`, label: person.name }));
  const monsters = monstersHere(ctx)
    .filter((monster) => wanted(monster.status) && monster.items.length > 0)
    .map((monster) => ({ value: `monster:${monster.id}`, label: monster.name }));
  return [...people, ...monsters];
}

/** 그 대상이 지닌 물건 */
export function victimItems(ctx: ActionContext, victim: TargetRef): Choice[] {
  const [kind, id] = splitRef(victim);
  const holder =
    kind === 'npc'
      ? ctx.cast?.people.find((person) => person.id === id)
      : ctx.cast?.monsters.find((monster) => monster.id === id);
  return (holder?.items ?? []).map((item) => ({
    value: item.entry_id,
    label: `${item.name} ×${item.count}${item.equipped ? '(장비)' : ''}`,
  }));
}

/** "npc:abc" → ["npc", "abc"]. 빈 값이면 ["", ""] */
export function splitRef(ref: TargetRef): [string, string] {
  const index = ref.indexOf(':');
  return index < 0 ? ['', ''] : [ref.slice(0, index), ref.slice(index + 1)];
}
