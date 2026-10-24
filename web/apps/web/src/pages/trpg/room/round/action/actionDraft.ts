// web/apps/web/src/pages/trpg/room/round/action/actionDraft.ts
// 선언에 붙일 행동의 입력. 순수한 함수다. 종류마다 칸이 다르지만 입력은 한 모양으로 들고, 보낼 때 종류에 맞게 고른다.
// 종류를 바꿔도 다른 종류의 칸은 지우지 않는다(되돌아오면 그대로다). 보내는 값에는 그 종류의 칸만 들어간다.
// 칸의 규칙은 서버의 것이다(trpg-server/app/engine/action.py). 여기서 막는 것은 보내기 전에 알리는 것이다.

import type { DeclaredAction, Ruleset } from '../../../../../api/types';
import { amountLabel, buyingCost, moneyOf } from '../../money';
import { chosenDevice, doorDevices, doorsHere } from './doorOptions';
import {
  heldCount,
  itemHeals,
  placeItems,
  splitRef,
  stockCount,
  stockPrice,
  type ActionContext,
  type ActionKind,
  type TargetRef,
} from './actionOptions';

/** 지목하는 이름의 길이(NAME_GUESS_MAX_LENGTH) */
export const NAME_GUESS_MAX = 50;
/** 한 번에 건네거나 줍거나 내려놓는 개수(GIVE_MAX_COUNT) */
export const COUNT_MAX = 99;
/** 기다리기의 가장 긴 시간(분). 일주일 */
export const WAIT_MAX_MINUTES = 7 * 24 * 60;
/** 한 번에 건네는 돈(PAY_MAX_AMOUNT) */
export const PAY_MAX_AMOUNT = 1_000_000;

/** 판정의 목적. 그냥 판정, 타격(인물이나 몬스터), 회복(사람이나 인물) */
export type CheckPurpose = 'plain' | 'harm' | 'recover';

export type ActionDraft = {
  /** none 이면 행동이 없는 선언이다 */
  kind: ActionKind | 'none';
  ability: string;
  difficulty: string;
  /** 실패의 대가(피해 등급). 빈 값이면 없다 */
  risk: string;
  purpose: CheckPurpose;
  /** 타격이나 회복의 등급 */
  magnitude: string;
  /** 판정, 치료, 물건 쓰기, 건네기, 훔치기, 빼앗기의 대상 */
  target: TargetRef;
  lethal: boolean;
  /** 노려 칠 부상. 빈 값이면 노리지 않는다 */
  aim: string;
  /** 타격에 쓰는 무기(착용한 물건, #276). 빈 값이면 쓰지 않는다 */
  weapon: string;
  /** 노릴 부위(장비의 칸, #276). 빈 값이면 서버가 굴린다. 부상을 노리는 것(aim)과 함께 고르지 않는다 */
  strike: string;
  injury: string;
  guess: string;
  /** 지목할 인물. 빈 값이면 "이런 이름의 인물이 있다" */
  npc: string;
  item: string;
  count: number;
  place: string;
  /** 잠그기와 열기의 장치(lock, bar). 빈 값이면 그 문에서 할 수 있는 것의 첫째 */
  device: string;
  /** 함께 업고 갈 사람의 user_id. 빈 값이면 혼자 */
  carry: string;
  length: 'short' | 'long';
  minutes: number;
  /** 건넬 돈 */
  amount: number;
};

export function emptyActionDraft(rules: Ruleset): ActionDraft {
  return {
    kind: 'none',
    ability: rules.abilities[0]?.key ?? '',
    difficulty: rules.default_difficulty,
    risk: '',
    purpose: 'plain',
    magnitude: rules.magnitudes[0]?.key ?? '',
    target: '',
    lethal: false,
    aim: '',
    weapon: '',
    strike: '',
    injury: '',
    guess: '',
    npc: '',
    item: '',
    count: 1,
    place: '',
    device: '',
    carry: '',
    length: 'short',
    minutes: 60,
    amount: 1,
  };
}

