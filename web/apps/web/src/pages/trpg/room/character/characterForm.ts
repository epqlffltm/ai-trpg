// web/apps/web/src/pages/trpg/room/character/characterForm.ts
// 캐릭터 정하기(B5)의 입력과 검사. 화면을 그리지 않는 순수한 함수다.
//
// 맞는지는 서버가 다시 본다(trpg-server/app/tables/characters.py 의 accept_character). 여기는 보내기 전에 알리는 것이다.
//   - 이름: 프리젠이 아니면 1~50자(앞뒤 빈칸을 뺀다). 설명은 1000자까지
//   - 능력치(manual, point_buy, rolled): 규칙의 능력치를 빠짐없이, score_min~score_max 안
//   - point_buy: 값표에 있는 점수만, 값의 합이 총점 이하(다 쓰지 않아도 된다)
//   - rolled: 이 캐릭터를 위해 굴린 점수를 남김없이 한 번씩. 어느 능력치에 놓을지는 플레이어가 정한다
// 최대 HP 는 보내지 않는다. 시작할 때 서버가 구한다(기준값 + hp_ability 의 보정, 1 이상 상한 이하). 여기서는 어림만 보인다.

import type { AbilityRoll, CharacterMode, CharacterUpdate, Ruleset, TableDetail, TableMember } from '../../../../api/types';

export const NAME_MAX = 50;
export const DESCRIPTION_MAX = 1000;

type PointBuy = NonNullable<Ruleset['point_buy']>;
type PlayerMadeHp = NonNullable<TableDetail['player_made_hp']>;
type Scores = Record<string, number>;

const PLAYER_MADE: ReadonlySet<CharacterMode> = new Set(['manual', 'point_buy', 'rolled']);

export type CharacterDraft = {
  mode: CharacterMode;
  pregenIndex: number | null;
  name: string;
  description: string;
  /** 직접 적기의 점수. 비운 칸은 NaN 이다 */
  manual: Scores;
  /** 점수제로 산 점수 */
  bought: Scores;
  /** 주사위: 능력치마다 놓은 굴린 점수의 자리(roll.scores 의 번호) */
  slots: Record<string, number>;
  /** slots 가 몇 번째 굴림의 것인가(times_rolled). 다시 굴리면 놓은 것을 버린다 */
  slotsOf: number | null;
};

export type DraftField = 'name' | 'description' | 'pregen' | 'abilities';

/** 플레이어가 능력치를 정하는 방식인가(서버의 PLAYER_MADE_MODES) */
export function isPlayerMade(mode: CharacterMode): boolean {
  return PLAYER_MADE.has(mode);
}

/** 지금 정하는 캐릭터의 번호. 시트가 없으면(시작 전) 1 이다 */
export function nextCharacterNumber(member: TableMember): number {
  return member.sheet ? member.sheet.number + 1 : 1;
}

/** 지금 정하는 캐릭터를 위해 굴린 것. 지난 캐릭터를 위해 굴린 것은 쓰지 못한다 */
export function freshRoll(member: TableMember): AbilityRoll | null {
  const roll = member.roll;
  return roll && roll.character_number === nextCharacterNumber(member) ? roll : null;
}

/** 지금 굴릴 수 있는가. 이 캐릭터를 위해 아직 굴리지 않았거나, 방장이 "한 번 더"를 줬을 때다 */
export function mayRoll(member: TableMember): boolean {
  const roll = freshRoll(member);
  return roll === null || roll.reroll_granted;
}

/** 고를 수 있는 프리젠인가. 죽은 것은 아무도, 남이 가져간 것은 나만 못 고른다 */
export function pregenAvailable(pregen: TableDetail['pregens'][number], myId: string): boolean {
  return !pregen.dead && (pregen.taken_by === null || pregen.taken_by === myId);
}

/** 이 점수를 사는 값. 값표에 없으면 null */
export function costOf(pointBuy: PointBuy, score: number): number | null {
  return pointBuy.costs.find((entry) => entry.score === score)?.cost ?? null;
}

/** 이 점수들을 사는 값의 합. 살 수 없는 점수가 있으면 null */
export function pointsSpent(pointBuy: PointBuy, scores: Scores): number | null {
  let total = 0;
  for (const score of Object.values(scores)) {
    const cost = costOf(pointBuy, score);
    if (cost === null) return null;
    total += cost;
  }
  return total;
}

/** 값표의 점수들. 낮은 점수부터 */
export function purchasableScores(pointBuy: PointBuy): number[] {
  return pointBuy.costs.map((entry) => entry.score).sort((a, b) => a - b);
}

