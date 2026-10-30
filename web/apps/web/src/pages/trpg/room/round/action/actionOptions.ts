// web/apps/web/src/pages/trpg/room/round/action/actionOptions.ts
// 선언에 붙일 행동의 고를 거리. 순수한 함수다. 무엇을 고를 수 있는지는 서버가 준 값(테이블, 내 시트, 장면)에서 정한다.
// 여기서 거르는 것은 안내다. 맞는지는 서버가 다시 본다(trpg-server/app/rounds/acceptance.py).
//
// 행동의 종류(app/engine/action.py)와 보이는 조건:
//   - 판정, 지목, 기다리기: 늘
//   - 치료: 규칙에 치료(rules.treatment)가 있을 때
//   - 쉬기: 규칙에 휴식(rules.rest)이 있을 때
//   - 물건 쓰기: 소모품을 지녔을 때. 던지기(#277): 던지는 판정이 있는 소모품을 지녔고 맞힐 대상(인물, 몬스터, 같은 곳의 동료)이 있을 때. 건네기: 물건을 지녔고 살아 있는 다른 사람이 있을 때. 내려놓기: 물건을 지녔고 맵에 서 있을 때.
//     덫 놓기(#806): 덫인 물건(판의 물건에 trap 이 있다)을 지녔고 맵에 서 있을 때. 덫 해제(#806 ①-b): 선 곳에 찾아낸 덫이 있을 때
//   - 가기: 아는 길이 있을 때. 찾기: 맵에 서 있을 때. 줍기: 선 곳에 보이게 놓인 물건이 있을 때
//   - 훔치기: 규칙에 훔치기(rules.steal)가 있고 물건을 지닌 산 대상이 있을 때. 빼앗기: 물건을 지닌 쓰러지거나 죽은 대상이 있을 때
//   - 사기, 팔기, 돈 건네기(#278): 화폐가 있는 판에서만. 사기는 파는 것이 있는 상인이 장면에 있을 때, 팔기는 상인이 사 주는 판이고
//     장면에 상인이 있고 값이 있는 물건을 지녔을 때, 돈 건네기는 돈이 있고 살아 있는 다른 사람이 있을 때.
//     상인은 장면의 인물 가운데 merchant 이고 살아 있고 적대하지 않는 이다(서버의 is_open)
//   - 열기, 잠그기, 따기, 부수기, 고치기, 자물쇠 바꾸기(#281): 내 장소에 닿은 길에 지금 그것을 할 수 있어 보이는 문이 있을 때(doorOptions.ts).
//     자물쇠 바꾸기는 자물쇠 물건도 지녀야 한다
// 캐릭터가 쓰러졌거나 죽었으면 행동을 붙이지 못한다(글만 낸다).
// 동료를 해치는 것(#803)은 테이블의 정도와 그 동료가 받아들인 정도 중 낮은 것이 끔이 아닐 때만 고를 거리에 넣는다(allyTargets).

import type { DeclaredAction, HeldItem, SceneCast, ScenePerson, TableDetail, TableMember } from '../../../../../api/types';
import { friendlyFireLabel, lowerFriendlyFire } from '../../../labels';
import { amountLabel, itemPrice, merchantsBuy, moneyOf } from '../../money';
import { injuryName, placeCover } from '../../status/statusView';
import { waysFrom, type Way } from '../../status/statusView';
import { doorsFor, isDoorKind, lockItems } from './doorOptions';

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
  'throw',
  'give',
  'move',
  'unlock',
  'lock',
  'pick',
  'force',
  'repair',
  'replace',
  'search',
  'take',
  'put_down',
  'set_trap',
  'disarm',
  'steal',
  'loot',
  'buy',
  'sell',
  'pay',
  'cover',
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
  if (kind === 'replace' && lockItems(ctx.table, ctx.me).length === 0) return false;
  if (isDoorKind(kind)) return doorsFor(kind, ctx.table.map, hereId(ctx)).length > 0;
  switch (kind) {
    case 'treat':
      return rules.treatment !== null;
    case 'rest':
      return rules.rest !== null;
    case 'use':
      return consumables(ctx.me).length > 0;
    case 'throw':
      return throwables(ctx).length > 0 && (harmTargets(ctx).length > 0 || membersHere(ctx).length > 0);
    case 'give':
      return heldItems(ctx.me).length > 0 && recipients(ctx).length > 0;
    case 'put_down':
      return heldItems(ctx.me).length > 0 && hereId(ctx) !== null;
    case 'set_trap':
      return trapItems(ctx).length > 0 && hereId(ctx) !== null;
    case 'disarm':
      return knownTraps(ctx).length > 0;
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
    case 'buy':
      return Boolean(ctx.table.currency) && merchants(ctx).some((choice) => merchantStock(ctx, choice.value).length > 0);
    case 'sell':
      return merchantsBuy(ctx.table) && merchants(ctx).length > 0 && sellableItems(ctx).length > 0;
    case 'pay':
      return Boolean(ctx.table.currency) && moneyOf(ctx.me) > 0 && recipients(ctx).length > 0;
    case 'cover':
      return coverHere(ctx) > 0;
    default:
      return true;
  }
}