/** 낸 선언의 행동으로 입력을 채운다(고치기) */
export function draftFromAction(rules: Ruleset, action: DeclaredAction | null): ActionDraft {
  const base = emptyActionDraft(rules);
  if (!action) return base;
  switch (action.kind) {
    case 'check':
      return { ...base, ...checkDraft(action), kind: 'check' };
    case 'treat':
      return { ...base, kind: 'treat', injury: action.injury, target: refOf(action.target, action.npc, null) };
    case 'name':
      return { ...base, kind: 'name', guess: action.name, npc: action.npc ?? '' };
    case 'use':
      return { ...base, kind: 'use', item: action.item, target: refOf(action.target, null, null) };
    case 'give':
      return { ...base, kind: 'give', item: action.item, count: action.count, target: `member:${action.target}` };
    case 'move':
      return { ...base, kind: 'move', place: action.place, carry: action.carry ?? '' };
    case 'take':
    case 'put_down':
      return { ...base, kind: action.kind, item: action.item, count: action.count };
    case 'steal':
    case 'loot':
      return { ...base, kind: action.kind, item: action.item, target: refOf(null, action.npc, action.monster) };
    case 'rest':
      return { ...base, kind: 'rest', length: action.length };
    case 'wait':
      return { ...base, kind: 'wait', minutes: action.minutes };
    case 'buy':
    case 'sell':
      return { ...base, kind: action.kind, item: action.item, count: action.count, target: `npc:${action.npc}` };
    case 'pay':
      return { ...base, kind: 'pay', amount: action.amount, target: `member:${action.target}` };
    case 'lock':
    case 'unlock':
      return { ...base, kind: action.kind, place: action.place, device: action.device ?? '' };
    case 'pick':
    case 'force':
    case 'repair':
      return { ...base, kind: action.kind, place: action.place };
    case 'replace':
      return { ...base, kind: 'replace', place: action.place, item: action.item };
    default:
      return { ...base, kind: action.kind };
  }
}

function checkDraft(action: Extract<DeclaredAction, { kind: 'check' }>): Partial<ActionDraft> {
  const purpose: CheckPurpose = action.harm ? 'harm' : action.recover ? 'recover' : 'plain';
  const magnitude = action.harm ?? action.recover;
  return {
    ability: action.ability,
    ...(action.difficulty ? { difficulty: action.difficulty } : {}),
    ...(magnitude ? { magnitude } : {}),
    risk: action.risk ?? '',
    purpose,
    target: refOf(action.target, action.npc, action.monster),
    lethal: action.lethal,
    aim: action.aim ?? '',
    weapon: action.weapon ?? '',
    strike: action.strike ?? '',
  };
}

function refOf(member: string | null | undefined, npc: string | null | undefined, monster: string | null | undefined): TargetRef {
  if (member) return `member:${member}`;
  if (npc) return `npc:${npc}`;
  if (monster) return `monster:${monster}`;
  return '';
}

/** 보내기 전에 알릴 것 한 줄. 없으면 null */
export function actionHint(draft: ActionDraft, ctx: ActionContext): string | null {
  switch (draft.kind) {
    case 'none':
    case 'search':
    case 'cover':
      return null;
    case 'check':
      return checkHint(draft, ctx.table.rules);
    case 'treat':
      return draft.injury ? null : '치료할 부상을 골라 주세요.';
    case 'name':
      return nameHint(draft.guess);
    case 'use':
      return draft.item ? null : '쓸 물건을 골라 주세요.';
    case 'give':
      if (!draft.item || !draft.target) return '건넬 물건과 받을 사람을 골라 주세요.';
      return countHint(draft.count, heldCount(ctx.me, draft.item));
    case 'put_down':
      return draft.item ? countHint(draft.count, heldCount(ctx.me, draft.item)) : '내려놓을 물건을 골라 주세요.';
    case 'take':
      return draft.item ? countHint(draft.count, COUNT_MAX) : '주울 물건을 골라 주세요.';
    case 'move':
      return draft.place ? null : '갈 곳을 골라 주세요.';
    case 'steal':
    case 'loot':
      return draft.target && draft.item ? null : '대상과 물건을 골라 주세요.';
    case 'rest':
      return null;
    case 'wait':
      return Number.isInteger(draft.minutes) && draft.minutes >= 1 && draft.minutes <= WAIT_MAX_MINUTES
        ? null
        : `기다리는 시간은 1분에서 ${WAIT_MAX_MINUTES}분 사이입니다.`;
    case 'buy':
      return draft.target && draft.item ? buyHint(draft, ctx) : '상인과 물건을 골라 주세요.';
    case 'sell':
      return draft.target && draft.item ? countHint(draft.count, heldCount(ctx.me, draft.item)) : '상인과 물건을 골라 주세요.';
    case 'pay':
      return draft.target ? payHint(draft.amount, ctx) : '돈을 받을 사람을 골라 주세요.';
    case 'lock':
    case 'unlock':
    case 'pick':
    case 'force':
    case 'repair':
      return draft.place ? null : '다룰 문을 골라 주세요.';
    case 'replace':
      return draft.place && draft.item ? null : '다룰 문과 달 자물쇠를 골라 주세요.';
  }
}