/** 놓은 자리로 점수를 만든다. 지금 굴림의 것이 아니거나 빈 능력치가 있으면 null */
export function placedScores(draft: CharacterDraft, rules: Ruleset, roll: AbilityRoll | null): Scores | null {
  if (!roll) return null;
  const slots = currentSlots(draft, roll);
  const scores: Scores = {};
  for (const ability of rules.abilities) {
    const slot = slots[ability.key];
    const score = slot === undefined ? undefined : roll.scores[slot];
    if (score === undefined) return null;
    scores[ability.key] = score;
  }
  // 굴린 점수의 수는 능력치의 수와 같다. 자리가 모두 다르면 남김없이 한 번씩 쓴 것이다
  const distinct = new Set(rules.abilities.map((ability) => slots[ability.key]));
  return distinct.size === roll.scores.length ? scores : null;
}

/** 지금 굴림에서 능력치마다 놓은 자리. 지난 굴림에 놓은 것은 없는 것으로 본다 */
export function currentSlots(draft: CharacterDraft, roll: AbilityRoll | null): Record<string, number> {
  return roll && draft.slotsOf === roll.times_rolled ? draft.slots : {};
}

/** 능력치 하나에 자리를 놓거나(slot) 뺀다(null). 바꿀 칸만 돌려준다 */
export function placeSlot(
  draft: CharacterDraft,
  roll: AbilityRoll,
  key: string,
  slot: number | null,
): Pick<CharacterDraft, 'slots' | 'slotsOf'> {
  const slots = { ...currentSlots(draft, roll) };
  if (slot === null) delete slots[key];
  else slots[key] = slot;
  return { slots, slotsOf: roll.times_rolled };
}

/** 다른 능력치가 이미 쓴 자리인가 */
export function slotTaken(slots: Record<string, number>, slot: number, exceptKey: string): boolean {
  return Object.entries(slots).some(([key, used]) => key !== exceptKey && used === slot);
}

/** 이 방식으로 보낼 능력치. 능력치를 적지 않는 방식이거나 아직 다 놓지 않았으면 null */
export function chosenAbilities(draft: CharacterDraft, rules: Ruleset, roll: AbilityRoll | null): Scores | null {
  switch (draft.mode) {
    case 'manual':
      return pick(rules, draft.manual);
    case 'point_buy':
      return pick(rules, draft.bought);
    case 'rolled':
      return placedScores(draft, rules, roll);
    default:
      return null;
  }
}

/** 규칙의 능력치만, 규칙의 차례로 */
function pick(rules: Ruleset, scores: Scores): Scores {
  return Object.fromEntries(rules.abilities.map((ability) => [ability.key, scores[ability.key] ?? Number.NaN]));
}

/** 최대 HP 의 어림(서버의 max_hp_for). 정할 값이 없으면 null */
export function maxHpPreview(rules: Ruleset, hp: PlayerMadeHp | null, scores: Scores | null): number | null {
  if (!hp || !scores) return null;
  const score = rules.hp_ability ? scores[rules.hp_ability] : undefined;
  if (rules.hp_ability && (score === undefined || !Number.isInteger(score))) return null;
  const bonus = score === undefined ? 0 : Math.floor((score - rules.modifier.base) / rules.modifier.step);
  return Math.max(1, Math.min(hp.cap, hp.base + bonus));
}

/** 보내기 전에 알릴 것. 칸마다 한 줄. 비어 있으면 보낼 수 있다 */
export function draftHints(
  draft: CharacterDraft,
  table: TableDetail,
  myId: string,
  roll: AbilityRoll | null,
): Partial<Record<DraftField, string>> {
  const hints: Partial<Record<DraftField, string>> = {};
  if (draft.mode === 'pregen') {
    const pregen = draft.pregenIndex === null ? undefined : table.pregens[draft.pregenIndex];
    if (!pregen || !pregenAvailable(pregen, myId)) hints.pregen = '프리젠을 골라 주세요.';
    return hints;
  }
  const name = nameHint(draft.name);
  if (name) hints.name = name;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `설명은 ${DESCRIPTION_MAX}자까지입니다.`;
  const abilities = abilityHint(draft, table.rules, roll);
  if (abilities) hints.abilities = abilities;
  return hints;
}

function nameHint(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return '이름을 적어 주세요.';
  if (trimmed.length > NAME_MAX) return `이름은 ${NAME_MAX}자까지입니다.`;
  return null;
}