/** 내가 선 장소. 맵이 없거나 맵에 서 있지 않으면 null */
export function hereId(ctx: ActionContext): string | null {
  return ctx.table.map && ctx.me.sheet?.place_id ? ctx.me.sheet.place_id : null;
}

/**
 * 엄폐할 수 있는 커버(#276). 세이브 방식의 판에서 내가 선 장소의 커버. 엄폐할 수 없으면 0
 * (서버의 app/rounds/covers.py 의 accept_cover 와 같은 조건)
 */
export function coverHere(ctx: ActionContext): number {
  return placeCover(ctx.table, hereId(ctx));
}

export function heldItems(me: TableMember): HeldItem[] {
  return me.sheet?.items ?? [];
}

/** 놓을 수 있는 덫(#806). 지닌 것 가운데 판의 물건에 덫(trap)이 적힌 것 */
export function trapItems(ctx: ActionContext): HeldItem[] {
  return heldItems(ctx.me).filter((held) => ctx.table.items.some((item) => item.entry_id === held.entry_id && item.trap));
}

export function consumables(me: TableMember): HeldItem[] {
  return heldItems(me).filter((item) => item.kind === 'consumable');
}

type AidAct = TableDetail['items'][number]['aids'][number]['act'];

/** 그 행동(치료, 따기, 고치기, 부수기, 넘기)에 붙여 쓸 수 있는 물건(#277, #802). 지닌 것 가운데 그 행동을 거드는 것 */
export function aidItems(ctx: ActionContext, act: AidAct): Choice[] {
  return heldItems(ctx.me).flatMap((held) => {
    const aid = ctx.table.items.find((item) => item.entry_id === held.entry_id)?.aids.find((one) => one.act === act);
    if (!aid) return [];
    const bonus = aid.bonus ? ` +${aid.bonus}` : '';
    const wear = aid.wear === 'always' ? ', 쓰면 없어짐' : aid.wear === 'on_fail' ? ', 실패하면 부러짐' : '';
    return [{ value: held.entry_id, label: `${held.name}${bonus} ×${held.count}${wear}` }];
  });
}

/** 던질 수 있는 물건(#277, #801). 지닌 것 가운데 던지는 판정(throw)이 있는 것. 룰북에 맞히는 판정이 있으면 모두 */
export function throwables(ctx: ActionContext): HeldItem[] {
  if (ctx.table.rules.item_check) return heldItems(ctx.me);
  return heldItems(ctx.me).filter((held) => ctx.table.items.some((item) => item.entry_id === held.entry_id && item.throw));
}

function effectsOf(table: TableDetail, entryId: string) {
  return table.items.find((item) => item.entry_id === entryId)?.effects ?? [];
}

/** 이 물건이 누군가에게 드는 소모품인가(판의 물건에 효과가 있다, #800). 효과가 없으면 대상이 없다 */
export function itemTakesTarget(table: TableDetail, entryId: string): boolean {
  return effectsOf(table, entryId).length > 0;
}

/**
 * 이 물건이 해로운가(피해나 부상, 수치를 내리는 맞추기, #804). 해로우면 동료에게는 동료 피해의 설정을 따른다(#803, allyTargets)
 */
export function itemHarms(table: TableDetail, entryId: string): boolean {
  return effectsOf(table, entryId).some(
    (effect) => effect.kind === 'damage' || effect.kind === 'injure' || (effect.kind === 'adjust' && effect.amount < 0),
  );
}

/** 이 물건이 피해를 주는가. 그때만 인물이나 몬스터를 죽이려 할 수 있다 */
export function itemDamages(table: TableDetail, entryId: string): boolean {
  return effectsOf(table, entryId).some((effect) => effect.kind === 'damage');
}

/**
 * 물건을 쓸 쪽(#800). 나는 빈 값이다. 해롭지 않으면 다른 사람, 해로우면 해칠 수 있는 동료(#803),
 * 규칙에 맞히는 판정(item_check)이 있으면 장면의 산 인물과 내가 선 곳의 산 몬스터도 고른다.
 * 인물과 몬스터에게는 맞히는 판정을 거친다.
 */