/** 상인의 재고까지, 가진 돈으로 살 수 있는 만큼 */
function buyHint(draft: ActionDraft, ctx: ActionContext): string | null {
  const counted = countHint(draft.count, stockCount(ctx, draft.target, draft.item));
  if (counted) return counted;
  const price = stockPrice(ctx, draft.target, draft.item);
  const money = moneyOf(ctx.me);
  if (price === null || buyingCost(price, draft.count) <= money) return null;
  const currency = ctx.table.currency;
  return `돈이 모자랍니다(값 ${amountLabel(currency, buyingCost(price, draft.count))}, 가진 돈 ${amountLabel(currency, money)}).`;
}

/** 1 이상, 가진 돈까지 */
function payHint(amount: number, ctx: ActionContext): string | null {
  const money = moneyOf(ctx.me);
  if (!Number.isInteger(amount) || amount < 1 || amount > PAY_MAX_AMOUNT) return `건넬 돈은 1에서 ${PAY_MAX_AMOUNT} 사이입니다.`;
  return amount > money ? `가진 돈(${amountLabel(ctx.table.currency, money)})보다 많이 건넬 수 없습니다.` : null;
}

function checkHint(draft: ActionDraft, rules: Ruleset): string | null {
  const ability = rules.abilities.some((entry) => entry.key === draft.ability);
  const difficulty = rules.difficulties.some((entry) => entry.key === draft.difficulty);
  if (!ability || !difficulty) return '이 테이블의 규칙에 있는 능력과 난이도를 골라 주세요.';
  if (draft.purpose === 'harm' && !draft.target) return '칠 대상을 골라 주세요.';
  if (draft.purpose !== 'plain' && !draft.magnitude) return '피해나 회복의 크기를 골라 주세요.';
  if (draft.purpose === 'harm' && draft.strike && draft.aim) return '부위와 부상을 함께 노릴 수 없습니다. 하나만 골라 주세요.';
  return null;
}

function nameHint(guess: string): string | null {
  const trimmed = guess.trim();
  if (!trimmed) return '짚을 이름을 적어 주세요.';
  return trimmed.length > NAME_GUESS_MAX ? `이름은 ${NAME_GUESS_MAX}자까지입니다.` : null;
}

function countHint(count: number, max: number): string | null {
  if (!Number.isInteger(count) || count < 1) return '개수는 1 이상입니다.';
  if (count > Math.min(max, COUNT_MAX)) return `개수는 ${Math.min(max, COUNT_MAX)}개까지입니다.`;
  return null;
}