function abilityHint(draft: CharacterDraft, rules: Ruleset, roll: AbilityRoll | null): string | null {
  if (draft.mode === 'rolled') {
    if (!roll) return '먼저 주사위를 굴려 주세요.';
    return placedScores(draft, rules, roll) ? null : '굴린 점수를 모든 능력치에 하나씩 놓아 주세요.';
  }
  const scores = chosenAbilities(draft, rules, roll);
  if (!scores) return null;
  if (!inRange(rules, scores)) return `점수는 ${rules.score_min}~${rules.score_max} 사이의 정수입니다.`;
  if (draft.mode === 'point_buy') return pointBuyHint(rules.point_buy, scores);
  return null;
}

function inRange(rules: Ruleset, scores: Scores): boolean {
  return Object.values(scores).every(
    (score) => Number.isInteger(score) && score >= rules.score_min && score <= rules.score_max,
  );
}

function pointBuyHint(pointBuy: PointBuy | null, scores: Scores): string | null {
  if (!pointBuy) return '이 규칙에는 점수제가 없습니다.';
  const spent = pointsSpent(pointBuy, scores);
  if (spent === null) return '값표에 없는 점수가 있습니다.';
  return spent > pointBuy.budget ? `총점 ${pointBuy.budget}을 넘었습니다(${spent}).` : null;
}

/** 서버에 보낼 값. 프리젠은 번호만, 나머지는 이름과 설명, 능력치를 정하는 방식은 능력치도 */
export function toCharacterUpdate(draft: CharacterDraft, rules: Ruleset, roll: AbilityRoll | null): CharacterUpdate {
  if (draft.mode === 'pregen') return { mode: 'pregen', pregen_index: draft.pregenIndex };
  const body: CharacterUpdate = { mode: draft.mode, name: draft.name.trim(), description: draft.description };
  const abilities = isPlayerMade(draft.mode) ? chosenAbilities(draft, rules, roll) : null;
  return abilities ? { ...body, abilities } : body;
}

/** 처음 보일 입력. 정해 둔 캐릭터가 있으면 그것으로 채운다(바꾸기) */
export function initialDraft(table: TableDetail, member: TableMember): CharacterDraft {
  const rules = table.rules;
  const current = member.character_mode;
  const mode = current && table.character_modes.includes(current) ? current : (table.character_modes[0] ?? 'custom');
  const roll = freshRoll(member);
  const own = current !== null && current !== 'pregen' ? member.character : null;
  const abilities = member.abilities;
  return {
    mode,
    pregenIndex: member.pregen_index ?? firstFreePregen(table, member.user_id),
    name: own?.name ?? '',
    description: own?.description ?? '',
    manual: current === 'manual' && abilities ? abilities : fill(rules, startingScore(rules)),
    bought: current === 'point_buy' && abilities ? abilities : startingPurchase(rules),
    slots: current === 'rolled' && abilities && roll ? slotsFor(rules, abilities, roll.scores) : {},
    slotsOf: current === 'rolled' && roll ? roll.times_rolled : null,
  };
}

/** 처음 고를 프리젠. 고를 수 있는 것 중 첫째 */
function firstFreePregen(table: TableDetail, myId: string): number | null {
  const index = table.pregens.findIndex((pregen) => pregen.taken_by === null && !pregen.dead);
  if (index >= 0) return index;
  const mine = table.pregens.findIndex((pregen) => pregenAvailable(pregen, myId));
  return mine >= 0 ? mine : null;
}

/** 직접 적기의 처음 점수. 보정이 0 인 점수(modifier.base)를 범위 안으로 */
function startingScore(rules: Ruleset): number {
  return Math.min(rules.score_max, Math.max(rules.score_min, rules.modifier.base));
}

/** 점수제의 처음 점수. 가장 싼 점수(값이 같으면 낮은 점수) */
function startingPurchase(rules: Ruleset): Scores {
  if (!rules.point_buy) return {};
  const cheapest = [...rules.point_buy.costs].sort((a, b) => a.cost - b.cost || a.score - b.score)[0];
  return cheapest ? fill(rules, cheapest.score) : {};
}

function fill(rules: Ruleset, score: number): Scores {
  return Object.fromEntries(rules.abilities.map((ability) => [ability.key, score]));
}

/** 정해 둔 점수를 굴린 점수의 자리로 되돌린다. 같은 점수가 둘이면 앞의 자리부터 */
export function slotsFor(rules: Ruleset, abilities: Scores, scores: number[]): Record<string, number> {
  const used = new Set<number>();
  const slots: Record<string, number> = {};
  for (const ability of rules.abilities) {
    const slot = scores.findIndex((score, index) => !used.has(index) && score === abilities[ability.key]);
    if (slot < 0) continue;
    used.add(slot);
    slots[ability.key] = slot;
  }
  return slots;
}