export function useTargets(ctx: ActionContext, entryId: string): Choice[] {
  const members = itemHarms(ctx.table, entryId) ? allyTargets(ctx) : recipients(ctx);
  return ctx.table.rules.item_check ? [...members, ...harmTargets(ctx)] : members;
}

/**
 * 물건을 던질 쪽(#801, #803). 장면의 인물, 내가 선 곳의 몬스터, 같은 곳의 동료다.
 * 해로운 물건이면 동료는 해칠 수 있는 이만(allyTargets), 이로운 물건(물약)이면 같은 곳의 산 동료 모두다.
 */
export function throwTargets(ctx: ActionContext, entryId: string): Choice[] {
  const members = entryId && itemHarms(ctx.table, entryId) ? allyTargets(ctx) : membersHere(ctx);
  return [...harmTargets(ctx), ...members];
}

/** 나와 같은 곳에 선 산 다른 사람(쓰러졌어도 된다). 맵이 없는 판이면 모두 같은 곳이다 */
function membersHere(ctx: ActionContext): Choice[] {
  const here = ctx.me.sheet?.place_id ?? null;
  return aliveMembers(ctx.table)
    .filter((member) => member.user_id !== ctx.me.user_id && (member.sheet?.place_id ?? null) === here)
    .map((member) => ({ value: `member:${member.user_id}`, label: member.character?.name ?? '' }));
}

/**
 * 해칠 수 있는 동료(#803). 같은 곳에 선, 쓰러지지 않은 산 다른 사람 가운데 테이블의 정도와 그 사람이 받아들인 정도 중
 * 낮은 것이 끔이 아닌 이다. "영애(동료, 장난만)". 맞는지는 서버가 받을 때와 라운드를 닫을 때 다시 본다
 */
export function allyTargets(ctx: ActionContext): Choice[] {
  const here = ctx.me.sheet?.place_id ?? null;
  return aliveMembers(ctx.table).flatMap((member) => {
    const level = lowerFriendlyFire(ctx.table.friendly_fire, member.friendly_fire);
    const reachable = member.user_id !== ctx.me.user_id && (member.sheet?.place_id ?? null) === here;
    if (!reachable || level === 'off' || (member.sheet?.hp ?? 0) <= 0) return [];
    return [{ value: `member:${member.user_id}`, label: `${member.character?.name ?? ''}(동료, ${friendlyFireLabel(level)})` }];
  });
}