/** 서버에 보낼 행동. 행동이 없으면 null. 그 종류의 칸만 넣는다 */
export function toAction(draft: ActionDraft, ctx: ActionContext): DeclaredAction | null {
  const [targetKind, targetId] = splitRef(draft.target);
  const member = targetKind === 'member' ? targetId : null;
  const npc = targetKind === 'npc' ? targetId : null;
  const monster = targetKind === 'monster' ? targetId : null;
  switch (draft.kind) {
    case 'none':
      return null;
    case 'check':
      return toCheck(draft, member, npc, monster);
    case 'treat':
      return { kind: 'treat', injury: draft.injury, ...(member ? { target: member } : {}), ...(npc ? { npc } : {}) };
    case 'name':
      return { kind: 'name', name: draft.guess.trim(), ...(draft.npc ? { npc: draft.npc } : {}) };
    case 'use':
      return { kind: 'use', item: draft.item, ...(member && itemHeals(ctx.table, draft.item) ? { target: member } : {}) };
    case 'give':
      return { kind: 'give', item: draft.item, count: draft.count, target: member ?? '' };
    case 'move':
      return { kind: 'move', place: draft.place, ...(draft.carry ? { carry: draft.carry } : {}) };
    case 'search':
      return { kind: 'search' };
    case 'cover':
      return { kind: 'cover' };
    case 'take':
      return { kind: 'take', item: draft.item, count: Math.min(draft.count, placeCount(ctx, draft.item)) };
    case 'put_down':
      return { kind: 'put_down', item: draft.item, count: draft.count };
    case 'steal':
    case 'loot':
      return { kind: draft.kind, item: draft.item, ...(npc ? { npc } : {}), ...(monster ? { monster } : {}) };
    case 'rest':
      return { kind: 'rest', length: draft.length };
    case 'wait':
      return { kind: 'wait', minutes: draft.minutes };
    case 'buy':
    case 'sell':
      return { kind: draft.kind, npc: npc ?? '', item: draft.item, count: draft.count };
    case 'pay':
      return { kind: 'pay', target: member ?? '', amount: draft.amount };
    // 문을 다루는 행동(#281). 잠그기와 열기는 장치를 적어 보낸다(자물쇠와 빗장이 다 있는 길은 서버가 적으라고 한다)
    case 'lock':
    case 'unlock':
      return toLockAction(draft.kind, draft, ctx);
    case 'pick':
    case 'force':
    case 'repair':
      return { kind: draft.kind, place: draft.place };
    case 'replace':
      return { kind: 'replace', place: draft.place, item: draft.item };
  }
}

/** 잠그기, 열기. 고른 장치가 지금 그 문에서 할 수 없으면 할 수 있는 것으로 바꾼다 */
function toLockAction(kind: 'lock' | 'unlock', draft: ActionDraft, ctx: ActionContext): DeclaredAction {
  const here = ctx.me.sheet?.place_id ?? '';
  const door = doorsHere(ctx.table.map, here).find((one) => one.place === draft.place);
  const device = chosenDevice(door ? doorDevices(kind, door.route, here) : [], draft.device);
  return { kind, place: draft.place, ...(device ? { device } : {}) };
}

/** 판정. 목적에 맞는 칸만 넣는다. 타격은 인물이나 몬스터, 회복은 사람이나 인물(비우면 자기 자신) */
function toCheck(draft: ActionDraft, member: string | null, npc: string | null, monster: string | null): DeclaredAction {
  const base = {
    kind: 'check' as const,
    ability: draft.ability,
    difficulty: draft.difficulty,
    ...(draft.risk ? { risk: draft.risk } : {}),
  };
  if (draft.purpose === 'harm') {
    // 노려 치기는 하나다. 부위를 노리면 부상은 노리지 않는다(서버도 둘을 함께 받지 않는다)
    const aim = npc && draft.aim && !draft.strike ? { aim: draft.aim } : {};
    const gear = { ...(draft.weapon ? { weapon: draft.weapon } : {}), ...(draft.strike ? { strike: draft.strike } : {}) };
    return { ...base, harm: draft.magnitude, lethal: draft.lethal, ...(npc ? { npc } : {}), ...(monster ? { monster } : {}), ...aim, ...gear };
  }
  if (draft.purpose === 'recover') {
    return { ...base, recover: draft.magnitude, lethal: false, ...(member ? { target: member } : {}), ...(npc ? { npc } : {}) };
  }
  return { ...base, lethal: false };
}

/** 줍는 개수는 놓인 것보다 많이 부르지 않는다(서버는 남은 만큼만 준다) */
function placeCount(ctx: ActionContext, entryId: string): number {
  return placeItems(ctx).find((item) => item.entry_id === entryId)?.count ?? COUNT_MAX;
}