/** 그 쪽에게 하는 것이 동료의 장난인가(#803). 동료가 아니거나 다 됨이면 아니다 */
export function isPrankToward(ctx: ActionContext, target: TargetRef): boolean {
  const [kind, id] = splitRef(target);
  const member = kind === 'member' ? ctx.table.members.find((entry) => entry.user_id === id) : undefined;
  return member !== undefined && lowerFriendlyFire(ctx.table.friendly_fire, member.friendly_fire) === 'prank';
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

/** 타격할 대상. 장면의 죽지 않은 인물과 내가 선 곳의 죽지 않은 몬스터. 몬스터는 몸 상태와 입은 부상을 붙인다(#799) */
export function harmTargets(ctx: ActionContext): Choice[] {
  const people = livingPeople(ctx).map((person) => ({ value: `npc:${person.id}`, label: person.name }));
  const monsters = monstersHere(ctx)
    .filter((monster) => monster.status !== 'dead')
    .map((monster) => {
      const state = [monster.condition, ...monster.injuries.map((key) => injuryName(ctx.table.rules, key))].join(' · ');
      return { value: `monster:${monster.id}`, label: `${monster.name}(${state})` };
    });
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

/**
 * 노려 칠 수 있는 부상(규칙의 aimable). 노려 치기는 인물과 몬스터와 동료(#803)에게 한다(#799).
 * 동료의 장난이면 짧은 것(rounds)만이다. 장난은 오래 가는 부상과 결손을 입히지 않는다
 */
export function aimableInjuries(ctx: ActionContext, prank = false): Choice[] {
  return ctx.table.rules.injuries
    .filter((injury) => injury.aimable && (!prank || injury.healing === 'rounds'))
    .map((injury) => ({ value: injury.key, label: injury.name }));
}

/** 타격에 쓸 무기. 내가 착용한 것 가운데 공격 보정이 있는 것. "장검(+2)", 관통력이 있으면 "볼터(+1, 관통 2)" (#276) */
export function myWeapons(ctx: ActionContext): Choice[] {
  return (ctx.me.sheet?.worn ?? []).flatMap((worn) => {
    const item = ctx.table.items.find((one) => one.entry_id === worn.entry_id);
    if (!item?.attack) return [];
    const pierce = item.ap ? `, 관통 ${item.ap}` : '';
    return [{ value: worn.entry_id, label: `${worn.name}(+${item.attack}${pierce})` }];
  });
}

/** 노릴 부위. 방어 방식과 노려 치기가 있는 규칙에서, 맞을 수 있는 칸(hit_weight 1 이상) (#276, 서버의 armor.can_strike) */
export function strikeSlots(ctx: ActionContext): Choice[] {
  const rules = ctx.table.rules;
  if (!rules.armor || !rules.called_shot) return [];
  return rules.equipment_slots.filter((slot) => slot.hit_weight > 0).map((slot) => ({ value: slot.key, label: slot.name }));
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

/** 그곳으로 가는 길에 넘기 판정이 있는가(#281). 있으면 넘기를 거드는 물건(#802)을 붙일 수 있다 */
export function climbs(ctx: ActionContext, place: string): boolean {
  return ways(ctx).some((way) => way.placeId === place && way.route.cross != null);
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
/** 내가 선 곳의 찾아낸 덫들(#806 ①-b). 해제할 수 있는 것 */
export function knownTraps(ctx: ActionContext) {
  const here = hereId(ctx);
  return ctx.table.map?.places.find((place) => place.entry_id === here)?.traps ?? [];
}

/** 맵에 보이는 찾아낸 덫의 이름. 맵에서 사라졌으면(거뒀거나 터졌다) null */
export function knownTrapName(table: TableDetail, trapId: string): string | null {
  for (const place of table.map?.places ?? []) {
    // 덫 찾기 전(#806 ①-b)의 응답에는 칸이 없다
    const found = (place.traps ?? []).find((trap) => trap.trap_id === trapId);
    if (found) return found.name;
  }
  return null;
}

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

/** 지금 거래하는 상인. 장면의 인물 가운데 상인이고 살아 있고 적대하지 않는 이(서버의 is_open) */
export function openMerchants(cast: SceneCast | null | undefined): ScenePerson[] {
  return (cast?.people ?? []).filter((person) => person.merchant && person.status === 'alive' && person.attitude !== 'hostile');
}

/** 거래할 상인의 고를 거리. 값은 "npc:<id>" */
export function merchants(ctx: ActionContext): Choice[] {
  return openMerchants(ctx.cast).map((person) => ({ value: `npc:${person.id}`, label: person.name }));
}

type Stock = ScenePerson['items'][number] & { price: number };

/** 상인이 파는 것. 소지품(장비가 아닌 것) 가운데 값이 있는 것 */
export function merchantStock(ctx: ActionContext, merchant: TargetRef): Stock[] {
  const [, id] = splitRef(merchant);
  const person = ctx.cast?.people.find((entry) => entry.id === id);
  return (person?.items ?? []).filter((item): item is Stock => !item.equipped && typeof item.price === 'number');
}

/** 살 물건의 고를 거리. "횃불 ×3 · 5닢" */
export function stockChoices(ctx: ActionContext, merchant: TargetRef): Choice[] {
  return merchantStock(ctx, merchant).map((item) => ({
    value: item.entry_id,
    label: `${item.name} ×${item.count} · ${amountLabel(ctx.table.currency, item.price)}`,
  }));
}

/** 상인의 그 물건 재고 */
export function stockCount(ctx: ActionContext, merchant: TargetRef, entryId: string): number {
  return merchantStock(ctx, merchant).find((item) => item.entry_id === entryId)?.count ?? 0;
}

/** 상인이 파는 그 물건의 값. 없으면 null */
export function stockPrice(ctx: ActionContext, merchant: TargetRef, entryId: string): number | null {
  return merchantStock(ctx, merchant).find((item) => item.entry_id === entryId)?.price ?? null;
}

/** 팔 수 있는 내 물건. 판의 물건에 값이 있는 것 */
export function sellableItems(ctx: ActionContext): HeldItem[] {
  return heldItems(ctx.me).filter((item) => itemPrice(ctx.table, item.entry_id) !== null);
}

/** "npc:abc" → ["npc", "abc"]. 빈 값이면 ["", ""] */
export function splitRef(ref: TargetRef): [string, string] {
  const index = ref.indexOf(':');
  return index < 0 ? ['', ''] : [ref.slice(0, index), ref.slice(index + 1)];
}
